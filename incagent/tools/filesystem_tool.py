"""Filesystem tool — read, write, list files in the agent's data directory."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from incagent.tools.base import BaseTool, ToolParam, ToolResult

# Agent can only access files within its own data directory
_ALLOWED_ROOT = os.environ.get("INCAGENT_DATA_DIR", "")


def _safe_path(base: str, relative: str) -> Path | None:
    """Resolve path and ensure it stays within base directory."""
    if not base:
        return None
    base_path = Path(base).resolve()
    target = (base_path / relative).resolve()
    if not str(target).startswith(str(base_path)):
        return None  # Path traversal attempt
    return target


class FileReadTool(BaseTool):
    """Read files from the agent's data directory."""

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return "Read a file from the agent's data directory. Returns file contents."

    @property
    def parameters(self) -> list[ToolParam]:
        return [
            ToolParam("path", "string", "Relative path within data directory"),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        rel_path = kwargs.get("path", "")
        data_dir = os.environ.get("INCAGENT_DATA_DIR", _ALLOWED_ROOT)
        target = _safe_path(data_dir, rel_path)

        if not target:
            return ToolResult(success=False, error="Invalid path or data directory not configured")
        if not target.exists():
            return ToolResult(success=False, error=f"File not found: {rel_path}")

        try:
            content = target.read_text(encoding="utf-8")
            return ToolResult(success=True, data={"path": rel_path, "content": content, "size": len(content)})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class FileWriteTool(BaseTool):
    """Write files to the agent's data directory."""

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        return (
            "Write a file to the agent's data directory. "
            "Use for generating reports, contracts, invoices, exports."
        )

    @property
    def parameters(self) -> list[ToolParam]:
        return [
            ToolParam("path", "string", "Relative path within data directory"),
            ToolParam("content", "string", "File content to write"),
            ToolParam("append", "boolean", "Append instead of overwrite", required=False, default=False),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        rel_path = kwargs.get("path", "")
        content = kwargs.get("content", "")
        append = kwargs.get("append", False)

        data_dir = os.environ.get("INCAGENT_DATA_DIR", _ALLOWED_ROOT)
        target = _safe_path(data_dir, rel_path)

        if not target:
            return ToolResult(success=False, error="Invalid path or data directory not configured")

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with open(target, mode, encoding="utf-8") as f:
                f.write(content)
            return ToolResult(success=True, data={"path": rel_path, "size": len(content)})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class FileListTool(BaseTool):
    """List files in the agent's data directory."""

    @property
    def name(self) -> str:
        return "file_list"

    @property
    def description(self) -> str:
        return "List files and directories in the agent's data directory."

    @property
    def parameters(self) -> list[ToolParam]:
        return [
            ToolParam("path", "string", "Relative directory path", required=False, default="."),
            ToolParam("pattern", "string", "Glob pattern to filter", required=False, default="*"),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        rel_path = kwargs.get("path", ".")
        pattern = kwargs.get("pattern", "*")

        data_dir = os.environ.get("INCAGENT_DATA_DIR", _ALLOWED_ROOT)
        target = _safe_path(data_dir, rel_path)

        if not target:
            return ToolResult(success=False, error="Invalid path or data directory not configured")
        if not target.is_dir():
            return ToolResult(success=False, error=f"Not a directory: {rel_path}")

        try:
            entries = []
            for p in sorted(target.glob(pattern)):
                entries.append({
                    "name": p.name,
                    "type": "dir" if p.is_dir() else "file",
                    "size": p.stat().st_size if p.is_file() else 0,
                })
            return ToolResult(success=True, data={"path": rel_path, "entries": entries})
        except Exception as e:
            return ToolResult(success=False, error=str(e))
