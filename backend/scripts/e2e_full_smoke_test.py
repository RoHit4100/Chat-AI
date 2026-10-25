import os
import sys
import time
import requests
import json
import subprocess
from pathlib import Path

BASE_URL = "http://localhost:8000"
KEYCLOAK_URL = "http://localhost:8080/realms/chat/protocol/openid-connect/token"
CLIENT_ID = "chat-web"
USERNAME = "demo"
PASSWORD = "demo1234"

def step(title):
    print(f"\n========================================================")
    print(f"==> {title}")
    print(f"========================================================")

def run():
    results = {}

    # 1. Keycloak Authentication
    step("1. Log in via Keycloak (OAuth2 Password Grant)")
    try:
        resp = requests.post(
            KEYCLOAK_URL,
            data={
                "client_id": CLIENT_ID,
                "grant_type": "password",
                "username": USERNAME,
                "password": PASSWORD,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Keycloak login failed ({resp.status_code}): {resp.text}")
        token_data = resp.json()
        access_token = token_data["access_token"]
        print(f"Successfully obtained access token for user '{USERNAME}' (token length: {len(access_token)})")
        results["keycloak_login"] = "PASS"
    except Exception as e:
        print(f"FAILED: {e}")
        results["keycloak_login"] = f"FAIL: {e}"
        return results

    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    # 2. Create Thread
    step("2. Create a new thread")
    try:
        resp = requests.post(
            f"{BASE_URL}/api/threads/",
            headers=headers,
            json={"title": "E2E Smoke Test Thread"},
            timeout=10,
        )
        if resp.status_code != 201:
            raise RuntimeError(f"Thread creation failed ({resp.status_code}): {resp.text}")
        thread_data = resp.json()
        thread_id = thread_data["id"]
        print(f"Thread created successfully: ID = {thread_id}")
        results["thread_create"] = "PASS"
    except Exception as e:
        print(f"FAILED: {e}")
        results["thread_create"] = f"FAIL: {e}"
        return results

    # 3. Upload Two Files of Different Types
    step("3. Upload two files of different types (CSV and PDF)")
    try:
        sample_csv = Path(__file__).resolve().parent.parent / "sample_files" / "sample.csv"
        sample_pdf = Path(__file__).resolve().parent.parent / "sample_files" / "sample.pdf"

        # Upload CSV
        with open(sample_csv, "rb") as f:
            resp_csv = requests.post(
                f"{BASE_URL}/api/threads/{thread_id}/files/",
                headers=headers,
                files={"files": ("sample.csv", f, "text/csv")},
                timeout=15,
            )
        if resp_csv.status_code != 201:
            raise RuntimeError(f"CSV upload failed ({resp_csv.status_code}): {resp_csv.text}")
        data_csv = resp_csv.json()
        csv_file_id = data_csv[0]["id"] if isinstance(data_csv, list) else data_csv["id"]
        print(f"Uploaded sample.csv (id: {csv_file_id})")

        # Upload PDF
        with open(sample_pdf, "rb") as f:
            resp_pdf = requests.post(
                f"{BASE_URL}/api/threads/{thread_id}/files/",
                headers=headers,
                files={"files": ("sample.pdf", f, "application/pdf")},
                timeout=15,
            )
        if resp_pdf.status_code != 201:
            raise RuntimeError(f"PDF upload failed ({resp_pdf.status_code}): {resp_pdf.text}")
        data_pdf = resp_pdf.json()
        pdf_file_id = data_pdf[0]["id"] if isinstance(data_pdf, list) else data_pdf["id"]
        print(f"Uploaded sample.pdf (id: {pdf_file_id})")

        results["upload_files"] = "PASS"
    except Exception as e:
        print(f"FAILED: {e}")
        results["upload_files"] = f"FAIL: {e}"
        return results

    # Helper function for SSE streaming
    def stream_query(prompt, timeout=60):
        print(f"\nSending prompt: '{prompt}'")
        t_start = time.time()
        resp = requests.post(
            f"{BASE_URL}/api/threads/{thread_id}/stream",
            headers=headers,
            json={"message": prompt, "files": [csv_file_id, pdf_file_id] if "csv_file_id" in locals() and csv_file_id else []},
            stream=True,
            timeout=timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Stream request failed ({resp.status_code}): {resp.text}")

        events = []
        tokens = []
        generated_files = []
        statuses = []
        first_status = None

        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                try:
                    payload = json.loads(line.split(":", 1)[1].strip())
                except:
                    payload = {}
                now = time.time() - t_start
                if current_event == "status":
                    if first_status is None:
                        first_status = now
                    statuses.append((now, payload))
                    print(f"  [Status {now:.2f}s] {payload.get('node')}: {payload.get('status')}")
                elif current_event == "token":
                    tokens.append(payload.get("content", ""))
                elif current_event == "file":
                    generated_files.append(payload)
                    print(f"  [File Event] {payload}")
                elif current_event == "done":
                    print(f"  [Done Event] Turn completed in {now:.2f}s")

        full_text = "".join(tokens)
        return {
            "text": full_text,
            "files": generated_files,
            "statuses": statuses,
            "first_status": first_status,
            "duration": time.time() - t_start,
        }

    # 4. Ask about both files
    step("4. Ask about both uploaded files")
    try:
        res = stream_query("What are the contents and summaries of both the uploaded files sample.csv and sample.pdf?")
        print(f"Assistant Response:\n{res['text'][:400]}...")
        if len(res['text']) > 50:
            results["query_both_files"] = "PASS"
        else:
            results["query_both_files"] = "FAIL: Response too short"
    except Exception as e:
        print(f"FAILED: {e}")
        results["query_both_files"] = f"FAIL: {e}"

    # 5. Request an xlsx and revise it
    step("5. Request an xlsx file")
    try:
        res_xlsx = stream_query("Generate an Excel spreadsheet quarterly_report.xlsx with columns Quarter, Revenue, Expenses and 4 quarters of data.")
        print(f"Assistant Response:\n{res_xlsx['text']}")
        print(f"Files: {res_xlsx['files']}")
        if res_xlsx["files"]:
            v1_id = res_xlsx["files"][0]["id"]
            results["generate_xlsx_v1"] = f"PASS (File ID: {v1_id})"
        else:
            raise RuntimeError("No file event emitted in stream.")
    except Exception as e:
        print(f"FAILED: {e}")
        results["generate_xlsx_v1"] = f"FAIL: {e}"
        v1_id = None

    if v1_id:
        step("5b. Revise the xlsx file")
        try:
            res_rev = stream_query(f"Please revise quarterly_report.xlsx to add a Profit column calculated from Revenue minus Expenses.")
            print(f"Assistant Response:\n{res_rev['text']}")
            print(f"Files: {res_rev['files']}")
            if res_rev["files"]:
                v2_id = res_rev["files"][0]["id"]
                v2_ver = res_rev["files"][0]["version"]
                print(f"Revised file ID: {v2_id}, Version: {v2_ver}")
                if v2_ver == 2:
                    results["revise_xlsx_v2"] = f"PASS (v2 ID: {v2_id})"
                else:
                    results["revise_xlsx_v2"] = f"FAIL: version is {v2_ver}, expected 2"
            else:
                results["revise_xlsx_v2"] = "FAIL: No file event emitted"
        except Exception as e:
            print(f"FAILED: {e}")
            results["revise_xlsx_v2"] = f"FAIL: {e}"

    # 6. Stop and Regenerate
    step("6. Test Stop and Regenerate response")
    try:
        # Start a stream and stop it early by closing connection
        print("Starting stream to simulate user clicking Stop...")
        req = requests.post(
            f"{BASE_URL}/api/threads/{thread_id}/stream",
            headers=headers,
            json={"message": "Write a long 500 word essay about the history of computing."},
            stream=True,
            timeout=5,
        )
        time.sleep(1.0)
        req.close()  # Simulate client disconnect / stop
        print("Client disconnected (Stop pressed).")

        # Now test regenerate
        time.sleep(1.0)
        print("Triggering regenerate...")
        regen_resp = requests.post(
            f"{BASE_URL}/api/threads/{thread_id}/regenerate",
            headers=headers,
            stream=True,
            timeout=60,
        )
        if regen_resp.status_code != 200:
            raise RuntimeError(f"Regenerate failed ({regen_resp.status_code}): {regen_resp.text}")

        regen_tokens = []
        for line in regen_resp.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                try:
                    payload = json.loads(line.split(":", 1)[1].strip())
                    if "content" in payload:
                        regen_tokens.append(payload["content"])
                except:
                    pass
        regen_text = "".join(regen_tokens)
        print(f"Regenerated response length: {len(regen_text)} chars")
        if len(regen_text) > 0:
            results["stop_and_regenerate"] = "PASS"
        else:
            results["stop_and_regenerate"] = "FAIL: empty regenerated response"
    except Exception as e:
        print(f"FAILED: {e}")
        results["stop_and_regenerate"] = f"FAIL: {e}"

    # 7. Refresh: retrieve messages from thread
    step("7. Refresh thread messages (HTTP GET /messages/)")
    try:
        resp = requests.get(f"{BASE_URL}/api/threads/{thread_id}/messages/", headers=headers, timeout=10)
        if resp.status_code != 200:
            raise RuntimeError(f"Get messages failed ({resp.status_code})")
        msgs = resp.json()
        print(f"Thread has {len(msgs)} messages persisted in database.")
        results["refresh_thread"] = f"PASS ({len(msgs)} messages)"
    except Exception as e:
        print(f"FAILED: {e}")
        results["refresh_thread"] = f"FAIL: {e}"

    # 8. Restart backend container and confirm thread resumes
    step("8. Restart backend container and confirm thread resumes")
    try:
        print("Restarting chat-ai-backend-1 container...")
        subprocess.check_call(["docker", "restart", "chat-ai-backend-1"])
        print("Waiting for backend health check...")
        for _ in range(30):
            time.sleep(1)
            try:
                r = requests.get(f"{BASE_URL}/api/threads/", headers=headers, timeout=2)
                if r.status_code == 200:
                    print("Backend is back online!")
                    break
            except Exception:
                pass

        # Confirm thread can be loaded and new message sent
        resp_resume = stream_query("Are you still there? Can you summarize our previous discussion?")
        print(f"Resumed response:\n{resp_resume['text']}")
        if len(resp_resume["text"]) > 20:
            results["restart_and_resume"] = "PASS"
        else:
            results["restart_and_resume"] = "FAIL: Resume response too short"
    except Exception as e:
        print(f"FAILED: {e}")
        results["restart_and_resume"] = f"FAIL: {e}"

    return results

if __name__ == "__main__":
    results = run()
    print("\n\n================ FINAL SUMMARY ================")
    for k, v in results.items():
        print(f"  {k}: {v}")
