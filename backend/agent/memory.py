import os
import re
from typing import Any, List
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
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

def sanitize_message_history(messages: List[BaseMessage]) -> tuple[List[BaseMessage], List[str]]:
    """Ensure message sequence strictly adheres to LLM provider requirements (OpenAI, Anthropic, Google).
    Rules enforced:
    1. A ToolMessage must be immediately preceded by an AIMessage with tool_calls.
    2. Every ToolMessage must correspond to an expected tool_call_id from the parent AIMessage.
    3. Any orphaned ToolMessage is converted into context or dropped, and its ID is returned for checkpoint cleanup.
    4. Any AIMessage with tool_calls must have all tool_calls answered before another Human/AI message; missing ones are synthesized.

    Returns:
        (sanitized_messages, orphaned_message_ids)
    """
    if not messages:
        return [], []

    valid_messages: List[BaseMessage] = []
    orphaned_ids: List[str] = []

    for msg in messages:
        if isinstance(msg, ToolMessage):
            # Find the parent AIMessage among preceding messages
            last_ai = None
            for prev in reversed(valid_messages):
                if isinstance(prev, AIMessage):
                    last_ai = prev
                    break
                elif not isinstance(prev, ToolMessage):
                    break

            is_valid = False
            if last_ai:
                tool_calls = getattr(last_ai, "tool_calls", []) or []
                expected_ids = {tc.get("id") for tc in tool_calls if isinstance(tc, dict)}
                msg_tool_id = getattr(msg, "tool_call_id", None)
                if msg_tool_id and msg_tool_id in expected_ids:
                    is_valid = True

            if is_valid:
                valid_messages.append(msg)
            else:
                msg_id = getattr(msg, "id", None)
                if msg_id:
                    orphaned_ids.append(str(msg_id))
                content = str(getattr(msg, "content", "")).strip()
                if content:
                    valid_messages.append(HumanMessage(content=f"[Context from prior tool output]: {content}"))

        elif isinstance(msg, (AIMessage, HumanMessage)):
            # If previous messages include an AIMessage with tool_calls, verify all tool_calls were answered
            last_ai = None
            answered_ids = set()
            for prev in reversed(valid_messages):
                if isinstance(prev, ToolMessage):
                    answered_ids.add(getattr(prev, "tool_call_id", None))
                elif isinstance(prev, AIMessage):
                    last_ai = prev
                    break
                else:
                    break

            if last_ai:
                tool_calls = getattr(last_ai, "tool_calls", []) or []
                for tc in tool_calls:
                    tc_id = tc.get("id") if isinstance(tc, dict) else None
                    if tc_id and tc_id not in answered_ids:
                        valid_messages.append(
                            ToolMessage(
                                content="Tool execution completed.",
                                tool_call_id=tc_id,
                            )
                        )
            valid_messages.append(msg)
        else:
            valid_messages.append(msg)

    return valid_messages, orphaned_ids

def count_conversation_tokens(messages: List[BaseMessage]) -> int:
    """Count tokens across only user and assistant conversation messages (not file text or tool output)."""
    total = 0
    for m in messages:
        # Strictly count only HumanMessage and AIMessage conversation messages
        if not isinstance(m, (HumanMessage, AIMessage)):
            continue
        usage = getattr(m, "usage_metadata", None)
        if usage and "total_tokens" in usage:
            total += usage["total_tokens"]
        elif usage and ("input_tokens" in usage or "output_tokens" in usage):
            total += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        else:
            text = str(getattr(m, "content", ""))
            total += max(1, len(text) // 4) + 4
    return total

count_message_tokens = count_conversation_tokens

async def summarize_node(state: AgentState, config: RunnableConfig | None = None) -> dict:
    """Summarize older messages when total conversation tokens exceed MAX_TOKENS (default 6000)."""
    max_tokens = int(os.getenv("MAX_TOKENS", "6000"))
    keep_last = int(os.getenv("KEEP_LAST", "8"))

    messages = state.get("messages", [])
    if not messages:
        return {}

    # Count only user and assistant conversation messages
    conversation_msgs = [m for m in messages if isinstance(m, (HumanMessage, AIMessage))]
    total_tokens = count_conversation_tokens(messages)

    # If within threshold or 5 or fewer conversation messages, no compaction needed
    if total_tokens <= max_tokens or len(conversation_msgs) <= 5 or len(messages) <= keep_last:
        return {}

    # Separate messages safely: never split an AIMessage(tool_calls) from its ToolMessages
    split_idx = max(0, len(messages) - keep_last)
    while split_idx > 0 and isinstance(messages[split_idx], ToolMessage):
        split_idx -= 1
    while split_idx > 0 and isinstance(messages[split_idx], AIMessage) and getattr(messages[split_idx], "tool_calls", None):
        split_idx -= 1

    messages_to_summarize = messages[:split_idx]
    messages_to_keep = messages[split_idx:]

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
