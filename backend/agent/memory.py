import os
import re
from typing import Any, List
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)
from langchain_core.runnables import RunnableConfig
from agent.state import AgentState
from agent.llm import get_llm

# Regex patterns to detect and strip base64 data and large encoded blobs
BASE64_IMAGE_PATTERN = re.compile(r"data:image\/[a-zA-Z0-9.-]+;base64,[A-Za-z0-9+/=]+", re.IGNORECASE)
LARGE_BLOB_PATTERN = re.compile(r"[A-Za-z0-9+/=]{300,}")

def sanitize_tool_output(content: str, max_chars: int = 2000) -> str:
    """Never store base64 images, full file text or large tool outputs in graph state; truncate before entering state."""
    if not isinstance(content, str):
        content = str(content)

    # Strip base64 image data URIs
    content = BASE64_IMAGE_PATTERN.sub("[base64 image omitted]", content)

    # Strip raw large base64 or binary text blobs
    content = LARGE_BLOB_PATTERN.sub("[large raw data omitted]", content)

    # Truncate tool output length
    if len(content) > max_chars:
        content = content[:max_chars] + "\n... [tool output truncated]"

    return content

def count_message_tokens(messages: List[BaseMessage]) -> int:
    """Estimate token count across a list of messages using metadata or heuristic (~4 chars/token)."""
    total = 0
    for m in messages:
        usage = getattr(m, "usage_metadata", None)
        if usage and "total_tokens" in usage:
            total += usage["total_tokens"]
        elif usage and ("input_tokens" in usage or "output_tokens" in usage):
            total += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        else:
            text = str(getattr(m, "content", ""))
            total += max(1, len(text) // 4) + 4
    return total

async def summarize_node(state: AgentState, config: RunnableConfig | None = None) -> dict:
    """Summarize older messages when total tokens exceed MAX_TOKENS, keeping KEEP_LAST messages verbatim."""
    max_tokens = int(os.getenv("MAX_TOKENS", "6000"))
    keep_last = int(os.getenv("KEEP_LAST", "8"))

    messages = state.get("messages", [])
    if not messages:
        return {}

    total_tokens = count_message_tokens(messages)

    # If within threshold or fewer messages than KEEP_LAST, no compaction needed
    if total_tokens <= max_tokens or len(messages) <= keep_last:
        return {}

    # Separate messages: older messages to summarize vs. recent messages to keep verbatim
    messages_to_summarize = messages[:-keep_last]
    messages_to_keep = messages[-keep_last:]

    if not messages_to_summarize:
        return {}

    # Format text of messages to summarize
    conversation_lines = []
    for m in messages_to_summarize:
        role = getattr(m, "type", "message")
        content = str(getattr(m, "content", ""))
        conversation_lines.append(f"{role}: {content}")
    conversation_text = "\n".join(conversation_lines)

    existing_summary = state.get("summary", "")

    # Generate updated merged summary with LLM
    if os.getenv("FAKE_LLM", "0").lower() in ("1", "true"):
        if existing_summary:
            updated_summary = f"{existing_summary} | Merged: {len(messages_to_summarize)} older messages ({conversation_lines[0][:60]}...)"
        else:
            updated_summary = f"Summary: {len(messages_to_summarize)} older messages ({conversation_lines[0][:60]}...)"
    else:
        llm = get_llm()
        prompt = (
            "You are an AI maintaining a concise rolling summary of a conversation.\n"
            f"Existing summary:\n{existing_summary or 'None'}\n\n"
            f"New messages to consolidate:\n{conversation_text}\n\n"
            "Produce an updated, cohesive summary integrating the new points into the existing summary."
        )
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        updated_summary = str(response.content).strip()

    # Create RemoveMessage operations for older messages
    remove_ops = [RemoveMessage(id=m.id) for m in messages_to_summarize if getattr(m, "id", None)]

    return {
        "summary": updated_summary,
        "messages": remove_ops,
    }
