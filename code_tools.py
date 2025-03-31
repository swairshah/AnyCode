from __future__ import annotations

import asyncio
import os
import json
import re
import glob as glob_module
import subprocess
import shutil
import pathlib
from typing import Dict, List, Optional, Any, Union, Callable, Generator, AsyncGenerator
import time
from dataclasses import dataclass


@dataclass
class ToolSuccessResponse:
    """Response when a tool executes successfully"""
    result: Any
    message: str


@dataclass
class ToolErrorResponse:
    """Response when a tool execution fails"""
    error_message: str


ToolResponse = Union[ToolSuccessResponse, ToolErrorResponse]


async def glob_tool(pattern: str, path: Optional[str] = None) -> Dict:
    """Fast file pattern matching tool that works with any codebase size.
    
    Args:
        pattern: The glob pattern to match files against
        path: The directory to search in (optional)
    """
    start_time = time.time()
    try:
        search_path = path or os.getcwd()
        
        if not os.path.isabs(search_path):
            search_path = os.path.abspath(search_path)
            
        # Execute glob search
        glob_path = os.path.join(search_path, pattern)
        matching_files = glob_module.glob(glob_path, recursive=True)
        
        # Sort by modification time
        matching_files.sort(key=lambda f: os.path.getmtime(f) if os.path.exists(f) else 0, reverse=True)
        
        # Limit results to prevent excessive output
        truncated = len(matching_files) > 100
        matching_files = matching_files[:100]
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        result = {
            "filenames": matching_files,
            "durationMs": duration_ms,
            "numFiles": len(matching_files),
            "truncated": truncated
        }
        
        return result
    except Exception as e:
        return {"error": f"Error in GlobTool: {str(e)}"}


async def grep_tool(pattern: str, path: Optional[str] = None, include: Optional[str] = None) -> Dict:
    """Fast content search tool that searches file contents using regular expressions.
    
    Args:
        pattern: The regular expression pattern to search for
        path: The directory to search in (optional)
        include: File pattern to include in the search (optional)
    """
    start_time = time.time()
    try:
        search_path = path or os.getcwd()
        
        # Make sure the path is absolute
        if not os.path.isabs(search_path):
            search_path = os.path.abspath(search_path)
            
        # Check if ripgrep (rg) is available
        has_ripgrep = shutil.which("rg") is not None
        
        matching_files = []
        
        if has_ripgrep:
            # Use ripgrep for faster searching
            cmd = ["rg", "-l", pattern]
            if include:
                cmd.extend(["--glob", include])
                
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=search_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, _ = await process.communicate()
            results = stdout.decode("utf-8").strip().split("\n")
            matching_files = [os.path.join(search_path, file) for file in results if file]
            
        else:
            # Fallback to Python's built-in functionality (slower)
            all_files = []
            
            # If include pattern is provided, use it to filter files
            if include:
                for root, _, files in os.walk(search_path):
                    for file in files:
                        if _glob_match(file, include):
                            all_files.append(os.path.join(root, file))
            else:
                for root, _, files in os.walk(search_path):
                    for file in files:
                        all_files.append(os.path.join(root, file))
            
            # Search files for pattern
            regex = re.compile(pattern)
            for file_path in all_files:
                try:
                    with open(file_path, 'r', errors='ignore') as f:
                        content = f.read()
                        if regex.search(content):
                            matching_files.append(file_path)
                except Exception:
                    # Skip files that can't be read
                    continue
        
        # Sort by modification time
        matching_files.sort(
            key=lambda f: os.path.getmtime(f) if os.path.exists(f) else 0,
            reverse=True
        )
        
        # Limit results to prevent excessive output
        truncated = len(matching_files) > 100
        matching_files = matching_files[:100]
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        result = {
            "filenames": matching_files,
            "durationMs": duration_ms,
            "numFiles": len(matching_files),
            "truncated": truncated
        }
        
        return result
    except Exception as e:
        return {"error": f"Error in GrepTool: {str(e)}"}


def _glob_match(filename: str, pattern: str) -> bool:
    """Simple glob pattern matching for filenames"""
    import fnmatch
    return fnmatch.fnmatch(filename, pattern)


