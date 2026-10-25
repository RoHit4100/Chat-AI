import asyncio
import json
import os
import sys
from django.contrib.auth import get_user_model

# Ensure Django is initialized
import django
sys.path.insert(0, "/app" if os.path.exists("/app") else str(os.path.abspath("backend")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from chat.models import Thread, Message, UploadedFile
from filesvc.service import file_service
from filesvc.storage import storage
from chat.streaming import stream_chat_turn
from asgiref.sync import sync_to_async

User = get_user_model()

async def run_chat_and_collect(thread, user_prompt: str):
    print(f"\n--- User: {user_prompt} ---")
    tokens = []
    statuses = []
    async for sse_chunk in stream_chat_turn(thread, user_prompt):
        for line in sse_chunk.split("\n"):
            if line.startswith("data: "):
                try:
                    payload = json.loads(line[6:])
                    if "content" in payload:
                        tokens.append(payload["content"])
                        print(payload["content"], end="", flush=True)
                    if "status" in payload:
                        statuses.append(payload["status"])
                except Exception:
                    pass
    print("\n")
    full_response = "".join(tokens)
    return full_response, statuses

async def verify_image_reading():
    user, _ = await User.objects.aget_or_create(username="vision_tester", defaults={"email": "vision@example.com"})

    # =========================================================================
    # Test 1: traffic_chart.png
    # =========================================================================
    print("\n========================================================")
    print("TEST 1: Uploading and reading traffic_chart.png with real LLM")
    print("========================================================")

    chart_paths = [
        "/app/sample_files/traffic_chart.png",
        "/app/sample_files/sample_files/traffic_chart.png",
    ]
    chart_path = next((p for p in chart_paths if os.path.exists(p)), None)
    if not chart_path:
        print("ERROR: traffic_chart.png not found!")
        sys.exit(1)

    thread1 = await Thread.objects.acreate(user=user, title="Traffic Chart Test")

    with open(chart_path, "rb") as f:
        file_bytes = f.read()

    saved_path, file_size = storage.save_raw(file_bytes, extension="png")
    uf1 = await UploadedFile.objects.acreate(
        thread=thread1,
        name="traffic_chart.png",
        mime="image/png",
        size=file_size,
        path=saved_path,
        status="uploaded",
    )
    # Parse file synchronously
    await sync_to_async(file_service.parse_file_sync)(uf1.id)
    await uf1.arefresh_from_db()
    print(f"Uploaded and parsed file_id={uf1.id}, status={uf1.status}")
    print(f"Manifest summary: {uf1.summary}")

    prompt1 = "Describe what this image shows, including the values."
    res1, statuses1 = await run_chat_and_collect(thread1, prompt1)

    print("\nValidating Test 1 assertions:")
    checks1 = {
        "Website Traffic Sources title": "traffic" in res1.lower(),
        "Organic search 42,000": "42,000" in res1 or "42000" in res1,
        "Direct 28,500": "28,500" in res1 or "28500" in res1,
        "Referral 15,200": "15,200" in res1 or "15200" in res1,
        "Social media 9,800": "9,800" in res1 or "9800" in res1,
        "Email 6,400": "6,400" in res1 or "6400" in res1,
    }

    all_passed1 = True
    for name, passed in checks1.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_passed1 = False
        print(f"  [{status}] {name}")

    # Check database messages for base64
    db_messages1 = [m async for m in Message.objects.filter(thread=thread1)]
    has_base64 = any("data:image" in m.content or ";base64," in m.content for m in db_messages1)
    print(f"  [{'PASS' if not has_base64 else 'FAIL'}] No base64 in database messages")

    # =========================================================================
    # Test 2: screenshot_with_text.png
    # =========================================================================
    print("\n========================================================")
    print("TEST 2: Screenshot with text")
    print("========================================================")

    ss_path = "/app/sample_files/screenshot_with_text.png"
    thread2 = await Thread.objects.acreate(user=user, title="Screenshot Test")

    with open(ss_path, "rb") as f:
        ss_bytes = f.read()

    saved_ss_path, ss_size = storage.save_raw(ss_bytes, extension="png")
    uf2 = await UploadedFile.objects.acreate(
        thread=thread2,
        name="screenshot_with_text.png",
        mime="image/png",
        size=ss_size,
        path=saved_ss_path,
        status="uploaded",
    )
    await sync_to_async(file_service.parse_file_sync)(uf2.id)
    await uf2.arefresh_from_db()
    print(f"Uploaded and parsed file_id={uf2.id}, status={uf2.status}")
    print(f"Manifest summary: {uf2.summary}")

    prompt2 = "What services, metrics, and log events are shown in this dashboard screenshot?"
    res2, statuses2 = await run_chat_and_collect(thread2, prompt2)

    checks2 = {
        "API Gateways mentioned": "api gateway" in res2.lower(),
        "Database Cluster mentioned": "database" in res2.lower(),
        "Worker Queue mentioned": "worker" in res2.lower() or "queue" in res2.lower(),
        "Cluster or Pod metrics": any(k in res2.lower() for k in ["pod", "latency", "health", "healthy"]),
    }

    all_passed2 = True
    for name, passed in checks2.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_passed2 = False
        print(f"  [{status}] {name}")

    # =========================================================================
    # Test 3: scenic_photo.jpg
    # =========================================================================
    print("\n========================================================")
    print("TEST 3: Photo (scenic_photo.jpg)")
    print("========================================================")

    photo_path = "/app/sample_files/scenic_photo.jpg"
    thread3 = await Thread.objects.acreate(user=user, title="Photo Test")

    with open(photo_path, "rb") as f:
        photo_bytes = f.read()

    saved_photo_path, photo_size = storage.save_raw(photo_bytes, extension="jpg")
    uf3 = await UploadedFile.objects.acreate(
        thread=thread3,
        name="scenic_photo.jpg",
        mime="image/jpeg",
        size=photo_size,
        path=saved_photo_path,
        status="uploaded",
    )
    await sync_to_async(file_service.parse_file_sync)(uf3.id)
    await uf3.arefresh_from_db()
    print(f"Uploaded and parsed file_id={uf3.id}, status={uf3.status}")
    print(f"Manifest summary: {uf3.summary}")

    prompt3 = "Describe the visual scene, subject, and colors of this photo."
    res3, statuses3 = await run_chat_and_collect(thread3, prompt3)

    checks3 = {
        "Mountain or landscape scene": any(k in res3.lower() for k in ["mountain", "sunset", "sky", "landscape"]),
        "Sun or sunset mentioned": any(k in res3.lower() for k in ["sun", "sunset", "horizon", "dusk", "evening"]),
        "Colors mentioned": any(k in res3.lower() for k in ["orange", "yellow", "purple", "dark", "gradient", "warm"]),
    }

    all_passed3 = True
    for name, passed in checks3.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_passed3 = False
        print(f"  [{status}] {name}")

    print("\n========================================================")
    if all_passed1 and all_passed2 and all_passed3 and not has_base64:
        print("ALL REAL VISION VERIFICATIONS PASSED SUCCESSFULLY!")
        return 0
    else:
        print("SOME CHECKS FAILED.")
        return 1

if __name__ == "__main__":
    code = asyncio.run(verify_image_reading())
    sys.exit(code)
