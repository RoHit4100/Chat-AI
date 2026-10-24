from langchain_core.tools import tool

@tool
def search_web(query: str) -> str:
    """Search the web for up-to-date information on a given topic."""
    return f"Search results for: {query}. (Simulated placeholder output)"

@tool
def inspect_file(filename: str) -> str:
    """Inspect and retrieve summary information for an uploaded file."""
    return f"File inspection results for '{filename}': Valid structure, verified content."

@tool
def failing_tool(query: str = "fail") -> str:
    """A tool designed to raise an error to verify error handling and loop termination."""
    raise ValueError(f"Simulated tool error executing query: {query}")

# Registered tools for agent node
ALL_TOOLS = [search_web, inspect_file, failing_tool]