async def ls_tool(path: str, ignore: Optional[List[str]] = None) -> List[str]:
    """Lists files and directories in a given path.
    
    Args:
        path: The absolute path to the directory to list
        ignore: List of glob patterns to ignore (optional)
    """
    try:
        # Make sure the path is absolute
        if not os.path.isabs(path):
            path = os.path.abspath(path)
            
        if not os.path.exists(path):
            return []
        
        if not os.path.isdir(path):
            return []
        
        # Get directory contents
        entries = os.listdir(path)
        
        # Filter ignored patterns if provided
        if ignore:
            import fnmatch
            filtered_entries = []
            for entry in entries:
                if not any(fnmatch.fnmatch(entry, pattern) for pattern in ignore):
                    filtered_entries.append(entry)
            entries = filtered_entries
        
        # Sort entries: directories first, then files
        dirs = []
        files = []
        for entry in entries:
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                dirs.append(entry + "/")
            else:
                files.append(entry)
        
        sorted_entries = sorted(dirs) + sorted(files)
        
        return sorted_entries
    except Exception as e:
        return []


async def view_tool(file_path: str, offset: Optional[int] = None, limit: Optional[int] = None) -> str:
    """Reads a file from the local filesystem.
    
    Args:
        file_path: The absolute path to the file to read
        offset: The line number to start reading from (optional)
        limit: The number of lines to read (optional)
    """
    try:
        # Make sure the path is absolute
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)
            
        if not os.path.exists(file_path):
            return f"File does not exist: {file_path}"
        
        if os.path.isdir(file_path):
            return f"Path is a directory, not a file: {file_path}"
        
        # Check if it's a binary file
        def is_binary(file_path):
            with open(file_path, 'rb') as file:
                chunk = file.read(1024)
                return b'\0' in chunk
        
        if is_binary(file_path):
            return f"[Binary file {file_path} not displayed]"
        
        # Read the file content
        with open(file_path, 'r', errors='replace') as file:
            lines = file.readlines()
        
        # Apply offset and limit
        offset = offset or 0
        if offset < 0:
            offset = 0
        
        if offset >= len(lines):
            return "File position is beyond the end of the file"
        
        if limit is None:
            limit = 2000
        
        # Truncate lines if needed
        lines = lines[offset:offset + limit]
        
        # Format lines with line numbers
        max_line_width = 2000
        formatted_lines = []
        for i, line in enumerate(lines, start=offset + 1):
            if len(line) > max_line_width:
                line = line[:max_line_width] + "... [truncated]"
            formatted_lines.append(f"{i:6d}\t{line.rstrip()}")
        
        result_message = "\n".join(formatted_lines) if formatted_lines else "[Empty file]"
        
        return result_message
    except Exception as e:
        return f"Error in ViewTool: {str(e)}"


async def edit_tool(file_path: str, old_string: str, new_string: str) -> str:
    """Edit a file by replacing one occurrence of old_string with new_string.
    
    Args:
        file_path: The absolute path to the file to modify
        old_string: The text to replace
        new_string: The text to replace it with
    """
    try:
        # Make sure the path is absolute
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)
        
        # Creating a new file
        if not old_string:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Write the new file
            with open(file_path, 'w') as file:
                file.write(new_string)
            
            return f"Created new file: {file_path}"
        
        # Editing an existing file
        if not os.path.exists(file_path):
            return f"File does not exist: {file_path}"
        
        if os.path.isdir(file_path):
            return f"Path is a directory, not a file: {file_path}"
        
        # Read the file content
        with open(file_path, 'r', encoding='utf-8', errors='replace') as file:
            content = file.read()
        
        # Check if old_string exists in the content
        if old_string not in content:
            return f"Could not find the text to replace in {file_path}"
        
        # Count occurrences to ensure uniqueness
        occurrences = content.count(old_string)
        if occurrences > 1:
            return f"Found {occurrences} occurrences of the text to replace in {file_path}. The text to replace must be unique within the file."
        
        # Replace the text
        new_content = content.replace(old_string, new_string, 1)
        
        # Write the modified content back to the file
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(new_content)
        
        return f"Successfully edited {file_path}"
    except Exception as e:
        return f"Error in EditTool: {str(e)}"


async def replace_tool(file_path: str, content: str) -> str:
    """Write content to a file, overwriting existing content if the file exists.
    
    Args:
        file_path: The absolute path to the file to write
        content: The content to write to the file
    """
    try:
        # Make sure the path is absolute
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Write the content to the file
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(content)
        
        return f"Successfully wrote to {file_path}"
    except Exception as e:
        return f"Error in ReplaceTool: {str(e)}"


