from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from multiagent.mcp.client import _MCP_AVAILABLE, MCPClient, MCPServerConfig

pytestmark = pytest.mark.skipif(not _MCP_AVAILABLE, reason="MCP SDK kurulu degil")


def test_mcp_config_validation() -> None:
    # Valid configs
    MCPServerConfig(command="node").validate()
    MCPServerConfig(url="http://localhost:8000").validate()

    # Invalid configs
    with pytest.raises(ValueError, match="command veya url"):
        MCPServerConfig().validate()

    with pytest.raises(ValueError, match="hem command hem url"):
        MCPServerConfig(command="node", url="http://localhost").validate()


@pytest.mark.asyncio
async def test_mcp_client_list_tools() -> None:
    config = MCPServerConfig(command="node")
    client = MCPClient(config)

    # Mock Tool
    mock_tool = MagicMock()
    mock_tool.name = "test_tool"
    mock_tool.description = "A test tool"
    mock_tool.inputSchema = {"type": "object"}

    # Mock ListToolsResult
    mock_list_result = MagicMock()
    mock_list_result.tools = [mock_tool]

    # Mock ClientSession
    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_session.list_tools = AsyncMock(return_value=mock_list_result)

    # Mock stdio_client
    mock_stdio_client = AsyncMock()
    mock_stdio_client.__aenter__.return_value = (AsyncMock(), AsyncMock())

    with patch("multiagent.mcp.client.stdio_client", return_value=mock_stdio_client):
        with patch("multiagent.mcp.client.ClientSession") as mock_ClientSession:
            # When we use ClientSession as async context manager,
            # we need its __aenter__ to return mock_session
            mock_ClientSession.return_value.__aenter__.return_value = mock_session

            async with client:
                tools = await client.list_tools()

            assert len(tools) == 1
            assert tools[0].name == "test_tool"
            assert tools[0].description == "A test tool"
            assert tools[0].input_schema == {"type": "object"}
            mock_session.initialize.assert_awaited_once()


@pytest.mark.asyncio
async def test_mcp_client_call_tool() -> None:
    config = MCPServerConfig(url="http://localhost:8000/sse")
    client = MCPClient(config)

    # Mock TextContent
    mock_content = MagicMock()
    mock_content.type = "text"
    mock_content.text = "Tool execution result"

    # Mock CallToolResult
    mock_call_result = MagicMock()
    mock_call_result.content = [mock_content]

    # Mock ClientSession
    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=mock_call_result)

    # Mock sse_client
    mock_sse_client = AsyncMock()
    mock_sse_client.__aenter__.return_value = (AsyncMock(), AsyncMock())

    with patch("multiagent.mcp.client.sse_client", return_value=mock_sse_client):
        with patch("multiagent.mcp.client.ClientSession") as mock_ClientSession:
            mock_ClientSession.return_value.__aenter__.return_value = mock_session

            async with client:
                result = await client.call_tool("test_tool", {"arg1": "val1"})

            assert result == "Tool execution result"
            mock_session.call_tool.assert_awaited_once_with(
                "test_tool", {"arg1": "val1"}
            )
