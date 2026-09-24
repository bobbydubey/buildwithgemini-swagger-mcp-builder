import base64
import json
import os
import datetime
import glob

import google.auth
import google.auth.transport.requests
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

RESOURCE = os.environ.get(
    "AGENT_ENGINE_RESOURCE_NAME",
    "projects/246530964117/locations/us-east1/reasoningEngines/7037290033161699328",
)
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]
MCPS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mcps"))
if not os.path.exists(MCPS_DIR):
    MCPS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "mcps"))
os.makedirs(MCPS_DIR, exist_ok=True)

_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


app = FastAPI(title="Swagger MCP Builder & Automation Studio")


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


# Store session_id per user_id
_user_sessions: dict[str, str] = {}


async def _get_or_create_session(user_id: str, client: httpx.AsyncClient) -> str:
    if user_id in _user_sessions:
        return _user_sessions[user_id]

    query_url = (
        f"https://{LOCATION}-aiplatform.googleapis.com/v1/{RESOURCE}:query"
    )
    payload = {
        "class_method": "async_create_session",
        "input": {"user_id": user_id},
    }
    resp = await client.post(query_url, json=payload)
    if resp.status_code == 200:
        session_id = resp.json().get("output", {}).get("id")
        if session_id:
            _user_sessions[user_id] = session_id
            return session_id
    return ""


def _extract_part(raw_val: str) -> dict | None:
    if not raw_val or not isinstance(raw_val, str):
        return None

    decoded = raw_val
    if "PGEyYV9k" in raw_val or "PGEyYQ" in raw_val:
        try:
            decoded = base64.b64decode(raw_val.strip()).decode("utf-8")
        except Exception:
            decoded = raw_val

    if "<a2a_datapart_json>" in decoded:
        try:
            json_part = decoded.split("<a2a_datapart_json>")[1].split(
                "</a2a_datapart_json>"
            )[0]
            parsed = json.loads(json_part)
            if (
                parsed.get("metadata", {}).get("mimeType")
                == "application/json+a2ui"
            ):
                return {"kind": "a2ui", "data": parsed.get("data")}
        except Exception:
            pass
        return None

    if decoded.startswith("PGEyYV") or "PGEyYV9k" in decoded:
        return None

    return {"kind": "text", "text": decoded}


@app.get("/api/mcps")
async def get_mcps(strategy: str = "gcp"):
    """Returns list of all registered MCP servers from GCP Firestore or File-based mcps/ directory."""
    if strategy.lower() == "filebased":
        try:
            results = []
            json_files = glob.glob(os.path.join(MCPS_DIR, "*.json"))
            for filepath in json_files:
                try:
                    with open(filepath, "r") as f:
                        data = json.load(f)
                        data["id"] = data.get("server_name") or os.path.basename(filepath).replace(".json", "")
                        results.append(data)
                except Exception:
                    pass
            return JSONResponse({"status": "success", "strategy": "filebased", "mcps": results})
        except Exception as e:
            return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    else:
        # Default: GCP Firestore
        try:
            from google.cloud import firestore
            db = firestore.Client(project=FIRESTORE_PROJECT_ID)
            docs = list(db.collection("mcp_servers").stream())
            results = []
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                results.append(data)
            return JSONResponse({"status": "success", "strategy": "gcp", "mcps": results})
        except Exception as e:
            return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/mcps/{server_name}/toggle")
async def toggle_mcp(server_name: str, req: Request):
    """Starts or Stops a sub-agent / MCP server process in GCP Firestore or local file storage."""
    body = await req.json()
    new_status = body.get("status", "running")
    strategy = body.get("strategy", "gcp").lower()

    if strategy == "filebased":
        try:
            file_path = os.path.join(MCPS_DIR, f"{server_name}.json")
            data = {}
            if os.path.exists(file_path):
                with open(file_path, "r") as f:
                    data = json.load(f)
            data["status"] = new_status.lower()
            data["server_name"] = server_name
            data["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)
            return JSONResponse({"status": "success", "strategy": "filebased", "server_name": server_name, "new_status": new_status})
        except Exception as e:
            return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    else:
        try:
            from google.cloud import firestore
            db = firestore.Client(project=FIRESTORE_PROJECT_ID)
            doc_ref = db.collection("mcp_servers").document(server_name)
            doc_ref.set({
                "status": new_status.lower(),
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }, merge=True)
            return JSONResponse({"status": "success", "strategy": "gcp", "server_name": server_name, "new_status": new_status})
        except Exception as e:
            return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    active_mcp = body.get("active_mcp") or ""
    strategy = body.get("strategy") or "gcp"
    parts: list[dict] = []

    # Format context with strategy and active sub-agent if selected
    prefix = f"[Storage Strategy: {strategy.upper()}]"
    if active_mcp and not message.lower().startswith("use "):
        message = f"{prefix} Using sub-agent '{active_mcp}': {message}"
    else:
        message = f"{prefix} {message}"

    stream_url = (
        f"https://{LOCATION}-aiplatform.googleapis.com/v1/{RESOURCE}:streamQuery"
    )

    async with httpx.AsyncClient(
        headers=_auth_headers(), timeout=120.0
    ) as client:
        session_id = await _get_or_create_session(user_id, client)
        current_message = message

        for turn in range(5):
            payload = {
                "class_method": "async_stream_query",
                "input": {
                    "user_id": user_id,
                    "session_id": session_id,
                    "message": current_message,
                },
            }

            turn_parts: list[dict] = []
            async with client.stream("POST", stream_url, json=payload) as resp:
                if resp.status_code != 200:
                    err_body = await resp.aread()
                    return JSONResponse(
                        {
                            "parts": [
                                {
                                    "kind": "text",
                                    "text": f"Agent Engine HTTP {resp.status_code}: {err_body.decode()}",
                                }
                            ]
                        }
                    )

                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except Exception:
                        continue

                    content = event.get("content") or {}
                    for p in content.get("parts", []):
                        p_extracted = _extract_part(p.get("text"))
                        if p_extracted:
                            turn_parts.append(p_extracted)

                        inline_data = p.get("inline_data") or {}
                        data_str = inline_data.get("data", "")
                        if data_str:
                            data_extracted = _extract_part(data_str)
                            if data_extracted:
                                turn_parts.append(data_extracted)

            if turn_parts:
                parts.extend(turn_parts)
                break
            else:
                current_message = "Please continue processing and complete the requested task."

    if not parts:
        parts = [{"kind": "text", "text": "(No response received from agent)"}]

    return JSONResponse({"parts": parts})


app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
