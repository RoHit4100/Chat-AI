from langgraph.graph import MessagesState

class AgentState(MessagesState):
    """LangGraph agent state containing messages, rolling summary, file manifest, and consecutive tool errors."""
    summary: str
    manifest: list
    tool_errors: int