async def bash_tool(command: str, timeout: Optional[int] = None) -> Dict:
    """Execute a bash command.
    
    Args:
        command: The command to execute
        timeout: Optional timeout in milliseconds (max 600000)
    """
    try:
        # Set default timeout (30 minutes)
        max_timeout = 1800  # 30 minutes in seconds
        if timeout:
            max_timeout = min(timeout / 1000, 600)  # Max 10 minutes
        
        # Check for banned commands
        banned_commands = [
            'alias', 'curl', 'curlie', 'wget', 'axel', 'aria2c', 'nc', 'telnet',
            'lynx', 'w3m', 'links', 'httpie', 'xh', 'http-prompt', 'chrome',
            'firefox', 'safari'
        ]
        
        for banned in banned_commands:
            if re.search(rf'\b{re.escape(banned)}\b', command):
                return {"error": f"Command '{banned}' is not allowed for security reasons"}
        
        # Execute the command
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=max_timeout)
            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')
            
            result = {
                "exitCode": process.returncode,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "output": stdout_str + (f"\n{stderr_str}" if stderr_str else "")
            }
            
            return result
        except asyncio.TimeoutError:
            process.terminate()
            return {"error": f"Command timed out after {max_timeout} seconds"}
            
    except Exception as e:
        return {"error": f"Error in BashTool: {str(e)}"}


