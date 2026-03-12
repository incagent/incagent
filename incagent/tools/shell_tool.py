"""Shell command execution tool — hardened with security validation.

Security layers:
1. Blocked patterns (reverse shells, data exfil, privilege escalation, etc.)
2. Optional strict mode (command allowlist)
3. Timeout enforcement
4. Output truncation to prevent memory exhaustion
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from incagent.tools.base import BaseTool, ToolParam, ToolResult


class ShellExecTool(BaseTool):
    """Execute shell commands on the host system with security validation."""

    @property
    def name(self) -> str:
        return "shell_exec"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command on the host system. "
            "Dangerous commands are blocked. "
            "Use for running scripts, build commands, data processing."
        )

    @property
    def parameters(self) -> list[ToolParam]:
        return [
            ToolParam("command", "string", "Shell command to execute"),
            ToolParam("timeout", "number", "Timeout in seconds (max 120)", required=False, default=60),
            ToolParam("cwd", "string", "Working directory", required=False),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command", "")
        timeout = min(kwargs.get("timeout", 60), 120)  # Cap at 120s
        cwd = kwargs.get("cwd")

        if not command:
            return ToolResult(success=False, error="Command is required")

        # Security validation
        try:
            from incagent.security import validate_shell_command
            strict = os.environ.get("INCAGENT_SHELL_STRICT", "").lower() in ("1", "true", "yes")
            violations = validate_shell_command(command, strict=strict)
            if violations:
                return ToolResult(
                    success=False,
                    error=f"Command blocked: {'; '.join(violations)}",
                )
        except ImportError:
            # Fallback to basic blocklist if security module unavailable
            blocked = [
                "rm -rf /", "rm -rf ~", "mkfs", "dd if=",
                ":(){:|:&};:", "sudo", "/dev/tcp/",
                "nc -", "curl|bash", "wget|bash",
            ]
            for b in blocked:
                if b in command:
                    return ToolResult(success=False, error=f"Blocked dangerous command pattern: {b}")

        # Validate cwd if provided
        if cwd:
            data_dir = os.environ.get("INCAGENT_DATA_DIR", "")
            if data_dir:
                from pathlib import Path
                cwd_path = Path(cwd).resolve()
                base_path = Path(data_dir).resolve()
                if not str(cwd_path).startswith(str(base_path)):
                    return ToolResult(
                        success=False,
                        error="Working directory must be within INCAGENT_DATA_DIR",
                    )

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=float(timeout),
            )

            return ToolResult(
                success=proc.returncode == 0,
                data={
                    "exit_code": proc.returncode,
                    "stdout": stdout.decode("utf-8", errors="replace")[:10000],
                    "stderr": stderr.decode("utf-8", errors="replace")[:5000],
                },
                error=stderr.decode("utf-8", errors="replace")[:1000] if proc.returncode != 0 else None,
            )
        except asyncio.TimeoutError:
            return ToolResult(success=False, error=f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
