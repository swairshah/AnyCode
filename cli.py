import os
import asyncio
import sys
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.text import Text
from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.openai import OpenAIModel
from typing import Dict, List, Optional, Any, Union
import inspect
import uvloop

from code_tools import (
    glob_tool, grep_tool, ls_tool, view_tool, 
    edit_tool, replace_tool, bash_tool,
    notebook_read_tool, notebook_edit_tool,
    agent_tool, batch_tool, TOOLS
)

from utils import register_tool_with_signature

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

console = Console()

TOOL_NAMES = {
    glob_tool: "glob_search",
    grep_tool: "grep_search",
    ls_tool: "list_files",
    view_tool: "view_file",
    edit_tool: "edit_file", 
    replace_tool: "replace_file",
    bash_tool: "run_bash",
    notebook_read_tool: "read_notebook",
    notebook_edit_tool: "edit_notebook",
    agent_tool: "launch_agent",
    batch_tool: "run_batch"
}

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
    
    register_tools(agent)
    
    agent.message_history = []
    return agent

def register_tools(agent):
    """Register all tools from code_tools.py with the agent"""
    
    # Register tools in a loop
    for func, display_name in TOOL_NAMES.items():
        register_tool_with_signature(agent, func, display_name)
    
    # Add context-dependent tools
    @agent.tool
    def get_current_directory(ctx: RunContext) -> str:
        """Get the current working directory."""
        return os.getcwd()

async def run_streaming(agent, servers, query):
    buffer = ""
    print_buffer = ""
    print_threshold = 100  # Number of characters to print at once
    
    async with agent.run_stream(query, message_history=agent.message_history) as result:
        async for chunk in result.stream():
            new_content = chunk[len(buffer):]
            buffer = chunk
            
            if new_content:
                print_buffer += new_content
                # Check if the print_buffer exceeds the threshold
                if len(print_buffer) >= print_threshold:
                    console.print(Text(print_buffer, style="grey70"), end="")
                    print_buffer = ""  # Clear the buffer after printing

        if print_buffer:
            console.print(Text(print_buffer, style="grey70"), end="")
        
        agent.message_history.extend(result.new_messages())
    return True

async def main():
    console.print(Panel(Text("AnyCode Tools CLI", style="dark_orange3"), subtitle="Press Ctrl+C to exit"))
    
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
