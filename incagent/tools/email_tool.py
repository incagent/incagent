"""Email sending tool."""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from incagent.tools.base import BaseTool, ToolParam, ToolResult


class EmailSendTool(BaseTool):
    """Send emails via SMTP."""

    @property
    def name(self) -> str:
        return "email_send"

    @property
    def description(self) -> str:
        return (
            "Send an email to a recipient. Use for trade confirmations, "
            "contract notifications, task assignments to humans, reports."
        )

    @property
    def parameters(self) -> list[ToolParam]:
        return [
            ToolParam("to", "string", "Recipient email address"),
            ToolParam("subject", "string", "Email subject line"),
            ToolParam("body", "string", "Email body (plain text or HTML)"),
            ToolParam("html", "boolean", "Whether body is HTML", required=False, default=False),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        to = kwargs.get("to", "")
        subject = kwargs.get("subject", "")
        body = kwargs.get("body", "")
        is_html = kwargs.get("html", False)

        smtp_host = os.environ.get("SMTP_HOST", "")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_pass = os.environ.get("SMTP_PASS", "")
        from_addr = os.environ.get("SMTP_FROM", smtp_user)

        if not smtp_host or not smtp_user:
            return ToolResult(success=False, error="SMTP_HOST and SMTP_USER not configured")

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = from_addr
            msg["To"] = to

            content_type = "html" if is_html else "plain"
            msg.attach(MIMEText(body, content_type, "utf-8"))

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(from_addr, [to], msg.as_string())

            return ToolResult(success=True, data={"to": to, "subject": subject})
        except Exception as e:
            return ToolResult(success=False, error=str(e))
