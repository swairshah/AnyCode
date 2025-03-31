import os
import asyncio
import sys
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.text import Text
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.openai import OpenAIModel

import uvloop
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

console = Console()

async def initialize_agent():
    model = OpenAIModel("gpt-4o-mini")
    fs_server = MCPServerStdio(
        'npx', 
        ["@modelcontextprotocol/server-filesystem", os.getcwd()]
    )  
    git_server = MCPServerStdio(
        "uv",
        ["--directory", os.getcwd(), "run", "mcp-server-git"]
    )
    agent = Agent(model, mcp_servers=[fs_server, git_server])
    agent.message_history = []
    return agent

async def run_streaming(agent, servers, query):
    # for sync: result = await agent.run(query, message_history=agent.message_history)
    buffer = ""
    async with agent.run_stream(query, message_history=agent.message_history) as result:
        async for chunk in result.stream():
            new_content = chunk[len(buffer):]
            if new_content:
                console.print(Text(new_content, style="grey70"), end="")
            buffer = chunk
        agent.message_history.extend(result.new_messages())
    return True

async def main():
    console.print(Panel(Text("Agent CLI", style="dark_orange3"), subtitle="Press Ctrl+C to exit"))
    
    agent = await initialize_agent()
    
    async with agent.run_mcp_servers() as servers:
        console.print("[bold green]MCP servers started successfully[/bold green]")
        
        while True:
            try:
                query = Prompt.ask("\n[dark_orange3] ➤ ")
                if query.lower() in ["exit", "quit"]:
                    break
                    
                await run_streaming(agent, servers, query)
                
            except KeyboardInterrupt:
                console.print("\n[bold yellow]Exiting ...[/bold yellow]")
                break
            except Exception as e:
                console.print(f"[bold red]Unexpected error: {str(e)}[/bold red]")
        
        console.print("[bold yellow]Shutting down MCP servers...[/bold yellow]")

if __name__ == "__main__":
    asyncio.run(main())
