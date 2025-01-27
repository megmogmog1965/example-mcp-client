import asyncio
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()  # load environment variables from .env


class TeeStdin:
    """
    MCP Client ⇔ Server 間のプロセス間通信（標準入出力）を盗み見る PIPE.
    """

    def __init__(self, original_stdin):
        self._stdin = original_stdin

    async def __aenter__(self):
        await self._stdin.__aenter__()
        return self

    async def __aexit__(self, *args):
        await self._stdin.__aexit__(*args)

    def __aiter__(self):
        self._stdin.__aiter__()
        return self

    async def __anext__(self):
        receive_stream = await self._stdin.__anext__()
        print('_' * 16)
        print(receive_stream)
        print('_' * 16)
        return receive_stream

    def __getattr__(self, name):
        return getattr(self._stdin, name)


class TeeWrite:
    """
    MCP Client ⇔ Server 間のプロセス間通信（標準入出力）を盗み見る PIPE.
    """

    def __init__(self, original_write):
        self._write = original_write

    def send_nowait(self, item):
        print('_' * 16)
        print(item)
        print('_' * 16)
        self._write.send_nowait(item)

    async def send(self, *args):
        print('_' * 16)
        print(args[0])
        print('_' * 16)
        await self._write.send(*args)

    async def __aenter__(self):
        await self._write.__aenter__()
        return self

    async def __aexit__(self, *args):
        await self._write.__aexit__(*args)

    def __aiter__(self):
        self._write.__aiter__()
        return self

    async def __anext__(self):
        return await self._write.__anext__()

    def __getattr__(self, name):
        return getattr(self._write, name)


class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic()

    async def connect_to_server(self, command: str, args: list):
        """Connect to an MCP server

        Args:
            command: e.g., "npx"
            args: e.g., ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
        """
        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=None
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport

        self.stdio = TeeStdin(self.stdio)
        self.write = TeeWrite(self.write)

        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools])

    async def process_query(self, query: str) -> str:
        """Process a query using Claude and available tools"""
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]

        response = await self.session.list_tools()
        available_tools = [{
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        } for tool in response.tools]

        # Initial Claude API call
        response = self.anthropic.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            messages=messages,
            tools=available_tools
        )

        # Process response and handle tool calls
        tool_results = []
        final_text = []

        for content in response.content:
            if content.type == 'text':
                final_text.append(content.text)
            elif content.type == 'tool_use':
                tool_name = content.name
                tool_args = content.input

                # Execute tool call
                result = await self.session.call_tool(tool_name, tool_args)
                tool_results.append({"call": tool_name, "result": result})
                final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")

                # Continue conversation with tool results
                if hasattr(content, 'text') and content.text:
                    messages.append({
                        "role": "assistant",
                        "content": content.text
                    })
                messages.append({
                    "role": "user",
                    "content": result.content
                })

                # Get next response from Claude
                response = self.anthropic.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    messages=messages,
                )

                final_text.append(response.content[0].text)

        return "\n".join(final_text)

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")

        while True:
            try:
                query = input("\nQuery: ").strip()

                if query.lower() == 'quit':
                    break

                response = await self.process_query(query)
                print("\n" + response)

            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()


async def main():
    if len(sys.argv) < 3:
        print("Usage: python client.py <command> <args>")
        sys.exit(1)

    client = MCPClient()
    try:
        command = sys.argv[1]
        args = sys.argv[2:]

        await client.connect_to_server(command, args)
        await client.chat_loop()
    finally:
        await client.cleanup()


if __name__ == "__main__":
    import sys
    asyncio.run(main())
