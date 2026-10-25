import os
import sys
import asyncio
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
import django
django.setup()

from agent.graph import get_compiled_graph

async def main():
    thread_id = sys.argv[1] if len(sys.argv) > 1 else "d029a3d6-33b8-47d0-b531-6da46da8d6c2"
    graph = await get_compiled_graph()
    state = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    print("=== CHECKPOINT STATE FOR THREAD:", thread_id, "===")
    messages = state.values.get("messages", [])
    print(f"Total messages in state: {len(messages)}")
    for i, m in enumerate(messages):
        tc = getattr(m, "tool_calls", None)
        print(f"\n--- Message {i+1}: {type(m).__name__} (tool_calls={tc}) ---")
        print(repr(m.content)[:500])

if __name__ == "__main__":
    asyncio.run(main())
