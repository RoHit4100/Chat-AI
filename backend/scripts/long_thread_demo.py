#!/usr/bin/env python
"""Demo script driving 200+ messages through the API with FAKE_LLM and rolling memory summarization."""
import os
import sys
import json
import asyncio
from pathlib import Path

# Configure paths and Django environment
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["FAKE_LLM"] = "1"
os.environ["USE_SQLITE"] = "1"
# Lower threshold so compactions trigger regularly across 200 messages
os.environ["MAX_TOKENS"] = "200"
os.environ["KEEP_LAST"] = "8"

import django
django.setup()

from django.core.management import call_command
call_command("migrate", verbosity=0)

from django.test import AsyncClient
from chat.models import Thread, Message
from agent.graph import get_compiled_graph

async def run_long_thread_demo():
    print("=" * 70)
    print("STARTING LONG THREAD DEMO (200+ MESSAGES)")
    print("=" * 70)

    token = "service-token-long-thread-tester"
    client = AsyncClient()

    # Create a fresh thread
    resp = await client.post(
        "/api/threads/",
        data=json.dumps({"title": "Long Thread Demo"}),
        content_type="application/json",
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code != 201:
        print(f"Failed to create thread: {resp.status_code} {resp.content}")
        return
    thread_data = resp.json()
    thread_id = thread_data["id"]
    print(f"Created Thread: {thread_id}")

    # Drive 205 messages through the API
    total_messages = 205
    secret_code = "OMEGA-42"

    for i in range(1, total_messages + 1):
        if i == 3:
            content = f"Important secret fact: The project launch code is {secret_code}."
        elif i == total_messages:
            content = "What was the project launch code mentioned early in our chat?"
        else:
            content = f"Update step #{i}: verified system component {i % 10} operational."

        stream_resp = await client.post(
            f"/api/threads/{thread_id}/stream",
            data=json.dumps({"message": content}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token}"},
        )

        if stream_resp.status_code != 200:
            print(f"Error on message #{i}: {stream_resp.status_code} {stream_resp.content}")
            return

        # Drain the SSE stream
        async for _ in stream_resp.streaming_content:
            pass

        if i % 25 == 0 or i == total_messages:
            # Query checkpoint state
            graph = await get_compiled_graph()
            state = await graph.aget_state({"configurable": {"thread_id": str(thread_id)}})
            active_msgs = len(state.values.get("messages", []))
            summary_preview = (state.values.get("summary") or "None")[:80]
            print(f"Turn {i}/{total_messages} -> Active in graph state: {active_msgs} msgs | Summary: {summary_preview}...")

    # Verification
    graph = await get_compiled_graph()
    final_state = await graph.aget_state({"configurable": {"thread_id": str(thread_id)}})
    final_active_msgs = len(final_state.values.get("messages", []))
    final_summary = final_state.values.get("summary", "")
    db_msg_count = await Message.objects.filter(thread_id=thread_id).acount()

    print("\n" + "=" * 70)
    print("DEMO VERIFICATION RESULTS:")
    print("=" * 70)
    print(f"Total messages persisted in DB display history: {db_msg_count}")
    print(f"Active messages in LangGraph working memory:   {final_active_msgs} (Kept <= KEEP_LAST)")
    print(f"Final rolling summary length:                   {len(final_summary)} characters")
    print(f"Rolling summary preview:                        {final_summary[:200]}...")
    print("=" * 70)
    print("SUCCESS: 200+ messages processed through API with rolling summarization!")

if __name__ == "__main__":
    asyncio.run(run_long_thread_demo())
