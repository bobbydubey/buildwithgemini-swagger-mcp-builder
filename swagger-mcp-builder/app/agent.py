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

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.a2ui_utils import a2ui_callback
from app.tools import (
    create_automation_subagent,
    execute_mcp_server_tool,
    filter_endpoints,
    generate_mcp_server,
    get_mcp_server_from_db,
    ingest_swagger_input,
    list_mcp_servers_from_db,
    manage_mcp_server,
    save_mcp_server_to_db,
)

# Build A2UI System Prompt using A2uiSchemaManager version 0.8 & BasicCatalog 0.8
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

SYSTEM_INSTRUCTION = schema_manager.generate_system_prompt(
    role_description=(
        "You are the Root Manager Agent for Java Application Automation. "
        "Your primary role is ORCHESTRATION, MANAGEMENT, AND TOOL EXECUTION: "
        "1. Ingest OpenAPI/Swagger documentation from running Java applications (e.g. Spring Boot `/v3/api-docs`). "
        "2. Filter endpoints to remove internal actuator/health routes. "
        "3. Generate FastMCP server code containing tools for the Java application's REST APIs. "
        "4. Persist registered MCP server metadata to the Firestore database (`save_mcp_server_to_db`, `list_mcp_servers_from_db`, `get_mcp_server_from_db`). "
        "5. Create dedicated AUTOMATION SUB-AGENTS (using `create_automation_subagent`) bound to generated MCP servers. "
        "6. Manage background MCP server processes (`manage_mcp_server`). "
        "7. Execute API requests and data actions on registered MCP servers on behalf of user requests or sub-agents using `execute_mcp_server_tool`. "
        "8. MASTER ROUTER (AUTO MODE): When [AUTO ROUTER MODE] is specified or no specific sub-agent is manually locked, call `list_mcp_servers_from_db` to inspect registered MCP servers. Select the sub-agent matching the user's intent (e.g. fakeapi_mcp for books, petstore_mcp for pets, user_auth_mcp for users) and immediately invoke `execute_mcp_server_tool` using the standard REST endpoint path (for books: `/Books/ID`, for pets: `/pet/ID`, for auth: `/users/ID`). Execute the tool directly without asking for confirmation."
    ),
    workflow_description=(
        "Analyze the request and return structured UI (Cards, Columns, Rows, Text) when presenting MCP servers, Swagger endpoints, or process statuses. "
        "Step 1: `ingest_swagger_input` (Fetch & parse spec). "
        "Step 2: `filter_endpoints` (Exclude `/actuator/*`, `/health*`, `/admin/*`). "
        "Step 3: `generate_mcp_server` (Generate MCP server file with payload safety). "
        "Step 4: `save_mcp_server_to_db` (Persist MCP server record to Firestore). "
        "Step 5: `create_automation_subagent` (Instantiate dedicated Automation Sub-Agent). "
        "Step 6: `manage_mcp_server` (Start server and verify active status). "
        "Step 7: `execute_mcp_server_tool` (Run API request against target server)."
    ),
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=SYSTEM_INSTRUCTION,
    tools=[
        ingest_swagger_input,
        filter_endpoints,
        generate_mcp_server,
        save_mcp_server_to_db,
        list_mcp_servers_from_db,
        get_mcp_server_from_db,
        create_automation_subagent,
        manage_mcp_server,
        execute_mcp_server_tool,
    ],
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="swagger-mcp-builder",
)
