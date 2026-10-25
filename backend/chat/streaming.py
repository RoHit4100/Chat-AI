import asyncio
import json
import logging
import os
import re
from typing import AsyncIterator, Any
from langchain_core.messages import HumanMessage, RemoveMessage, AIMessage, AIMessageChunk
from agent.graph import get_compiled_graph
from chat.models import Thread, Message, GeneratedFile

logger = logging.getLogger(__name__)

# Active streaming registry to ensure only one stream per thread at a time
_active_streams: set[str] = set()
_active_streams_lock = asyncio.Lock()

async def acquire_stream_lock(thread_id: str) -> bool:
    """Attempt to acquire stream lock for thread. Returns False if already active."""
    async with _active_streams_lock:
        if thread_id in _active_streams:
            return False
        _active_streams.add(thread_id)
        return True

async def release_stream_lock(thread_id: str):
    """Release streaming lock for thread."""
    async with _active_streams_lock:
        _active_streams.discard(thread_id)

def format_sse(event: str, data: dict) -> str:
    """Format SSE event frame with event name and JSON data."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

def estimate_tokens(text: str) -> int:
    """Estimate token count as a fallback heuristic (1 token per 4 characters)."""
    return max(1, len(text) // 4) if text else 0

def extract_text_from_chunk_content(content: Any) -> str:
    """Extract plain text string from AIMessageChunk content (which can be str or list of dicts/blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces = []
        for item in content:
            if isinstance(item, str):
                pieces.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text" and "text" in item:
                    pieces.append(str(item["text"]))
                elif "text" in item:
                    pieces.append(str(item["text"]))
            elif hasattr(item, "text"):
                pieces.append(str(getattr(item, "text", "")))
        return "".join(pieces)
    return ""

async def stream_chat_turn(
    thread: Thread,
    user_prompt: str | None = None,
    is_regenerate: bool = False,
    existing_assistant_message: Message | None = None,
) -> AsyncIterator[str]:
    """Execute LangGraph astream and emit SSE events, persisting the result in finally."""
    thread_id = str(thread.id)
    recursion_limit = int(os.getenv("GRAPH_RECURSION_LIMIT", "25"))
    config = {
        "configurable": {"thread_id": thread_id, "user_id": str(thread.user_id)},
        "recursion_limit": recursion_limit,
    }
    graph = await get_compiled_graph()

    collected_content = ""
    status = "stopped"
    input_tokens = 0
    output_tokens = 0

    try:
        if is_regenerate:
            # Prune previous assistant turn from the checkpoint state
            state = await graph.aget_state(config)
            has_human_in_state = False
            if state and state.values.get("messages"):
                remove_list = []
                for m in reversed(state.values["messages"]):
                    if isinstance(m, HumanMessage):
                        has_human_in_state = True
                        break
                    remove_list.append(RemoveMessage(id=m.id))
                if remove_list:
                    await graph.aupdate_state(config, {"messages": remove_list, "tool_errors": 0})

            if has_human_in_state:
                # Checkpoint contains conversation up to last user message; trigger graph from START
                input_data = {}
            else:
                # Checkpoint empty or pruned; rebuild conversation history from DB up to last assistant message
                rebuilt_messages = []
                if existing_assistant_message:
                    db_msgs = [
                        m async for m in Message.objects.filter(
                            thread=thread,
                            created_at__lt=existing_assistant_message.created_at,
                        ).order_by("created_at")
                    ]
                    for dm in db_msgs:
                        if dm.role == "user":
                            rebuilt_messages.append(HumanMessage(content=dm.content))
                        elif dm.role == "assistant":
                            rebuilt_messages.append(AIMessage(content=dm.content))
                if not rebuilt_messages and user_prompt:
                    rebuilt_messages.append(HumanMessage(content=user_prompt))

                input_data = {"messages": rebuilt_messages} if rebuilt_messages else {}
        else:
            input_data = {"messages": [HumanMessage(content=user_prompt)]}

        yield format_sse("status", {"node": "prepare", "status": "starting"})

        # Async generator consumption with 15s heartbeat
        stream_iter = aiter(graph.astream(input_data, config=config, stream_mode=["messages", "updates"]))

        while True:
            try:
                chunk = await asyncio.wait_for(anext(stream_iter), timeout=15.0)
            except TimeoutError:
                yield ": heartbeat\n\n"
                continue
            except StopAsyncIteration:
                break

            mode, data = chunk

            if mode == "messages":
                chunk_msg, metadata = data
                node_name = (metadata or {}).get("langgraph_node")

                # Strictly emit token events ONLY for AIMessageChunk from the "agent" node
                # Never stream ToolMessage content or output from summarize node
                if node_name == "agent" and isinstance(chunk_msg, AIMessageChunk):
                    raw_content = getattr(chunk_msg, "content", "")
                    text = extract_text_from_chunk_content(raw_content)
                    if text:
                        collected_content += text
                        yield format_sse("token", {"content": text})

                # Emit status event when model invokes a tool (never as token)
                tool_calls = getattr(chunk_msg, "tool_calls", None)
                if tool_calls:
                    for tc in tool_calls:
                        name = tc.get("name")
                        yield format_sse("status", {"node": "tools", "status": f"calling tool {name}..."})
                        if name == "read_file":
                            yield format_sse("status", {"node": "tools", "status": "Reading file..."})
                        elif name == "generate_file":
                            yield format_sse("status", {"node": "tools", "status": "Generating and verifying file..."})
                        elif name == "inspect_file":
                            yield format_sse("status", {"node": "tools", "status": "Inspecting file metadata..."})
                        elif name == "web_search":
                            yield format_sse("status", {"node": "tools", "status": "Searching the web..."})
                        elif name == "browse_web_page":
                            yield format_sse("status", {"node": "tools", "status": "Browsing web page..."})

                # Emit status when tool call chunks start arriving for generate_file
                tc_chunks = getattr(chunk_msg, "tool_call_chunks", None) or []
                for tcc in tc_chunks:
                    if tcc.get("name") == "generate_file":
                        yield format_sse("status", {"node": "agent", "status": "Writing file specification..."})

                # Extract token usage metadata from chunk if provided by LLM
                usage = getattr(chunk_msg, "usage_metadata", None)
                if usage:
                    input_tokens = usage.get("input_tokens", input_tokens)
                    output_tokens = usage.get("output_tokens", output_tokens)

            elif mode == "updates":
                for node_name, updates in data.items():
                    if node_name == "summarize":
                        yield format_sse("status", {"node": "summarize", "status": "Conversation summary updated"})
                    elif node_name == "tools":
                        # Check messages for specific tool completions
                        tool_msgs = updates.get("messages", []) if isinstance(updates, dict) else []
                        gen_success = any("Successfully generated" in str(getattr(m, "content", "")) for m in tool_msgs)
                        ver_error = any("Verification error" in str(getattr(m, "content", "")) for m in tool_msgs)
                        if gen_success:
                            yield format_sse("status", {"node": "tools", "status": "File generated and verified"})
                        elif ver_error:
                            yield format_sse("status", {"node": "tools", "status": "File verification failed, fixing specification..."})
                        else:
                            yield format_sse("status", {"node": "tools", "status": "Tool execution completed"})
                    else:
                        yield format_sse("status", {"node": node_name, "status": "completed"})

                    # Emit file event when file generation tool completes
                    if node_name == "tools" and isinstance(updates, dict):
                        for m in updates.get("messages", []):
                            content = str(getattr(m, "content", ""))
                            if "Successfully generated" in content:
                                match = re.search(r"\(id:\s*(\d+),\s*version:\s*(\d+)\)", content)
                                if match:
                                    file_id = int(match.group(1))
                                    gf = await GeneratedFile.objects.filter(id=file_id).afirst()
                                    if gf:
                                        yield format_sse("file", {
                                            "id": gf.id,
                                            "name": gf.name,
                                            "kind": gf.kind,
                                            "version": gf.version,
                                            "download_url": f"/api/generated/{gf.id}/download/",
                                        })

        status = "complete"
        yield format_sse("done", {"status": "complete"})

    except asyncio.CancelledError:
        status = "stopped"
        raise
    except Exception as exc:
        status = "failed"
        logger.exception("Streaming execution encountered an error: %s", exc)
        yield format_sse("error", {"error": str(exc)})
    finally:
        # Fallback: if collected_content is empty, retrieve final text from graph state
        if not collected_content:
            try:
                state_snapshot = await graph.aget_state(config)
                if state_snapshot and state_snapshot.values.get("messages"):
                    for m in reversed(state_snapshot.values["messages"]):
                        if isinstance(m, AIMessage):
                            fb_text = extract_text_from_chunk_content(m.content)
                            if fb_text:
                                collected_content = fb_text
                                break
            except Exception:
                pass

        # Save only the final assistant text (never tool or summarize outputs)
        final_text = collected_content.strip()
        final_input_tokens = input_tokens or estimate_tokens(user_prompt or "")
        final_output_tokens = output_tokens or estimate_tokens(final_text)

        if is_regenerate and existing_assistant_message:
            existing_assistant_message.content = final_text
            existing_assistant_message.status = status
            existing_assistant_message.input_tokens = final_input_tokens
            existing_assistant_message.output_tokens = final_output_tokens
            await existing_assistant_message.asave()
        else:
            await Message.objects.acreate(
                thread=thread,
                role="assistant",
                content=final_text,
                status=status,
                input_tokens=final_input_tokens,
                output_tokens=final_output_tokens,
            )

        # Prune older checkpoint snapshots to prevent database bloat
        from agent.checkpointer import aprune_thread_checkpoints
        await aprune_thread_checkpoints(thread_id, keep_last=10)

        # Release thread concurrency lock
        await release_stream_lock(thread_id)
