"""Tool registry — discovers, loads, and manages tools.

Built-in tools are loaded automatically.
Custom tools from the tools directory are hot-reloaded.
Agent can create new tools at runtime via create_tool().

Security:
- All dynamically created tools pass through CodeSandbox validation
- Blocked imports/patterns prevent code injection
- Tool names are sanitized
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import sys
from pathlib import Path
from typing import Any

from incagent.tools.base import BaseTool, ToolResult

logger = logging.getLogger("incagent.tools")

# Built-in tool modules (relative to incagent.tools package)
_BUILTIN_MODULES = [
    "incagent.tools.slack_tool",
    "incagent.tools.email_tool",
    "incagent.tools.webhook_tool",
    "incagent.tools.filesystem_tool",
    "incagent.tools.shell_tool",
    "incagent.tools.http_tool",
]


class ToolRegistry:
    """Manages all available tools for an agent."""

    def __init__(self, custom_tools_dir: Path | str | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._custom_dir = Path(custom_tools_dir) if custom_tools_dir else None
        self._load_builtins()
        if self._custom_dir:
            self._load_custom()

    def _load_builtins(self) -> None:
        """Load all built-in tools."""
        for mod_name in _BUILTIN_MODULES:
            try:
                mod = importlib.import_module(mod_name)
                self._register_from_module(mod)
            except ImportError as e:
                # Optional dependencies missing (e.g., slack_sdk) - skip silently
                logger.debug("Skipping built-in tool %s: %s", mod_name, e)
            except Exception as e:
                logger.warning("Failed to load built-in tool %s: %s", mod_name, e)

    def _load_custom(self) -> None:
        """Load custom tools from the tools directory."""
        if not self._custom_dir or not self._custom_dir.exists():
            return

        for py_file in sorted(self._custom_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                # Validate code before loading
                code = py_file.read_text(encoding="utf-8")
                violations = self._validate_code(code)
                if violations:
                    logger.warning(
                        "Custom tool %s failed security check: %s",
                        py_file.name, violations,
                    )
                    continue

                spec = importlib.util.spec_from_file_location(
                    f"incagent_custom_tool_{py_file.stem}", py_file,
                )
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = mod
                    spec.loader.exec_module(mod)
                    self._register_from_module(mod)
                    logger.info("Loaded custom tool from %s", py_file.name)
            except Exception as e:
                logger.warning("Failed to load custom tool %s: %s", py_file.name, e)

    def _validate_code(self, code: str) -> list[str]:
        """Validate tool code through CodeSandbox.

        Returns list of violations (empty = safe).
        """
        try:
            from incagent.security import CodeSandbox
            sandbox = CodeSandbox()
            return sandbox.validate(code)
        except ImportError:
            # Security module not available, do basic check
            if "BaseTool" not in code:
                return ["Code must define a BaseTool subclass"]
            return []

    def _register_from_module(self, mod: Any) -> None:
        """Find and register all BaseTool subclasses in a module."""
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, BaseTool) and obj is not BaseTool:
                try:
                    instance = obj()
                    self.register(instance)
                except Exception as e:
                    logger.warning("Failed to instantiate tool %s: %s", obj.__name__, e)

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def unregister(self, name: str) -> bool:
        """Remove a tool by name."""
        return self._tools.pop(name, None) is not None

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        """List all available tools with their schemas."""
        return [t.schema() for t in self._tools.values()]

    def list_names(self) -> list[str]:
        """List tool names."""
        return list(self._tools.keys())

    async def execute(self, tool_name: str, **kwargs: Any) -> ToolResult:
        """Execute a tool by name."""
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

        try:
            return await tool.execute(**kwargs)
        except Exception as e:
            logger.error("Tool %s execution failed: %s", tool_name, e)
            return ToolResult(success=False, error=str(e))

    def reload(self) -> None:
        """Reload custom tools (hot-reload)."""
        if self._custom_dir:
            # Remove previously loaded custom tools
            custom_names = [
                name for name, t in self._tools.items()
                if getattr(t, '_is_custom', False)
            ]
            for name in custom_names:
                del self._tools[name]
            self._load_custom()

    def create_tool(self, name: str, code: str) -> bool:
        """Create a new custom tool by writing a Python file.

        The agent calls this to extend its own capabilities.
        The code must define a class that inherits from BaseTool.

        Security: Code is validated through CodeSandbox before execution.
        """
        if not self._custom_dir:
            logger.warning("No custom tools directory configured")
            return False

        # Sanitize tool name
        try:
            from incagent.security import InputValidator
            safe_name = InputValidator.sanitize_name(name)
            if not safe_name:
                logger.error("Invalid tool name: %s", name)
                return False
        except ImportError:
            safe_name = name.replace(" ", "_").lower()

        # Validate code safety
        violations = self._validate_code(code)
        if violations:
            logger.error(
                "Tool code for '%s' failed security validation: %s",
                safe_name, violations,
            )
            return False

        self._custom_dir.mkdir(parents=True, exist_ok=True)
        path = self._custom_dir / f"{safe_name}.py"

        path.write_text(code, encoding="utf-8")
        logger.info("Created custom tool file: %s", path)

        # Hot-load the new tool
        try:
            spec = importlib.util.spec_from_file_location(
                f"incagent_custom_tool_{safe_name}", path,
            )
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = mod
                spec.loader.exec_module(mod)
                self._register_from_module(mod)
                # Mark as custom for reload tracking
                tool = self._tools.get(safe_name)
                if tool:
                    tool._is_custom = True  # type: ignore[attr-defined]
                return True
        except Exception as e:
            logger.error("Failed to load created tool %s: %s", safe_name, e)
            path.unlink(missing_ok=True)

        return False

    @property
    def count(self) -> int:
        return len(self._tools)
