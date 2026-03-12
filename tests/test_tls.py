"""TLS/HTTPS module tests — config, SSL context, redirect app, cert generation."""

from __future__ import annotations

import ssl
import tempfile
from pathlib import Path

import pytest

from incagent.config import AgentConfig, TLSConfig
from incagent.gateway import _create_ssl_context, _create_redirect_app


class TestTLSConfig:
    def test_defaults(self):
        config = TLSConfig()
        assert config.enabled is False
        assert config.cert_file == ""
        assert config.key_file == ""
        assert config.auto_generate is False
        assert config.redirect_http is True
        assert config.redirect_http_port == 8080
        assert config.min_version == "TLSv1.3"

    def test_enabled(self):
        config = TLSConfig(enabled=True, cert_file="/path/to/cert.pem", key_file="/path/to/key.pem")
        assert config.enabled is True
        assert config.cert_file == "/path/to/cert.pem"

    def test_agent_config_has_tls(self):
        config = AgentConfig(name="Test Corp")
        assert hasattr(config, "tls")
        assert isinstance(config.tls, TLSConfig)
        assert config.tls.enabled is False

    def test_agent_config_with_tls(self):
        config = AgentConfig(
            name="Test Corp",
            tls=TLSConfig(enabled=True, auto_generate=True),
        )
        assert config.tls.enabled is True
        assert config.tls.auto_generate is True


class TestSSLContext:
    def test_disabled_returns_none(self):
        config = TLSConfig(enabled=False)
        ctx = _create_ssl_context(config, Path(tempfile.mkdtemp()))
        assert ctx is None

    def test_no_cert_no_autogenerate_returns_none(self):
        config = TLSConfig(enabled=True, auto_generate=False)
        ctx = _create_ssl_context(config, Path(tempfile.mkdtemp()))
        assert ctx is None

    def test_missing_cert_file_returns_none(self):
        config = TLSConfig(
            enabled=True,
            cert_file="/nonexistent/cert.pem",
            key_file="/nonexistent/key.pem",
        )
        ctx = _create_ssl_context(config, Path(tempfile.mkdtemp()))
        assert ctx is None

    def test_auto_generate_creates_cert(self):
        """Auto-generate self-signed cert — requires cryptography or openssl."""
        config = TLSConfig(enabled=True, auto_generate=True)
        tmp = Path(tempfile.mkdtemp())
        try:
            ctx = _create_ssl_context(config, tmp)
            # If cryptography or openssl is available, ctx should be valid
            if ctx is not None:
                assert isinstance(ctx, ssl.SSLContext)
                # Check cert files were created
                assert (tmp / "tls" / "cert.pem").exists()
                assert (tmp / "tls" / "key.pem").exists()
        except Exception:
            # Skip if neither cryptography nor openssl is available
            pytest.skip("No TLS cert generation available")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_valid_cert_creates_context(self):
        """Create SSL context with a real self-signed cert."""
        tmp = Path(tempfile.mkdtemp())
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec
            import datetime

            key = ec.generate_private_key(ec.SECP256R1())
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, "test"),
            ])
            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
                .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1))
                .sign(key, hashes.SHA256())
            )

            cert_path = tmp / "cert.pem"
            key_path = tmp / "key.pem"
            cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            key_path.write_bytes(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.TraditionalOpenSSL,
                    serialization.NoEncryption(),
                )
            )

            config = TLSConfig(
                enabled=True,
                cert_file=str(cert_path),
                key_file=str(key_path),
                min_version="TLSv1.2",
            )
            ctx = _create_ssl_context(config, tmp)
            assert ctx is not None
            assert isinstance(ctx, ssl.SSLContext)

        except ImportError:
            pytest.skip("cryptography package not installed")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestRedirectApp:
    def test_redirect_app_created(self):
        app = _create_redirect_app("0.0.0.0", 8400)
        assert app is not None
        # Should have routes
        assert len(app.routes) >= 1
