import os
import sys
import django

# Setup Django environment
sys.path.insert(0, "/app" if os.path.exists("/app") else str(os.path.abspath("backend")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth.models import User
from chat.models import Thread, UploadedFile
from filesvc.service import FileService
from filesvc.storage import storage
from agent.tools import read_file
from agent.nodes import agent_node
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

def reproduce():
    print("=" * 60)
    print("REPRODUCING IMAGE READING ISSUE")
    print("=" * 60)

    user, _ = User.objects.get_or_create(username="repro_user")
    thread = Thread.objects.create(user=user, title="Image Repro Thread")

    img_path = "/app/sample_files/traffic_chart.png"
    if not os.path.exists(img_path):
        img_path = "backend/sample_files/traffic_chart.png"

    print(f"1. Reading sample image: {img_path}")
    with open(img_path, "rb") as f:
        file_bytes = f.read()

    # Save to storage and create UploadedFile
    dest_path, total_size = storage.save_raw(file_bytes, ".png")
    uf = UploadedFile.objects.create(
        thread=thread,
        name="traffic_chart.png",
        mime="image/png",
        size=total_size,
        path=dest_path,
        status="uploaded",
    )

    # Parse file
    FileService().parse_file_sync(uf.id)
    uf.refresh_from_db()
    print(f"UploadedFile ID: {uf.id}, Status: {uf.status}, Summary: {uf.summary}")

    # Step 2: Call read_file
    print("\n2. Executing read_file tool...")
    config = {"configurable": {"thread_id": str(thread.id), "user_id": str(user.id)}}
    tool_result = read_file.invoke({"file_id": str(uf.id)}, config=config)
    print("=== WHAT read_file RETURNS ===")
    print(tool_result)
    print("===============================")

    # Step 3: Run agent with prompt
    user_prompt = "Describe what this image shows, including the values."
    print(f"\n3. Asking model: '{user_prompt}'")
    
    # Simulate LLM call in agent_node
    # State has user message, then agent tool call to read_file, then tool message
    messages = [
        HumanMessage(content=user_prompt),
        AIMessage(
            content="",
            tool_calls=[{"name": "read_file", "args": {"file_id": str(uf.id)}, "id": "call_1"}],
        ),
        ToolMessage(content=tool_result, tool_call_id="call_1"),
    ]

    import asyncio
    state = {
        "messages": messages,
        "manifest": [{
            "id": str(uf.id),
            "name": uf.name,
            "mime": uf.mime,
            "size": uf.size,
            "status": uf.status,
            "summary": uf.summary,
            "kind": "uploaded",
        }],
        "summary": "",
        "tool_errors": 0,
    }

    result = asyncio.run(agent_node(state, config=config))
    last_msg = result["messages"][-1]
    print("\n=== WHAT IS SENT TO / RETURNED BY THE MODEL ===")
    print("Model response:")
    print(last_msg.content)
    print("================================================")

if __name__ == "__main__":
    reproduce()
