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
