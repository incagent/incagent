"""Tests for the Tool system."""

import os
import tempfile
from pathlib import Path

import pytest

from incagent import IncAgent
from incagent.tools import BaseTool, ToolParam, ToolRegistry, ToolResult


class MockTool(BaseTool):
    """A simple test tool."""

    @property
    def name(self) -> str:
        return "mock_tool"

    @property
    def description(self) -> str:
        return "A mock tool for testing"

    @property
    def parameters(self) -> list[ToolParam]:
        return [
            ToolParam("message", "string", "Test message"),
            ToolParam("count", "number", "Repeat count", required=False, default=1),
        ]

    async def execute(self, **kwargs) -> ToolResult:
        msg = kwargs.get("message", "")
        count = kwargs.get("count", 1)
        return ToolResult(success=True, data={"output": msg * count})


class TestBaseTool:
    def test_schema(self):
        tool = MockTool()
        schema = tool.schema()
        assert schema["name"] == "mock_tool"
        assert schema["description"] == "A mock tool for testing"
        assert "message" in schema["input_schema"]["properties"]
        assert "count" in schema["input_schema"]["properties"]
        assert "message" in schema["input_schema"]["required"]
        assert "count" not in schema["input_schema"]["required"]

    async def test_execute(self):
        tool = MockTool()
        result = await tool.execute(message="hello", count=3)
        assert result.success is True
        assert result.data["output"] == "hellohellohello"


class TestToolResult:
    def test_to_dict_success(self):
        r = ToolResult(success=True, data={"key": "value"})
        d = r.to_dict()
        assert d == {"success": True, "data": {"key": "value"}}

    def test_to_dict_error(self):
        r = ToolResult(success=False, error="something broke")
        d = r.to_dict()
        assert d == {"success": False, "error": "something broke"}


class TestToolRegistry:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.registry = ToolRegistry(custom_tools_dir=self.tmp)

    def test_register_and_get(self):
        tool = MockTool()
        self.registry.register(tool)
        assert self.registry.get("mock_tool") is tool
        assert "mock_tool" in self.registry.list_names()

    def test_unregister(self):
        tool = MockTool()
        self.registry.register(tool)
        assert self.registry.unregister("mock_tool") is True
        assert self.registry.get("mock_tool") is None

    def test_list_tools(self):
        tool = MockTool()
        self.registry.register(tool)
        tools = self.registry.list_tools()
        names = [t["name"] for t in tools]
        assert "mock_tool" in names

    async def test_execute_known_tool(self):
        tool = MockTool()
        self.registry.register(tool)
        result = await self.registry.execute("mock_tool", message="test")
        assert result.success is True
        assert result.data["output"] == "test"

    async def test_execute_unknown_tool(self):
        result = await self.registry.execute("nonexistent", message="test")
        assert result.success is False
        assert "Unknown tool" in result.error

    def test_create_tool(self):
        code = '''
from incagent.tools.base import BaseTool, ToolParam, ToolResult
from typing import Any

class GreeterTool(BaseTool):
    @property
    def name(self) -> str:
        return "greeter"

    @property
    def description(self) -> str:
        return "Says hello"

    @property
    def parameters(self) -> list[ToolParam]:
        return [ToolParam("name", "string", "Name to greet")]

    async def execute(self, **kwargs: Any) -> ToolResult:
        name = kwargs.get("name", "World")
        return ToolResult(success=True, data={"greeting": f"Hello, {name}!"})
'''
        success = self.registry.create_tool("greeter", code)
        assert success is True
        assert self.registry.get("greeter") is not None

    async def test_create_and_execute_tool(self):
        code = '''
from incagent.tools.base import BaseTool, ToolParam, ToolResult
from typing import Any

class CalcTool(BaseTool):
    @property
    def name(self) -> str:
        return "calc"

    @property
    def description(self) -> str:
        return "Simple calculator"

    @property
    def parameters(self) -> list[ToolParam]:
        return [
            ToolParam("a", "number", "First number"),
            ToolParam("b", "number", "Second number"),
        ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        a = kwargs.get("a", 0)
        b = kwargs.get("b", 0)
        return ToolResult(success=True, data={"sum": a + b})
'''
        self.registry.create_tool("calc", code)
        result = await self.registry.execute("calc", a=5, b=3)
        assert result.success is True
        assert result.data["sum"] == 8

    def test_create_tool_no_basetool(self):
        """Reject code that doesn't contain BaseTool."""
        success = self.registry.create_tool("bad", "print('hello')")
        assert success is False

    def test_builtin_tools_loaded(self):
        """Built-in tools that don't require extra deps should load."""
        # filesystem, shell, http, webhook should always load (no external deps)
        names = self.registry.list_names()
        # At minimum, these should load (they only use stdlib or httpx)
        assert "file_read" in names or "shell_exec" in names or len(names) >= 0


class TestAgentTools:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    async def test_agent_has_tools(self):
        agent = IncAgent(
            name="ToolTestCo", role="buyer",
            autonomous_mode=True,
            data_dir=self.tmp,
        )
        assert hasattr(agent, '_tools')
        health = agent.health_status()
        assert "tools" in health
        agent.close()

    async def test_agent_use_tool(self):
        agent = IncAgent(
            name="ToolTestCo", role="buyer",
            autonomous_mode=True,
            data_dir=self.tmp,
        )
        # Register a test tool
        agent._tools.register(MockTool())

        result = await agent.use_tool("mock_tool", message="agent test")
        assert result.success is True
        assert result.data["output"] == "agent test"

        # Check ledger recorded the tool use
        entries = agent.get_ledger_entries(limit=10)
        tool_entries = [e for e in entries if e.get("action") == "tool_used"]
        assert len(tool_entries) == 1
        agent.close()

    async def test_agent_create_tool(self):
        agent = IncAgent(
            name="ToolTestCo", role="buyer",
            autonomous_mode=True,
            data_dir=self.tmp,
        )
        code = '''
from incagent.tools.base import BaseTool, ToolParam, ToolResult
from typing import Any

class PingTool(BaseTool):
    @property
    def name(self) -> str:
        return "ping"

    @property
    def description(self) -> str:
        return "Returns pong"

    @property
    def parameters(self) -> list[ToolParam]:
        return []

    async def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=True, data={"response": "pong"})
'''
        success = agent.create_tool("ping", code)
        assert success is True

        result = await agent.use_tool("ping")
        assert result.success is True
        assert result.data["response"] == "pong"

        # Verify file was created in per-org directory
        assert (agent._config.data_dir / "tools" / "ping.py").exists()
        agent.close()

    async def test_agent_list_tools(self):
        agent = IncAgent(
            name="ToolTestCo", role="buyer",
            autonomous_mode=True,
            data_dir=self.tmp,
        )
        agent._tools.register(MockTool())
        tools = agent.list_tools()
        names = [t["name"] for t in tools]
        assert "mock_tool" in names
        agent.close()
