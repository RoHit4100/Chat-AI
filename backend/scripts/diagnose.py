import os
import sys
import shutil
import asyncio
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Initialize Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
import django
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status
import jwt
from datetime import datetime, timezone, timedelta

from chat.models import Thread, Message, UploadedFile, GeneratedFile
from filesvc.parsers.registry import get_parser_for_file
from filesvc.generators.registry import get_generator, GENERATOR_MAP
from filesvc.storage import storage
from agent.tools import read_file, generate_file, ALL_TOOLS
from agent.nodes import prepare_node
from agent.graph import build_chat_graph
from agent.llm import get_llm
from chat.streaming import stream_chat_turn

User = get_user_model()
SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_files"

def run_check(label: str, fn):
    """Run a check function and print PASS/FAIL with details."""
    try:
        res = fn()
        if asyncio.iscoroutine(res):
            res = asyncio.run(res)
        print(f"[{label}] PASS: {res or 'OK'}")
        return True, ""
    except Exception as exc:
        import traceback
        err = f"{type(exc).__name__}: {str(exc)}"
        print(f"[{label}] FAIL: {err}")
        return False, err

def check_a_env():
    """a) env: LLM_PROVIDER, LLM_MODEL, key present, FAKE_LLM off."""
    provider = os.getenv("LLM_PROVIDER")
    if not provider:
        raise ValueError("LLM_PROVIDER environment variable is missing.")
    
    model = os.getenv("LLM_MODEL")
    if not model:
        raise ValueError("LLM_MODEL environment variable is missing.")
    
    fake_llm = os.getenv("FAKE_LLM", "0").lower()
    if fake_llm in ("1", "true"):
        raise ValueError(f"FAKE_LLM is enabled (value: {fake_llm}), expected FAKE_LLM=0.")
    
    key_var = f"{provider.upper()}_API_KEY"
    key_val = os.getenv(key_var)
    if not key_val:
        raise ValueError(f"API key {key_var} is missing or empty.")
    
    return f"provider={provider}, model={model}, key={key_var} (set), FAKE_LLM=0"

def check_b_model_tool_calling():
    """b) the model supports tool calling (bind a dummy tool and invoke)."""
    from langchain_core.tools import tool
    
    @tool
    def dummy_weather(location: str) -> str:
        """Get weather for location."""
        return f"Sunny in {location}"

    llm = get_llm()
    bound = llm.bind_tools([dummy_weather])
    resp = bound.invoke("What is the weather in Tokyo? Please use the dummy_weather tool.")
    
    # Check if tool_calls list is populated
    tool_calls = getattr(resp, "tool_calls", None)
    if not tool_calls:
        # Some models may emit tool calls in additional_kwargs
        raw_tc = getattr(resp, "additional_kwargs", {}).get("tool_calls")
        if not raw_tc:
            raise ValueError(f"Model did not return tool_calls. Content: {getattr(resp, 'content', '')}")
    return f"Model successfully emitted tool call: {tool_calls}"

def check_c_parsers_and_system():
    """c) every parser against sample_files/ (one per type), including libmagic, poppler and tesseract."""
    # Check system dependencies
    errors = []
    
    # libmagic
    try:
        import magic
        magic.Magic()
    except Exception as exc:
        errors.append(f"libmagic failure: {exc}")
        
    # poppler
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        errors.append("poppler (pdftoppm) is NOT installed in PATH.")

    # tesseract
    tesseract = shutil.which("tesseract")
    if not tesseract:
        errors.append("tesseract-ocr is NOT installed in PATH.")

    # Parsers
    sample_files = [
        "sample.pdf",
        "sample.docx",
        "sample.xlsx",
        "sample.csv",
        "sample.pptx",
        "sample.png",
        "sample.txt",
        "sample.py",
        "sample.json",
        "sample.zip",
    ]
    
    parsed_ok = []
    for fname in sample_files:
        fpath = SAMPLE_DIR / fname
        if not fpath.exists():
            errors.append(f"Missing sample file: {fname}")
            continue
        try:
            parser = get_parser_for_file(fname)
            res = parser.parse(str(fpath), fname)
            if not res.summary:
                errors.append(f"{fname}: parser returned empty summary")
            if not res.text and fname != "sample.png":
                errors.append(f"{fname}: parser returned empty text")
            parsed_ok.append(fname)
        except Exception as exc:
            errors.append(f"{fname} parse error: {exc}")
            
    if errors:
        raise RuntimeError(" | ".join(errors))
    return f"All system binaries and {len(parsed_ok)} parsers passed."

