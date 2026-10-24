from langgraph.graph import StateGraph, START, END
from agent.state import AgentState
from agent.nodes import (
    prepare_node,
    agent_node,
    tools_node,
    summarize_node,
    should_continue,
)
from agent.checkpointer import get_checkpointer

def build_chat_graph(checkpointer=None):
    """Build and compile the LangGraph agent state machine."""
    workflow = StateGraph(AgentState)

    # Define nodes: prepare, agent, tools, summarize
    workflow.add_node("prepare", prepare_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tools_node)
    workflow.add_node("summarize", summarize_node)

    # Define edges: START -> prepare -> agent
    workflow.add_edge(START, "prepare")
    workflow.add_edge("prepare", "agent")

    # Conditional routing after agent execution
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "summarize": "summarize",
        },
    )

    # Loop tools back to agent; terminate after summarize
    workflow.add_edge("tools", "agent")
    workflow.add_edge("summarize", END)

    return workflow.compile(checkpointer=checkpointer)

async def get_compiled_graph():
    """Return compiled chat graph configured with active checkpointer."""
    checkpointer = await get_checkpointer()
    return build_chat_graph(checkpointer=checkpointer)
