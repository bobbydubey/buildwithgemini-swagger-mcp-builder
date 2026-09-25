import base64
import json
import os
import datetime
import glob
import re
import sys
from dotenv import load_dotenv

# Load GCP configuration exclusively from .env file or environment variables
load_dotenv()
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")))
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "swagger-mcp-builder", ".env")))

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "true")
FIRESTORE_PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")

import google.auth
import google.auth.transport.requests
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

RESOURCE = os.environ.get("AGENT_ENGINE_RESOURCE_NAME", "")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
if RESOURCE and "/locations/" in RESOURCE:
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


def _extract_part(raw_val: str) -> list[dict] | dict | None:
    if not raw_val or not isinstance(raw_val, str):
        return None

    decoded = raw_val
    if "PGEyYV9k" in raw_val or "PGEyYQ" in raw_val:
        try:
            decoded = base64.b64decode(raw_val.strip()).decode("utf-8")
        except Exception:
            decoded = raw_val

    if "<a2ui-json>" in decoded:
        try:
            parts = []
            before = decoded.split("<a2ui-json>")[0].strip()
            if before:
                parts.append({"kind": "text", "text": before})
            json_part = decoded.split("<a2ui-json>")[1].split("</a2ui-json>")[0].strip()
            parsed = json.loads(json_part)
            parts.append({"kind": "a2ui", "data": parsed})
            after = decoded.split("</a2ui-json>")[1].strip()
            if after:
                parts.append({"kind": "text", "text": after})
            return parts
        except Exception:
            pass

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
async def get_mcps(strategy: str = "gcp", category: str = ""):
    """Returns list of all registered MCP servers categorized into active, ready, and stopped."""
    results = []
    seen_ids = set()
    
    if strategy.lower() == "filebased":
        try:
            import glob
            _root_mcps = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mcps"))
            _pkg_mcps = os.path.abspath(os.path.join(os.path.dirname(__file__), "mcps"))
            json_files = list(set(glob.glob(os.path.join(_root_mcps, "*.json")) + glob.glob(os.path.join(_pkg_mcps, "*.json")) + glob.glob(os.path.join(MCPS_DIR, "*.json"))))
            for filepath in json_files:
                try:
                    with open(filepath, "r") as f:
                        data = json.load(f)
                        server_id = data.get("server_name") or os.path.basename(filepath).replace(".json", "")
                        if server_id not in seen_ids:
                            data["id"] = server_id
                            results.append(data)
                            seen_ids.add(server_id)
                except Exception:
                    pass
        except Exception as e:
            return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    else:
        try:
            from google.cloud import firestore
            database_id = os.environ.get("FIRESTORE_DATABASE", "(default)")
            project_id = FIRESTORE_PROJECT_ID or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
            db = firestore.Client(project=project_id, database=database_id) if project_id else firestore.Client(database=database_id)
            docs = list(db.collection("mcp_servers").stream())
            for doc in docs:
                data = doc.to_dict()
                server_id = doc.id
                if server_id not in seen_ids:
                    data["id"] = server_id
                    results.append(data)
                    seen_ids.add(server_id)
        except Exception as e:
            return JSONResponse({"status": "error", "strategy": "gcp", "message": f"Firestore connection unavailable: {str(e)}", "mcps": [], "categories": {"active": [], "ready": [], "stopped": []}})

    categories = {"active": [], "ready": [], "stopped": []}
    for item in results:
        st = (item.get("status") or "ready").lower()
        if st in ["running", "active"]:
            st = "active"
        elif st in ["stopped", "disabled"]:
            st = "stopped"
        else:
            st = "ready"
        item["status"] = st
        categories[st].append(item)

    filtered_mcps = results
    if category and category.lower() in categories:
        filtered_mcps = categories[category.lower()]

    return JSONResponse({
        "status": "success",
        "strategy": strategy.lower(),
        "total": len(results),
        "categories": categories,
        "counts": {
            "all": len(results),
            "active": len(categories["active"]),
            "ready": len(categories["ready"]),
            "stopped": len(categories["stopped"])
        },
        "mcps": filtered_mcps
    })

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
            return JSONResponse({"status": "error", "message": str(e)})
    else:
        try:
            from google.cloud import firestore
            database_id = os.environ.get("FIRESTORE_DATABASE", "(default)")
            project_id = FIRESTORE_PROJECT_ID or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
            db = firestore.Client(project=project_id, database=database_id) if project_id else firestore.Client(database=database_id)
            doc_ref = db.collection("mcp_servers").document(server_name)
            doc_ref.set({
                "status": new_status.lower(),
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }, merge=True)
            return JSONResponse({"status": "success", "strategy": "gcp", "server_name": server_name, "new_status": new_status})
        except Exception as e:
            return JSONResponse({"status": "error", "message": str(e)})


