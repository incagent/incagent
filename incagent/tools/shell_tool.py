"""Shell command execution tool — run system commands."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from incagent.tools.base import BaseTool, ToolParam, ToolResult


class ShellExecTool(BaseTool):
    """Execute shell commands on the host system."""

    @property
    def name(self) -> str:
        return "shell_exec"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command on the host system. "
            "Use for system operations, running scripts, managing processes, "
            "installing packages, generating PDFs, database operations."
        )

    @property
    def parameters(self) -> list[ToolParam]:
        return [
            ToolParam("command", "string", "Shell command to execute"),
            ToolParam("timeout", "number", "Timeout in seconds", required=False, default=60),
            ToolParam("cwd", "string", "Working directory", required=False),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command", "")
        timeout = kwargs.get("timeout", 60)
        cwd = kwargs.get("cwd")

        if not command:
            return ToolResult(success=False, error="Command is required")

        # Safety: block obviously destructive commands
        blocked = ["rm -rf /", "mkfs", "dd if=", ":(){:|:&};:"]
        for b in blocked:
            if b in command:
                return ToolResult(success=False, error=f"Blocked dangerous command pattern: {b}")

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
