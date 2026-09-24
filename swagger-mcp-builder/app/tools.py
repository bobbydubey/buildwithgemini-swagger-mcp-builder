# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tools for parsing OpenAPI/Swagger specs, generating MCP servers, and managing server lifecycle."""

import fnmatch
import json
import os
import re
import signal
import subprocess
import sys
import urllib.request
import yaml


SERVERS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mcp_servers"))
PID_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mcp_pids.json"))


def _load_pids() -> dict:
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_pids(pids: dict):
    with open(PID_FILE, "w") as f:
        json.dump(pids, f, indent=2)


def ingest_swagger_input(url_or_content: str) -> str:
    """Fetches and parses an OpenAPI 3.x or Swagger 2.0 specification from a URL or raw JSON/YAML content.

    Args:
        url_or_content: A HTTP/HTTPS URL pointing to swagger.json/openapi.yaml (e.g. http://localhost:8080/v3/api-docs) or raw string content.

    Returns:
        JSON string containing the parsed API metadata, title, base URL, and extracted endpoints with parameters.
    """
    spec_data = None
    if url_or_content.startswith("http://") or url_or_content.startswith("https://"):
        req = urllib.request.Request(
            url_or_content,
            headers={"User-Agent": "Swagger-MCP-Builder/1.0", "Accept": "application/json, application/yaml, text/yaml, */*"}
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                content = response.read().decode("utf-8")
                try:
                    spec_data = json.loads(content)
                except Exception:
                    spec_data = yaml.safe_load(content)
        except Exception as e:
            return json.dumps({"error": f"Failed to fetch URL {url_or_content}: {str(e)}"})
    else:
        try:
            spec_data = json.loads(url_or_content)
        except Exception:
            try:
                spec_data = yaml.safe_load(url_or_content)
            except Exception as e:
                return json.dumps({"error": f"Failed to parse input as JSON or YAML: {str(e)}"})

    if not isinstance(spec_data, dict):
        return json.dumps({"error": "Parsed spec is not a valid JSON/YAML object."})

    info = spec_data.get("info", {})
    title = info.get("title", "Java Service API")
    description = info.get("description", "")
    version = info.get("version", "1.0.0")

    servers = spec_data.get("servers", [])
    base_url = servers[0].get("url", "http://localhost:8080") if servers else "http://localhost:8080"

    paths = spec_data.get("paths", {})
    endpoints = []

    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, details in methods.items():
            if method.lower() not in ["get", "post", "put", "delete", "patch"]:
                continue
            if not isinstance(details, dict):
                continue

            op_id = details.get("operationId") or f"{method.lower()}_{re.sub(r'[^a-zA-Z0-9_]', '_', path)}"
            summary = details.get("summary") or details.get("description") or f"{method.upper()} {path}"
            
            params = []
            for p in details.get("parameters", []):
                if isinstance(p, dict):
                    params.append({
                        "name": p.get("name"),
                        "in": p.get("in"),
                        "required": p.get("required", False),
                        "description": p.get("description", ""),
                        "type": p.get("schema", {}).get("type", "string") if "schema" in p else p.get("type", "string")
                    })

            endpoints.append({
                "path": path,
                "method": method.upper(),
                "operation_id": op_id,
                "summary": summary,
                "parameters": params
            })

    result = {
        "title": title,
        "version": version,
        "description": description,
        "base_url": base_url,
        "total_endpoints": len(endpoints),
        "endpoints": endpoints
    }
    return json.dumps(result, indent=2)


def filter_endpoints(spec_json: str, exclude_patterns: str = "/actuator/*,/health*,/admin/*") -> str:
    """Filters out internal or unneeded API endpoints (such as /actuator/* or /health) from the spec.

    Args:
        spec_json: The JSON string output from ingest_swagger_input.
        exclude_patterns: Comma-separated glob patterns to exclude (e.g. '/actuator/*,/health*').

    Returns:
        Updated JSON string with filtered endpoints list.
    """
    try:
        data = json.loads(spec_json)
    except Exception as e:
        return json.dumps({"error": f"Invalid spec_json: {str(e)}"})

    patterns = [p.strip() for p in exclude_patterns.split(",") if p.strip()]
    original_endpoints = data.get("endpoints", [])
    filtered_endpoints = []

    for ep in original_endpoints:
        path = ep.get("path", "")
        excluded = any(fnmatch.fnmatch(path, pat) for pat in patterns)
        if not excluded:
            filtered_endpoints.append(ep)

    data["endpoints"] = filtered_endpoints
    data["total_endpoints"] = len(filtered_endpoints)
    data["filtered_count"] = len(original_endpoints) - len(filtered_endpoints)
    return json.dumps(data, indent=2)


def generate_mcp_server(spec_json: str, base_url: str = "", server_name: str = "java_app_mcp") -> str:
    """Generates a standalone Python MCP server script for the filtered endpoints with context protection & error handling.

    Args:
        spec_json: The JSON spec data containing title, base_url, and endpoints.
        base_url: Optional base URL override (e.g. http://localhost:8080 or https://staging.example.com).
        server_name: Identifier for the generated server (e.g. java_inventory_mcp).

    Returns:
        JSON object containing success status, generated script path, and tool list.
    """
    try:
        data = json.loads(spec_json)
    except Exception as e:
        return json.dumps({"error": f"Invalid spec_json: {str(e)}"})

    os.makedirs(SERVERS_DIR, exist_ok=True)
    target_base_url = base_url.strip() or data.get("base_url", "http://localhost:8080")
    sanitized_name = re.sub(r'[^a-zA-Z0-9_]', '_', server_name.lower())
    server_file_path = os.path.join(SERVERS_DIR, f"{sanitized_name}.py")

    endpoints = data.get("endpoints", [])
    tools_code = []

    for ep in endpoints:
        path = ep["path"]
        method = ep["method"]
        op_id = ep["operation_id"]
        summary = ep["summary"]
        params = ep.get("parameters", [])

        param_args = ["self"]
        query_params_dict = {}
        path_params_dict = {}

        for p in params:
            p_name = p.get("name")
            if not p_name:
                continue
            clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', p_name)
            p_type = "str"
            if p.get("type") in ["integer", "number"]:
                p_type = "int"
            elif p.get("type") == "boolean":
                p_type = "bool"

            if p.get("required"):
                param_args.append(f"{clean_name}: {p_type}")
            else:
                param_args.append(f"{clean_name}: {p_type} | None = None")

            if p.get("in") == "path":
                path_params_dict[p_name] = clean_name
            else:
                query_params_dict[p_name] = clean_name

        args_str = ", ".join(param_args)

        func_code = f"""
    def {op_id}({args_str}) -> str:
        \"\"\"{summary}
        
        Method: {method} Path: {path}
        \"\"\"
        target_path = "{path}"
        for p_key, p_val in {path_params_dict}.items():
            if locals().get(p_val) is not None:
                target_path = target_path.replace("{" + p_key + "}", str(locals()[p_val]))
        
        url = f"{{BASE_URL}}{{target_path}}"
        params = {{k: locals()[v] for k, v in {query_params_dict}.items() if locals().get(v) is not None}}
        
        try:
            req = urllib.request.Request(url, headers={{"Accept": "application/json", "User-Agent": "MCP-Agent/1.0"}}, method="{method}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read().decode("utf-8")
                # Payload truncation protection
                if len(data) > 4000:
                    return data[:4000] + "\\n... [Output truncated for context protection]"
                return data
        except Exception as err:
            return json.dumps({{"error": str(err), "url": url}})
"""
        tools_code.append(func_code)

    server_script = f"""# Generated MCP Server: {sanitized_name}
# Title: {data.get('title', 'Java Service')}
import json
import urllib.request
import sys

BASE_URL = "{target_base_url}"

class {sanitized_name.capitalize()}MCPServer:
    \"\"\"Standalone MCP Server for Java REST endpoints.\"\"\"
{''.join(tools_code)}

if __name__ == "__main__":
    print(f"MCP Server '{sanitized_name}' ready. Target Base URL: {{BASE_URL}}")
    print("Serving {len(endpoints)} tools.")
"""

    with open(server_file_path, "w") as f:
        f.write(server_script)

    return json.dumps({
        "status": "success",
        "server_name": sanitized_name,
        "server_file": server_file_path,
        "target_base_url": target_base_url,
        "total_tools": len(endpoints),
        "tools": [ep["operation_id"] for ep in endpoints]
    }, indent=2)


def manage_mcp_server(server_name: str, action: str) -> str:
    """Manages background MCP server processes (status, start, stop, restart).

    Args:
        server_name: Name of the server (e.g. java_inventory_mcp).
        action: One of 'status', 'start', 'stop', 'restart'.

    Returns:
        JSON response with the current process status and details.
    """
    sanitized_name = re.sub(r'[^a-zA-Z0-9_]', '_', server_name.lower())
    server_file_path = os.path.join(SERVERS_DIR, f"{sanitized_name}.py")

    pids = _load_pids()
    current_pid = pids.get(sanitized_name)

    is_running = False
    if current_pid:
        try:
            os.kill(current_pid, 0)
            is_running = True
        except OSError:
            is_running = False
            del pids[sanitized_name]
            _save_pids(pids)

    action = action.lower()

    if action == "status":
        return json.dumps({
            "server_name": sanitized_name,
            "status": "running" if is_running else "stopped",
            "pid": current_pid if is_running else None,
            "file_exists": os.path.exists(server_file_path)
        }, indent=2)

    elif action == "stop":
        if is_running and current_pid:
            try:
                os.kill(current_pid, signal.SIGTERM)
            except Exception:
                pass
            pids.pop(sanitized_name, None)
            _save_pids(pids)
            return json.dumps({"server_name": sanitized_name, "status": "stopped", "message": "Server stopped successfully."})
        return json.dumps({"server_name": sanitized_name, "status": "stopped", "message": "Server was not running."})

    elif action in ["start", "restart"]:
        if action == "restart" and is_running and current_pid:
            try:
                os.kill(current_pid, signal.SIGTERM)
            except Exception:
                pass
            pids.pop(sanitized_name, None)

        if not os.path.exists(server_file_path):
            return json.dumps({"error": f"Server script {server_file_path} does not exist. Generate it first."})

        proc = subprocess.Popen([sys.executable, server_file_path])
        pids[sanitized_name] = proc.pid
        _save_pids(pids)

        return json.dumps({
            "server_name": sanitized_name,
            "status": "running",
            "pid": proc.pid,
            "message": f"Server {action}ed successfully."
        }, indent=2)

    return json.dumps({"error": f"Unknown action '{action}'. Allowed: status, start, stop, restart."})


SUBAGENTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sub_agents"))


def create_automation_subagent(subagent_name: str, server_name: str, role_description: str = "") -> str:
    """Creates a dedicated automation Sub-Agent bound to a specific generated MCP server.

    Args:
        subagent_name: Name for the sub-agent (e.g. java_inventory_automation_agent).
        server_name: Name of the generated MCP server to bind (e.g. java_inventory_mcp).
        role_description: Detailed instruction describing what Java API automation tasks this sub-agent performs.

    Returns:
        JSON string confirming sub-agent creation and binding to the MCP server.
    """
    os.makedirs(SUBAGENTS_DIR, exist_ok=True)
    sanitized_agent_name = re.sub(r'[^a-zA-Z0-9_]', '_', subagent_name.lower())
    sanitized_server_name = re.sub(r'[^a-zA-Z0-9_]', '_', server_name.lower())

    config = {
        "name": sanitized_agent_name,
        "role": role_description or f"Automation agent bound to MCP server '{sanitized_server_name}'",
        "mcp_server": sanitized_server_name,
        "status": "active",
        "parent_agent": "root_agent"
    }

    subagent_file = os.path.join(SUBAGENTS_DIR, f"{sanitized_agent_name}.json")
    with open(subagent_file, "w") as f:
        json.dump(config, f, indent=2)

    return json.dumps({
        "status": "success",
        "subagent_name": sanitized_agent_name,
        "mcp_server_bound": sanitized_server_name,
        "subagent_config": subagent_file,
        "message": f"Sub-Agent '{sanitized_agent_name}' created successfully. Root agent will delegate Java application automation tasks to this sub-agent."
    }, indent=2)


# HARDCODED GCP Project ID string to prevent Agent Platform deployment project-number errors
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-02-2343073419d6"


def list_mcp_servers_from_db(status_filter: str = "") -> str:
    """Reads all registered MCP servers from the Firestore database collection 'mcp_servers'.

    Args:
        status_filter: Optional filter by server status (e.g. 'running', 'stopped', 'ready'). Leave empty to list all.

    Returns:
        JSON string containing the array of matching MCP server documents.
    """
    try:
        from google.cloud import firestore
        db = firestore.Client(project=FIRESTORE_PROJECT_ID)
        collection_ref = db.collection("mcp_servers")

        if status_filter:
            query = collection_ref.where("status", "==", status_filter.lower())
            docs = query.stream()
        else:
            docs = collection_ref.stream()

        results = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            results.append(data)

        return json.dumps({
            "status": "success",
            "total": len(results),
            "servers": results
        }, indent=2)
    except Exception as err:
        return json.dumps({"status": "error", "error": str(err)})


def save_mcp_server_to_db(
    server_name: str,
    title: str,
    base_url: str,
    status: str = "ready",
    total_tools: int = 0,
    target_app: str = "Java Spring Boot Application",
    environment: str = "dev"
) -> str:
    """Saves or updates an MCP server document in the Firestore database collection 'mcp_servers'.

    Args:
        server_name: Unique identifier/name of the MCP server (e.g. petstore_mcp).
        title: Descriptive title of the Java REST API.
        base_url: Target base URL of the running Java application.
        status: Status of the MCP server ('running', 'stopped', 'ready').
        total_tools: Number of tools exposed by the MCP server.
        target_app: Description of the target Java application.
        environment: Deployment environment ('dev', 'staging', 'prod').

    Returns:
        JSON string confirming document write to Firestore.
    """
    try:
        from google.cloud import firestore
        import datetime

        db = firestore.Client(project=FIRESTORE_PROJECT_ID)
        sanitized_id = re.sub(r'[^a-zA-Z0-9_]', '_', server_name.lower())

        doc_data = {
            "server_name": sanitized_id,
            "title": title,
            "base_url": base_url,
            "status": status.lower(),
            "total_tools": int(total_tools),
            "target_app": target_app,
            "environment": environment,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

        db.collection("mcp_servers").document(sanitized_id).set(doc_data, merge=True)

        return json.dumps({
            "status": "success",
            "id": sanitized_id,
            "message": f"MCP server '{sanitized_id}' saved to Firestore collection 'mcp_servers'."
        }, indent=2)
    except Exception as err:
        return json.dumps({"status": "error", "error": str(err)})


def get_mcp_server_from_db(server_name: str) -> str:
    """Reads full details and generated code of a specific registered MCP server from Firestore.

    Args:
        server_name: Unique identifier of the server (e.g. petstore_mcp).

    Returns:
        JSON string containing the document fields and tools list.
    """
    try:
        from google.cloud import firestore
        db = firestore.Client(project=FIRESTORE_PROJECT_ID)
        sanitized_id = re.sub(r'[^a-zA-Z0-9_]', '_', server_name.lower())
        doc = db.collection("mcp_servers").document(sanitized_id).get()
        if doc.exists:
            data = doc.to_dict()
            data["id"] = doc.id
            return json.dumps({"status": "success", "server": data}, indent=2)
        return json.dumps({"status": "error", "error": f"Server '{sanitized_id}' not found in Firestore."})
    except Exception as err:
        return json.dumps({"status": "error", "error": str(err)})


def execute_mcp_server_tool(server_name: str, endpoint_path: str, method: str = "GET", query_or_body_json: str = "{}") -> str:
    """Executes an API request against a registered MCP server's target base URL on behalf of sub-agents.

    Args:
        server_name: Name of the registered MCP server (e.g. petstore_mcp).
        endpoint_path: Path of the API endpoint (e.g. /pet/1 or /pet/findByStatus).
        method: HTTP method (GET, POST, PUT, DELETE).
        query_or_body_json: JSON string of parameters or body data (e.g. '{"status": "available"}').

    Returns:
        Response from the target service or error message.
    """
    full_url = ""
    try:
        from google.cloud import firestore
        import urllib.parse
        import urllib.request

        db = firestore.Client(project=FIRESTORE_PROJECT_ID)
        sanitized_id = re.sub(r'[^a-zA-Z0-9_]', '_', server_name.lower())
        doc = db.collection("mcp_servers").document(sanitized_id).get()
        if not doc.exists:
            return json.dumps({"error": f"MCP server '{sanitized_id}' not found in database."})
        
        server_data = doc.to_dict()
        base_url = server_data.get("base_url", "http://localhost:8080").rstrip("/")
        full_url = f"{base_url}/{endpoint_path.lstrip('/')}"

        params = json.loads(query_or_body_json) if query_or_body_json else {}
        
        if method.upper() == "GET" and params:
            query_str = urllib.parse.urlencode(params)
            full_url = f"{full_url}?{query_str}"
            req = urllib.request.Request(full_url, headers={"Accept": "application/json", "User-Agent": "MCP-Agent/1.0"}, method="GET")
        else:
            data_bytes = json.dumps(params).encode("utf-8") if params else None
            headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "MCP-Agent/1.0"}
            req = urllib.request.Request(full_url, data=data_bytes, headers=headers, method=method.upper())

        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
            if len(content) > 4000:
                content = content[:4000] + "\n... [Output truncated for context protection]"
            return json.dumps({"status": "success", "url": full_url, "response": content}, indent=2)
    except Exception as err:
        return json.dumps({"status": "error", "url": full_url, "error": str(err)})