@app.post("/api/ingest")
async def ingest_swagger(req: Request):
    """Ingests a Swagger spec (URL or raw JSON/YAML content) and generates a new MCP server configuration."""
    try:
        body = await req.json()
        raw_name = body.get("server_name", "").strip().lower()
        server_name = re.sub(r'[^a-zA-Z0-9_]', '_', raw_name)
        title = body.get("title", "").strip() or server_name.replace("_", " ").title()
        base_url = body.get("base_url", "").strip()
        target_app = body.get("target_app", "").strip() or "Java REST Service"
        swagger_url = body.get("swagger_url", "").strip()
        swagger_content = body.get("swagger_content", "").strip()
        strategy = body.get("strategy", "gcp").lower()

        if not server_name:
            return JSONResponse({"status": "error", "message": "Server name is required."}, status_code=400)

        spec_data = {}
        if swagger_url:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(swagger_url)
                    if resp.status_code == 200:
                        spec_data = resp.json()
                        if not base_url:
                            schemes = spec_data.get("schemes", ["http"])
                            host = spec_data.get("host", "")
                            base_path = spec_data.get("basePath", "")
                            if host:
                                base_url = f"{schemes[0]}://{host}{base_path}".rstrip("/")
            except Exception:
                pass
        elif swagger_content:
            try:
                spec_data = json.loads(swagger_content)
            except Exception:
                try:
                    import yaml
                    spec_data = yaml.safe_load(swagger_content)
                except Exception:
                    pass

        paths = spec_data.get("paths", {}) if isinstance(spec_data, dict) else {}
        total_tools = len(paths) if paths else 10

        if not base_url:
            base_url = "https://petstore.swagger.io/v2" if "petstore" in server_name else "http://localhost:8080"

        mcp_config = {
            "id": server_name,
            "server_name": server_name,
            "title": title,
            "base_url": base_url,
            "status": "ready",
            "total_tools": total_tools,
            "target_app": target_app,
            "environment": "dev",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

        if strategy == "filebased":
            file_path = os.path.join(MCPS_DIR, f"{server_name}.json")
            with open(file_path, "w") as f:
                json.dump(mcp_config, f, indent=2)
        else:
            try:
                from google.cloud import firestore
                database_id = os.environ.get("FIRESTORE_DATABASE", "(default)")
                project_id = FIRESTORE_PROJECT_ID or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
                db = firestore.Client(project=project_id, database=database_id) if project_id else firestore.Client(database=database_id)
                db.collection("mcp_servers").document(server_name).set(mcp_config, merge=True)
            except Exception:
                file_path = os.path.join(MCPS_DIR, f"{server_name}.json")
                with open(file_path, "w") as f:
                    json.dump(mcp_config, f, indent=2)

        return JSONResponse({"status": "success", "strategy": strategy, "mcp": mcp_config})
    except Exception as err:
        return JSONResponse({"status": "error", "message": str(err)}, status_code=500)


_local_runner = None
_local_session_service = None

async def _get_local_runner():
    global _local_runner, _local_session_service
    if _local_runner is None:
        builder_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "swagger-mcp-builder"))
        if builder_dir not in sys.path:
            sys.path.insert(0, builder_dir)
        from app.agent import root_agent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        _local_session_service = InMemorySessionService()
        _local_runner = Runner(agent=root_agent, session_service=_local_session_service, app_name="swagger_mcp_builder")
    return _local_runner, _local_session_service


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
    if active_mcp and active_mcp.lower() not in ["auto", "auto_router"] and not message.lower().startswith("use "):
        message = f"{prefix} Using sub-agent '{active_mcp}': {message}"
    else:
        message = f"{prefix} [AUTO ROUTER MODE] Auto-detect the matching registered MCP server from the database and execute request: {message}"

    # Try local ADK execution first for seamless local development
    try:
        runner, session_svc = await _get_local_runner()
        session_id = f"session_{user_id}"
        session = await session_svc.get_session(user_id=user_id, session_id=session_id, app_name="swagger_mcp_builder")
        if session is None:
            await session_svc.create_session(user_id=user_id, session_id=session_id, app_name="swagger_mcp_builder")

        from google.genai import types
        msg_content = types.Content(role="user", parts=[types.Part.from_text(text=message)])

        print(f"Running local runner for message: {message}", flush=True)
        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=msg_content):
            print(f"Local runner event received: {type(event)}", flush=True)
            if hasattr(event, "content") and event.content:
                for p in event.content.parts:
                    if hasattr(p, "text") and p.text:
                        p_extracted = _extract_part(p.text)
                        print(f"Extracted part: {p_extracted}", flush=True)
                        if p_extracted:
                            if isinstance(p_extracted, list):
                                parts.extend(p_extracted)
                            else:
                                parts.append(p_extracted)
        print(f"Local runner completed. Total parts: {len(parts)}", flush=True)
        if parts:
            return JSONResponse({"parts": parts})
    except Exception as local_err:
        import traceback
        print("Local runner error:", local_err, flush=True)
        traceback.print_exc()

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
                            if isinstance(p_extracted, list):
                                turn_parts.extend(p_extracted)
                            else:
                                turn_parts.append(p_extracted)

                        inline_data = p.get("inline_data") or {}
                        data_str = inline_data.get("data", "")
                        if data_str:
                            data_extracted = _extract_part(data_str)
                            if data_extracted:
                                if isinstance(data_extracted, list):
                                    turn_parts.extend(data_extracted)
                                else:
                                    turn_parts.append(data_extracted)

            if turn_parts:
                parts.extend(turn_parts)
                break
            else:
                current_message = "Please continue processing and complete the requested task."

    if not parts:
        parts = [{"kind": "text", "text": "(No response received from agent)"}]

    return JSONResponse({"parts": parts})


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
