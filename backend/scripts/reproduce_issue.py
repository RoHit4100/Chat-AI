import os
import sys
import time
import asyncio
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
import django
django.setup()

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from chat.models import Thread, Message, UploadedFile, GeneratedFile
from chat.streaming import stream_chat_turn
from filesvc.service import file_service
from filesvc.storage import storage

User = get_user_model()
SAMPLE_DIR = BASE_DIR / "sample_files"
RESUME_PDF = SAMPLE_DIR / "Rohit_Udamale_Resume_Updated_AI_React.pdf"

async def reproduce():
    print("=== REPRODUCING FILE GENERATION ISSUE ===")
    t_start = time.time()
    
    # 1. Create test user and thread
    user, _ = User.objects.get_or_create(username="repro_user", defaults={"email": "repro@example.com"})
    thread = Thread.objects.create(user=user, title="Resume Update Repro")
    
    # 2. Upload the resume PDF
    with open(RESUME_PDF, "rb") as f:
        file_obj = SimpleUploadedFile("Rohit_Udamale_Resume_Updated_AI_React.pdf", f.read(), content_type="application/pdf")
        saved_path, written_size = storage.save_raw(file_obj, ".pdf")
        uf = UploadedFile.objects.create(
            thread=thread,
            name="Rohit_Udamale_Resume_Updated_AI_React.pdf",
            mime="application/pdf",
            size=written_size,
            path=saved_path,
            status="pending",
        )
        uf = file_service.parse_file_sync(uf.id)
        
    print(f"[Upload] File uploaded and parsed in {time.time() - t_start:.2f}s, status={uf.status}, summary_len={len(uf.summary)}")

    # 3. Stream chat turn with exact prompt
    prompt = "take the reference of the attached resume and give me one updated resume for the backend, react native developer"
    
    t_prompt_start = time.time()
    first_status_time = None
    read_file_time = None
    gen_file_time = None
    tokens = []
    statuses = []
    files = []
    
    async for event_str in stream_chat_turn(thread, user_prompt=prompt):
        lines = [l for l in event_str.strip().split("\n") if l]
        event_name = ""
        data = {}
        for line in lines:
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                import json
                try:
                    data = json.loads(line.split(":", 1)[1].strip())
                except:
                    data = {}
                    
        now = time.time()
        if event_name == "status":
            if first_status_time is None:
                first_status_time = now - t_prompt_start
            node = data.get("node")
            status_text = data.get("status", "")
            statuses.append((now - t_prompt_start, node, status_text))
            if "read_file" in status_text and read_file_time is None:
                read_file_time = now - t_prompt_start
            if "generate_file" in status_text and gen_file_time is None:
                gen_file_time = now - t_prompt_start
        elif event_name == "token":
            tokens.append(data.get("content", ""))
        elif event_name == "file":
            files.append(data)
            
    total_time = time.time() - t_prompt_start
    print(f"\n[Timing Metrics]")
    print(f"  Time to first status event: {first_status_time:.2f}s" if first_status_time else "  Time to first status event: N/A")
    print(f"  Time to read_file tool: {read_file_time:.2f}s" if read_file_time else "  Time to read_file tool: NOT CALLED!")
    print(f"  Time to generate_file tool: {gen_file_time:.2f}s" if gen_file_time else "  Time to generate_file tool: NOT CALLED!")
    print(f"  Total turn time: {total_time:.2f}s")
    
    print(f"\n[Agent Response]")
    print("".join(tokens))
    
    print(f"\n[Generated Files]")
    print(files)
    
    # 4. Inspect generated file if created
    gf = GeneratedFile.objects.filter(thread=thread).order_by("-id").first()
    if gf and os.path.exists(gf.path):
        print(f"\n[Generated File Analysis] ID={gf.id}, Path={gf.path}, Size={os.path.getsize(gf.path)} bytes")
        # Extract text with pdftotext
        import subprocess
        out_txt = subprocess.check_output(["pdftotext", gf.path, "-"]).decode("utf-8", errors="replace")
        print(f"  Extracted Text Length: {len(out_txt)} chars")
        print(f"  Extracted Text Preview:\n{out_txt[:1000]}")
        
        # Rasterize page 1 to PNG using pdf2image and poppler
        from pdf2image import convert_from_path
        images = convert_from_path(gf.path, first_page=1, last_page=1)
        if images:
            repro_png = BASE_DIR / "sample_files" / "repro_page1.png"
            images[0].save(repro_png, "PNG")
            print(f"  Page 1 rasterized to: {repro_png} ({images[0].size})")
    else:
        print("\n[Generated File Analysis] No file was generated!")

if __name__ == "__main__":
    asyncio.run(reproduce())
