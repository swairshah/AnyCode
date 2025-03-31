import os
import asyncio
import sys
import json
import warnings
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.openai import OpenAIModel

# why the fuck does asyncio eventloop not work properly
import uvloop
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

def load_mcp_config(config_path="mcp_config.json"):
    """Load MCP server configurations from a JSON file."""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config.get('mcpServers', {})
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error loading MCP config: {e}")
        return {}

def initialize_mcp_servers(config):
    """Initialize MCP servers from configuration."""
    servers = []
    
    for name, server_config in config.items():
        command = server_config.get('command')
        args = server_config.get('args', [])
        env = server_config.get('env', {})
        
        if command:
            server_env = os.environ.copy()
            server_env.update(env)
            
            server = MCPServerStdio(
                command,
                args,
                env=server_env if env else None
            )
            servers.append(server)
            print(f"Initialized MCP server: {name}")
    
    return servers

import functools
import inspect
from typing import Callable, Any, Dict, Optional

def register_tool_with_signature(agent, original_func, tool_name=None):
    """
    Register a function as a tool with pydantic-ai while preserving its signature.
    
    This helper allows you to avoid duplicating function signatures when
    registering tools with pydantic-ai.
    
    Args:
        agent: The pydantic-ai Agent instance
        original_func: The function to register as a tool
        tool_name: Optional custom name for the tool (defaults to function name)
    
    Returns:
        The registered tool function
    """
    # Create a wrapper that preserves docstring and signature
    @functools.wraps(original_func)
    async def wrapper(*args, **kwargs):
        return await original_func(*args, **kwargs)
    
    # Register the wrapper as a tool
    name = tool_name or original_func.__name__
    
    # Apply the decorator to our wrapper function
    wrapped_tool = agent.tool_plain(wrapper)
    
    # Store the registered tool in the agent's tools dict under the specified name
    return wrapped_tool

def register_core_tools(agent, tools_dict):
    """
    Register multiple tools from a dictionary while preserving signatures.
    
    Args:
        agent: The pydantic-ai Agent instance
        tools_dict: Dictionary mapping tool names to functions
    
    Returns:
        Dictionary of registered tool functions
    """
    registered_tools = {}
    
    for name, func in tools_dict.items():
        registered_tools[name] = register_tool_with_signature(agent, func, name)
        
    return registered_tools


async def test():
    model = OpenAIModel("gpt-4o-mini")
    mcp_config = load_mcp_config()
    
    mcp_servers = initialize_mcp_servers(mcp_config)
    
    agent = Agent(model, mcp_servers=mcp_servers)
    
    async with agent.run_mcp_servers() as servers:
        query = "What's the most recent commit in the current git repository?"
        if len(sys.argv) > 1:
            query = " ".join(sys.argv[1:])
            
        print(f"Running query: {query}")
        result = await agent.run(query)
    
    result_data = result.data
    print("\nResult:")
    print(result_data)

if __name__ == "__main__":
    asyncio.run(test())
