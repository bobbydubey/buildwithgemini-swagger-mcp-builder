# My agent: Java App Swagger-to-MCP Enterprise Automation Builder

**Author**: Anurag Dubey  
**Email**: dubey.anurag@outlook.com  

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

---

### 🛠️ Running Locally (File-Based Storage Strategy)

You can run the application locally without requiring a connection to GCP Firestore by using the **File-Based Storage Strategy (`filebased`)**. In file-based mode, all MCP server configurations are automatically loaded, managed, and persisted as `.json` files in the local `mcps/` directory.

#### Prerequisites
- Python 3.10+
- Install dependencies:
  ```bash
  pip install -r frontend/requirements.txt
  ```

#### Step-by-Step Local Launch:

1. **Verify Local MCP Config Files**:
   Ensure the `mcps/` directory exists and contains seed `.json` files (e.g., `petstore_mcp.json`, `inventory_service_mcp.json`):
   ```bash
   mkdir -p mcps/
   ```

2. **Start the FastAPI Web App & Proxy**:
   From the project root directory, run:
   ```bash
   python3 -m uvicorn frontend.main:app --host 0.0.0.0 --port 8080 --reload
   ```

3. **Open the App in Browser**:
   Open **[http://localhost:8080](http://localhost:8080)**.

4. **Select File-Based Storage Strategy**:
   - In the left panel under **Storage Strategy**, select **`📁 File-Based Storage (mcps/)`** from the dropdown menu.
   - The MCP Server Fleet sidebar will load all `.json` server files from the `mcps/` directory.
   - Sub-agent **Start** and **Stop** buttons will update server statuses directly inside the local `mcps/*.json` files.