async def notebook_read_tool(notebook_path: str) -> Dict:
    """Read a Jupyter notebook file.
    
    Args:
        notebook_path: The absolute path to the Jupyter notebook file
    """
    try:
        # Make sure the path is absolute
        if not os.path.isabs(notebook_path):
            notebook_path = os.path.abspath(notebook_path)
            
        if not os.path.exists(notebook_path):
            return {"error": f"Notebook does not exist: {notebook_path}"}
        
        if not notebook_path.endswith('.ipynb'):
            return {"error": f"File is not a Jupyter notebook: {notebook_path}"}
        
        # Read and parse the notebook
        with open(notebook_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
        
        return notebook
    except Exception as e:
        return {"error": f"Error in NotebookReadTool: {str(e)}"}


async def notebook_edit_tool(
    notebook_path: str, 
    cell_number: int,
    new_source: str, 
    cell_type: Optional[str] = None,
    edit_mode: Optional[str] = "replace"
) -> str:
    """Edit a cell in a Jupyter notebook.
    
    Args:
        notebook_path: The absolute path to the Jupyter notebook file
        cell_number: The index of the cell to edit (0-based)
        new_source: The new source for the cell
        cell_type: The type of the cell (code or markdown) (optional)
        edit_mode: The type of edit to make (replace, insert, delete) (optional)
    """
    try:
        # Make sure the path is absolute
        if not os.path.isabs(notebook_path):
            notebook_path = os.path.abspath(notebook_path)
            
        if not os.path.exists(notebook_path) and edit_mode != "insert":
            return f"Notebook does not exist: {notebook_path}"
        
        if not notebook_path.endswith('.ipynb'):
            return f"File is not a Jupyter notebook: {notebook_path}"
        
        # Read and parse the notebook if it exists
        if os.path.exists(notebook_path):
            with open(notebook_path, 'r', encoding='utf-8') as f:
                notebook = json.load(f)
        else:
            # Create a new notebook with default structure
            notebook = {
                "cells": [],
                "metadata": {
                    "kernelspec": {
                        "display_name": "Python 3",
                        "language": "python",
                        "name": "python3"
                    },
                    "language_info": {
                        "codemirror_mode": {
                            "name": "ipython",
                            "version": 3
                        },
                        "file_extension": ".py",
                        "mimetype": "text/x-python",
                        "name": "python",
                        "nbconvert_exporter": "python",
                        "pygments_lexer": "ipython3",
                        "version": "3.8.0"
                    }
                },
                "nbformat": 4,
                "nbformat_minor": 4
            }
        
        # Validate cell_number
        if cell_number < 0:
            return f"Cell number must be non-negative: {cell_number}"
        
        # Process based on edit_mode
        if edit_mode == "replace":
            if cell_number >= len(notebook.get('cells', [])):
                return f"Cell {cell_number} does not exist in the notebook"
            
            # Get the existing cell to determine its type if not specified
            existing_cell = notebook['cells'][cell_number]
            cell_type_to_use = cell_type or existing_cell.get('cell_type', 'code')
            
            # Update the cell
            notebook['cells'][cell_number]['source'] = new_source.split('\n')
            notebook['cells'][cell_number]['cell_type'] = cell_type_to_use
            
            # Reset outputs if it's a code cell
            if cell_type_to_use == 'code':
                notebook['cells'][cell_number]['outputs'] = []
                notebook['cells'][cell_number]['execution_count'] = None
            
            result_message = f"Replaced cell {cell_number}"
            
        elif edit_mode == "insert":
            if not cell_type:
                return "Cell type is required for insert mode"
            
            # Create a new cell
            new_cell = {
                "cell_type": cell_type,
                "source": new_source.split('\n'),
                "metadata": {}
            }
            
            # Add execution_count and outputs fields for code cells
            if cell_type == 'code':
                new_cell["outputs"] = []
                new_cell["execution_count"] = None
            
            # Insert the new cell at the specified position
            if cell_number > len(notebook.get('cells', [])):
                cell_number = len(notebook.get('cells', []))
            notebook.setdefault('cells', []).insert(cell_number, new_cell)
            
            result_message = f"Inserted new {cell_type} cell at position {cell_number}"
            
        elif edit_mode == "delete":
            if cell_number >= len(notebook.get('cells', [])):
                return f"Cell {cell_number} does not exist in the notebook"
            
            # Delete the cell
            deleted_cell = notebook['cells'].pop(cell_number)
            result_message = f"Deleted {deleted_cell.get('cell_type', 'unknown')} cell at position {cell_number}"
            
        else:
            return f"Invalid edit_mode: {edit_mode}"
        
        # Write the updated notebook
        with open(notebook_path, 'w', encoding='utf-8') as f:
            json.dump(notebook, f, indent=2)
        
        return result_message
    except Exception as e:
        return f"Error in NotebookEditTool: {str(e)}"


async def agent_tool(prompt: str) -> Dict:
    """Launch a new agent with search capabilities.
    
    Args:
        prompt: The task for the agent to perform
    """
    # In a real implementation, this would dispatch to a separate agent
    # For this demo, we'll just return a message explaining what would happen
    return {
        "taskCompleted": True,
        "agentResponse": f"I would search for '{prompt}' using the available tools"
    }


async def batch_tool(description: str, invocations: List[Dict[str, Any]]) -> Dict:
    """Run multiple tool operations in batch.
    
    Args:
        description: A short description of the batch operation
        invocations: List of tool invocations to execute in parallel
    """
    try:
        # Map of available tools
        tools_map = {
            "glob_tool": glob_tool,
            "grep_tool": grep_tool,
            "ls_tool": ls_tool,
            "view_tool": view_tool,
            "edit_tool": edit_tool,
            "replace_tool": replace_tool,
            "bash_tool": bash_tool,
            "notebook_read_tool": notebook_read_tool,
            "notebook_edit_tool": notebook_edit_tool,
            "agent_tool": agent_tool
        }
        
        # Function to execute one tool
        async def execute_tool(invocation):
            tool_name = invocation.get("tool_name")
            tool_input = invocation.get("input", {})
            
            if tool_name not in tools_map:
                return {
                    "tool_name": tool_name,
                    "status": "error",
                    "error": f"Tool not found: {tool_name}"
                }
            
            try:
                tool_fn = tools_map[tool_name]
                result = await tool_fn(**tool_input)
                
                return {
                    "tool_name": tool_name,
                    "status": "success",
                    "result": result
                }
            except Exception as e:
                return {
                    "tool_name": tool_name,
                    "status": "error",
                    "error": f"Error executing {tool_name}: {str(e)}"
                }
        
        # Execute all tool invocations in parallel
        tasks = []
        for invocation in invocations:
            tasks.append(execute_tool(invocation))
        
        results = await asyncio.gather(*tasks)
        
        return {
            "description": description,
            "results": results
        }
    except Exception as e:
        return {"error": f"Error in BatchTool: {str(e)}"}


TOOLS = {
    "glob_tool": glob_tool,
    "grep_tool": grep_tool,
    "ls_tool": ls_tool,
    "view_tool": view_tool,
    "edit_tool": edit_tool,
    "replace_tool": replace_tool,
    "bash_tool": bash_tool,
    "notebook_read_tool": notebook_read_tool,
    "notebook_edit_tool": notebook_edit_tool,
    "agent_tool": agent_tool,
    "batch_tool": batch_tool
}

async def main():
    result = await glob_tool(pattern="**/*.py")
    print(f"glob_tool result: {result}")
    
    batch_result = await batch_tool(
        description="Find Python files and list directory",
        invocations=[
            {"tool_name": "glob_tool", "input": {"pattern": "**/*.py"}},
            {"tool_name": "ls_tool", "input": {"path": os.getcwd()}}
        ]
    )
    print(f"batch_tool result: {batch_result}")


if __name__ == "__main__":
    asyncio.run(main())