def _get_auth_client(user):
    from chat.authentication import get_jwks_client
    from unittest.mock import MagicMock
    from cryptography.hazmat.primitives.asymmetric import rsa
    
    # Generate test token
    test_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    mock_jwks = MagicMock()
    mock_jwks.get_signing_key_from_jwt.return_value = MagicMock(key=test_key.public_key())
    
    token = jwt.encode(
        {
            "sub": str(user.username),
            "email": str(user.email),
            "iss": settings.KEYCLOAK_PUBLIC_URL,
            "azp": settings.KEYCLOAK_CLIENT_ID,
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        },
        test_key,
        algorithm="RS256",
        headers={"kid": "test-kid"}
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client, mock_jwks

def check_d_upload_flow():
    """d) upload flow: upload a file via the API and confirm status becomes ready with parsed text and a summary."""
    from unittest.mock import patch
    user, _ = User.objects.get_or_create(username="diag_user_d", defaults={"email": "diag_d@example.com"})
    thread = Thread.objects.create(user=user, title="Diag Thread D")
    
    client, mock_jwks = _get_auth_client(user)
    with patch("chat.authentication.get_jwks_client", return_value=mock_jwks):
        sample_path = SAMPLE_DIR / "sample.txt"
        with open(sample_path, "rb") as f:
            upload_data = SimpleUploadedFile("sample.txt", f.read(), content_type="text/plain")
            resp = client.post(f"/api/threads/{thread.id}/files/", {"files": upload_data}, format="multipart")
            
        if resp.status_code != status.HTTP_201_CREATED:
            raise ValueError(f"Upload endpoint returned status {resp.status_code}: {resp.data}")
            
        uf = UploadedFile.objects.filter(thread=thread, name="sample.txt").first()
        if not uf:
            raise ValueError("UploadedFile record not found in database.")
        if uf.status != "ready":
            raise ValueError(f"UploadedFile status is '{uf.status}', expected 'ready'. Error: {uf.error}")
        if not uf.summary:
            raise ValueError("UploadedFile summary is empty.")
        if not uf.parsed_path or not os.path.exists(uf.parsed_path):
            raise ValueError(f"Parsed file not found on disk: {uf.parsed_path}")
        parsed_data = storage.read_parsed(uf.parsed_path)
        if not parsed_data.get("text"):
            raise ValueError("Parsed file JSON contains no text.")
            
    return f"File {uf.name} uploaded, status='{uf.status}', summary length={len(uf.summary)}"

async def check_e_manifest():
    """e) manifest: the prepare node loads the thread's files into state."""
    user, _ = User.objects.get_or_create(username="diag_user_e", defaults={"email": "diag_e@example.com"})
    thread = Thread.objects.create(user=user, title="Diag Thread E")
    uf = UploadedFile.objects.create(
        thread=thread,
        name="manifest_test.txt",
        mime="text/plain",
        size=100,
        path="/tmp/test",
        summary="Test file summary",
        status="ready"
    )
    
    config = {"configurable": {"thread_id": str(thread.id), "user_id": str(user.id)}}
    state = await prepare_node({}, config=config)
    manifest = state.get("manifest", [])
    
    found = any(item.get("id") == str(uf.id) and item.get("name") == "manifest_test.txt" for item in manifest)
    if not found:
        raise ValueError(f"Uploaded file not found in state manifest: {manifest}")
    return f"Prepare node loaded {len(manifest)} file(s) into state manifest."

def check_f_read_file_and_ownership():
    """f) read_file called directly for each file, including cross-thread ownership logic."""
    from unittest.mock import patch
    user1, _ = User.objects.get_or_create(username="diag_user_f1", defaults={"email": "diag_f1@example.com"})
    user2, _ = User.objects.get_or_create(username="diag_user_f2", defaults={"email": "diag_f2@example.com"})
    thread1 = Thread.objects.create(user=user1, title="Diag Thread F1")
    thread2 = Thread.objects.create(user=user2, title="Diag Thread F2")
    
    client, mock_jwks = _get_auth_client(user1)
    with patch("chat.authentication.get_jwks_client", return_value=mock_jwks):
        # Upload each sample file
        files_tested = []
        for fname in ["sample.txt", "sample.csv", "sample.pdf", "sample.docx", "sample.xlsx"]:
            fpath = SAMPLE_DIR / fname
            with open(fpath, "rb") as f:
                upload_data = SimpleUploadedFile(fname, f.read())
                resp = client.post(f"/api/threads/{thread1.id}/files/", {"files": upload_data}, format="multipart")
                if resp.status_code != 201:
                    raise ValueError(f"Failed to upload {fname}: {resp.data}")
            
            uf = UploadedFile.objects.filter(thread=thread1, name=fname).first()
            if not uf:
                raise ValueError(f"UploadedFile {fname} not created.")
                
            config1 = {"configurable": {"thread_id": str(thread1.id), "user_id": str(user1.id)}}
            # Read via ID
            out_id = read_file.invoke({"file_id": str(uf.id)}, config=config1)
            if "Error:" in out_id:
                raise ValueError(f"read_file failed for {fname} by id: {out_id}")
            
            # Cross-thread access test with user2 / thread2
            config2 = {"configurable": {"thread_id": str(thread2.id), "user_id": str(user2.id)}}
            out_unauth = read_file.invoke({"file_id": str(uf.id)}, config=config2)
            if "not found or access denied" not in out_unauth.lower():
                raise ValueError(f"Cross-thread read succeeded when it should fail: {out_unauth}")
                
            files_tested.append(fname)
            
    return f"Successfully tested read_file and cross-thread ownership on {files_tested}."

def check_g_generators_and_download():
    """g) every generator writes a valid file to the volume and download endpoint returns it."""
    from unittest.mock import patch
    user, _ = User.objects.get_or_create(username="diag_user_g", defaults={"email": "diag_g@example.com"})
    thread = Thread.objects.create(user=user, title="Diag Thread G")
    
    specs = {
        "md": ("doc.md", {"title": "Test MD", "content": "Sample content"}),
        "csv": ("data.csv", {"headers": ["A", "B"], "rows": [[1, 2], [3, 4]]}),
        "docx": ("report.docx", {"title": "Report", "paragraphs": ["Para 1"]}),
        "pdf": ("document.pdf", {"title": "Doc PDF", "paragraphs": ["Para 1"]}),
        "xlsx": ("sheet.xlsx", {"headers": ["Col1"], "rows": [["Val1"]]}),
        "pptx": ("slides.pptx", {"title": "Presentation", "slides": [{"title": "Slide 1"}]}),
        "png": ("chart.png", {"chart_type": "bar", "labels": ["X", "Y"], "values": [10, 20]}),
        "code": ("script.py", {"language": "python", "code": "print('hello')"}),
    }
    
    config = {"configurable": {"thread_id": str(thread.id), "user_id": str(user.id)}}
    client, mock_jwks = _get_auth_client(user)
    
    tested = []
    with patch("chat.authentication.get_jwks_client", return_value=mock_jwks):
        for kind, (name, spec) in specs.items():
            res = generate_file.invoke({"kind": kind, "name": name, "spec": spec}, config=config)
            if "Error" in res:
                raise ValueError(f"generate_file failed for {kind}: {res}")
                
            gf = GeneratedFile.objects.filter(thread=thread, kind=kind).order_by("-id").first()
            if not gf:
                raise ValueError(f"GeneratedFile record for {kind} not created in DB.")
            if not gf.path or not os.path.exists(gf.path) or os.path.getsize(gf.path) == 0:
                raise ValueError(f"Generated file {kind} missing or empty on disk: {gf.path}")
                
            # Test download endpoint
            resp = client.get(f"/api/generated/{gf.id}/download/")
            if resp.status_code != status.HTTP_200_OK:
                raise ValueError(f"Download endpoint failed for {kind} with status {resp.status_code}")
            if resp.get("X-Content-Type-Options") != "nosniff":
                raise ValueError(f"nosniff header missing on download for {kind}")
                
            tested.append(kind)
            
    return f"All {len(tested)} generators wrote valid files and download passed: {tested}"

def check_h_graph_tools_bound():
    """h) the graph: tools are actually bound to the agent node and tool names match."""
    from agent.tools import ALL_TOOLS
    tool_names = [t.name for t in ALL_TOOLS]
    expected = {"read_file", "generate_file", "read_generated_spec"}
    missing = expected - set(tool_names)
    if missing:
        raise ValueError(f"Missing expected tools in ALL_TOOLS: {missing}")
        
    graph = build_chat_graph()
    nodes = set(graph.nodes.keys())
    expected_nodes = {"prepare", "agent", "tools", "summarize"}
    if not expected_nodes.issubset(nodes):
        raise ValueError(f"Graph missing required nodes: {expected_nodes - nodes}")
        
    return f"Graph verified with nodes {nodes} and tools {tool_names}"

async def check_i_streaming():
    """i) streaming: file and status events still pass the stream filter and only agent text goes out as token events."""
    user, _ = User.objects.get_or_create(username="diag_user_i", defaults={"email": "diag_i@example.com"})
    thread = Thread.objects.create(user=user, title="Diag Thread I")
    
    events = []
    async for event_str in stream_chat_turn(thread, user_prompt="Say exactly 'STREAM_OK' and nothing else."):
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
                except Exception:
                    data = line.split(":", 1)[1].strip()
        if event_name:
            events.append((event_name, data))
            
    event_types = [e[0] for e in events]
    if "status" not in event_types:
        raise ValueError(f"Status events missing in stream. Event types: {event_types}")
    if "token" not in event_types:
        raise ValueError(f"Token events missing in stream. Event types: {event_types}")
    if "done" not in event_types:
        raise ValueError(f"Done event missing in stream. Event types: {event_types}")
        
    tokens = [e[1].get("content", "") for e in events if e[0] == "token"]
    full_text = "".join(tokens)
    if not full_text.strip():
        raise ValueError("Streamed tokens produced empty text.")
        
    # Verify saved assistant message in DB
    msg = await Message.objects.filter(thread=thread, role="assistant").alast()
    if not msg:
        raise ValueError("Saved assistant Message record not found in database.")
    if not msg.content:
        raise ValueError("Saved assistant Message content is empty.")
    if "prepare" in msg.content or "summarize" in msg.content:
        raise ValueError(f"Saved message contains status/summary text: {msg.content}")
        
    return f"Streaming completed with {len(tokens)} token chunks, final message length: {len(msg.content)}."

def main():
    print("========================================")
    print("STARTING DIAGNOSTIC SUITE (Step 1)")
    print("========================================")
    
    results = {}
    results["a) env"] = run_check("a) env", check_a_env)
    results["b) model tool calling"] = run_check("b) model tool calling", check_b_model_tool_calling)
    results["c) parsers and system"] = run_check("c) parsers and system", check_c_parsers_and_system)
    results["d) upload flow"] = run_check("d) upload flow", check_d_upload_flow)
    results["e) manifest"] = run_check("e) manifest", check_e_manifest)
    results["f) read_file & ownership"] = run_check("f) read_file & ownership", check_f_read_file_and_ownership)
    results["g) generators & download"] = run_check("g) generators & download", check_g_generators_and_download)
    results["h) graph & tools"] = run_check("h) graph & tools", check_h_graph_tools_bound)
    results["i) streaming"] = run_check("i) streaming", check_i_streaming)

    print("========================================")
    print("DIAGNOSTIC SUMMARY:")
    passed_count = sum(1 for passed, _ in results.values() if passed)
    total_count = len(results)
    for name, (passed, err) in results.items():
        status_str = "PASS" if passed else "FAIL"
        err_str = f" -> {err}" if err else ""
        print(f"  {name}: {status_str}{err_str}")
    print(f"\nTOTAL: {passed_count}/{total_count} PASSED")
    print("========================================")
    
    if passed_count < total_count:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
