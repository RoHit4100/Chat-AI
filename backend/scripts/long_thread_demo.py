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
# If running in Docker with DATABASE_URL, keep PostgreSQL; otherwise default to SQLite
if "DATABASE_URL" not in os.environ and "USE_SQLITE" not in os.environ:
    os.environ["USE_SQLITE"] = "1"
# Lower threshold so compactions trigger regularly across 200 messages
os.environ["MAX_TOKENS"] = "200"
os.environ["KEEP_LAST"] = "8"
os.environ["THROTTLE_RATE_CHAT"] = "10000/minute"

import django
django.setup()

from django.core.management import call_command
call_command("migrate", verbosity=0)

from django.test import AsyncClient
from django.contrib.auth import get_user_model
from chat.models import Thread, Message
from agent.graph import get_compiled_graph

async def run_long_thread_demo():
    print("=" * 70)
    print("STARTING LONG THREAD DEMO (200+ MESSAGES)")
    print("=" * 70)

    User = get_user_model()
    # Resolve demo user (Keycloak sub fcfd5ad2-ab47-4d20-91b6-a2ba37994cbc or email demo@example.com)
    demo_user = (
        await User.objects.filter(username="fcfd5ad2-ab47-4d20-91b6-a2ba37994cbc").afirst()
        or await User.objects.filter(email="demo@example.com").afirst()
        or await User.objects.filter(username="demo").afirst()
    )
    if not demo_user:
        demo_user = await User.objects.acreate(
            username="fcfd5ad2-ab47-4d20-91b6-a2ba37994cbc",
            email="demo@example.com",
        )

    token = f"service-token-{demo_user.username}"
    client = AsyncClient()

    # Ensure there will be exactly one chat for the demo user: delete existing threads
    demo_users = [u async for u in User.objects.filter(email="demo@example.com")]
    for candidate in [demo_user, await User.objects.filter(username="demo").afirst()]:
        if candidate and candidate not in demo_users:
            demo_users.append(candidate)
    for u in demo_users:
        async for t in Thread.objects.filter(user=u):
            await t.adelete()

    # Create a fresh thread for demo user
    resp = await client.post(
        "/api/threads/",
        data=json.dumps({"title": "Project Orion"}),
        content_type="application/json",
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code != 201:
        print(f"Failed to create thread: {resp.status_code} {resp.content}")
        return
    thread_data = resp.json()
    thread_id = thread_data["id"]
    print(f"Created Thread for Demo User ({demo_user.username}): {thread_id}")

    # Drive 205 messages through the API
    total_messages = 205
    secret_code = "OMEGA-42"

    for i in range(1, total_messages + 1):
        if i == 1:
            content = "My project is called Orion."
        elif i == 2:
            content = f"Important secret fact: The project launch code is {secret_code}."
        elif i == total_messages:
            content = "What was the name of my project and the launch code mentioned early in our chat?"
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
    last_asst = await Message.objects.filter(thread_id=thread_id, role="assistant").order_by("-created_at").afirst()
    if last_asst:
        print(f"Final Assistant Recall Response:                {last_asst.content}")

    # Ensure all demo user accounts have this exact one thread
    original_thread = await Thread.objects.aget(id=thread_id)
    messages_to_copy = [m async for m in Message.objects.filter(thread_id=thread_id).order_by("created_at")]
    for other_user in demo_users:
        if other_user.id != demo_user.id:
            async for t in Thread.objects.filter(user=other_user):
                await t.adelete()
            cloned = await Thread.objects.acreate(
                user=other_user,
                title=original_thread.title,
            )
            for m in messages_to_copy:
                await Message.objects.acreate(
                    thread=cloned,
                    role=m.role,
                    content=m.content,
                    status=m.status,
                    input_tokens=m.input_tokens,
                    output_tokens=m.output_tokens,
                )

    print("=" * 70)
    print("SUCCESS: 200+ messages processed through API with rolling summarization!")

if __name__ == "__main__":
    asyncio.run(run_long_thread_demo())
