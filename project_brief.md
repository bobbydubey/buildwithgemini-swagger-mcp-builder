# My agent: Java App Swagger-to-MCP Enterprise Automation Builder

**Author**: Anurag Dubey  
**Email**: anurag.dubey3@cognizant.com  

**One-liner**: A web-managed conversational agent that accepts Swagger/OpenAPI specs from running Java applications (e.g. Spring Boot `/v3/api-docs`), allows endpoint selection and environment configuration, automatically generates & tests MCP servers with built-in audit logging and payload safety, and provides a dashboard with user login to manage MCP server lifecycle (Running, Stopped, Restart).

### Input & Filtering Ingestion Step:
- Provide live Swagger/OpenAPI URL (e.g. `http://my-java-service:8080/v3/api-docs` or Springdoc UI endpoint) or upload a `swagger.json` / `openapi.yaml` file.
- Endpoint Filter & Selector: Filter out internal `/actuator/*` and management endpoints; selectively pick which REST APIs to expose as MCP tools.
- Multi-Environment Override: Set target base URLs for `dev`, `staging`, or `prod` environments.

### Tool coverage:
- Memory: Remembers target Java application specs, environment base URLs, authentication tokens (JWT/OAuth/Basic), generated MCP server configs, and user session state.
- Tools: 
  - `ingest_swagger_input`: Fetches, validates, and parses live Swagger/OpenAPI specs from running Java applications or uploaded files.
  - `filter_and_select_endpoints`: Filters out actuator/management routes and lets users pick active endpoints.
  - `generate_mcp_code`: Generates FastMCP / MCP SDK server code mapping Java REST endpoints into clean MCP tools with docstrings, payload truncation, and rate limiting.
  - `test_mcp_server`: Runs dry-run test invocations against target Java application endpoints.
  - `manage_mcp_lifecycle`: Tracks status (`running`, `stopped`), starts, stops, and restarts MCP server process instances.
  - `register_mcp_server`: Updates `mcp_config.json` and system process registry so agents can connect.
- Catalog/UI: Interactive Web UI with login, Swagger input & endpoint selection form, real-time MCP server status dashboard (Running/Stopped with Start/Stop/Restart controls), and A2UI endpoint tables.
- Image gen: Generates architectural diagrams showing Java App ↔ MCP Server ↔ AI Agent connectivity.
- Sandbox: Executes generated MCP server code and runs dry-run API tests in a secure sandbox.

### Enterprise Features Included:
- **Payload Truncation & Token Protection**: Wraps large JSON responses to protect LLM context windows.
- **Audit Logging & Telemetry**: Logs agent tool executions, parameters, caller identity, and response status via Cloud Trace / OpenTelemetry.
- **Rate Limiting & Timeout Controls**: Prevents AI agents from overloading background Java services.

Recommended for every project: memory, storage, tools, image generation, A2UI, web frontend (FastAPI proxy + Cloud Run)
Agent-specific / stretch: Java app OpenAPI auto-discovery, selective endpoint filtering, user login & auth, process lifecycle manager (start/stop/restart), code sandbox for generated MCP validation, Cloud Trace telemetry.
