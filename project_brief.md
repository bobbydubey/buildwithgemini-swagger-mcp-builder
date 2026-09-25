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

### 🛠️ Setting Up Environment & Running Locally

You can run the application locally using either Vertex AI or local ADK execution with the **File-Based Storage Strategy (`filebased`)**. In file-based mode, all MCP server configurations are automatically loaded, managed, and persisted as `.json` files in the local `mcps/` directory.

#### 1. Unified Environment Setup (`.env`)

A **single unified `.env` file** located at the project root (`/.env`) configures both the **Frontend Web UI** and the **Backend Agent Engine / Sub-Agents**:

```env
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
AGENT_ENGINE_RESOURCE_NAME=projects/your-gcp-project-id/locations/us-central1/reasoningEngines/default
FIRESTORE_DATABASE=(default)
GCS_BUCKET_NAME=your-gcp-project-id-mcp-storage
```

*(Note: Both frontend `main.py` and backend `tools.py` automatically load this single `.env` file from the project root — eliminating the need for separate `.env` files).*

#### 2. Prerequisites & Dependencies

- Python 3.10+
- Activate virtual environment and install requirements:
  ```bash
  source swagger-mcp-builder/.venv/bin/activate
  pip install -r frontend/requirements.txt
  ```

#### 3. Step-by-Step Local Launch:

1. **Verify Local MCP Config Files**:
   Ensure the `mcps/` directory exists and contains seed `.json` files (e.g., `petstore_mcp.json`, `inventory_service_mcp.json`):
   ```bash
   mkdir -p mcps/
   ```

2. **Start the FastAPI Web Server**:
   From the project root directory, run:
   ```bash
   PYTHONUNBUFFERED=1 PYTHONPATH=. swagger-mcp-builder/.venv/bin/python -m uvicorn frontend.main:app --host 0.0.0.0 --port 8080
   ```

3. **Open the App in Browser**:
   Open **[http://localhost:8080](http://localhost:8080)**.

4. **Select Storage Strategy & Use Sub-Agents**:
   - In the left panel under **Storage Strategy**, select **`📁 File-Based Storage (mcps/)`** or **`☁️ GCP Firestore Storage`**.
   - The MCP Server Fleet sidebar will load all `.json` server files from the `mcps/` directory or Firestore.
   - Click **Start** / **Stop** on sub-agents (e.g., `petstore_mcp`, `fakeapi_mcp`) and send queries like `"find pet with ID 10"` or `"get book details for book ID 122"` to see rendered A2UI cards!

---

### ☁️ Step-by-Step GCP Production Deployment Guide

This section provides complete instructions for deploying the **Swagger MCP Builder** agent and Web UI to GCP without relying on specialized IDE tools or Antigravity extensions.

---

#### 1. Accounts & Service Account Roles Required

Before deploying, ensure the following identities and service accounts exist and have been granted appropriate IAM roles:

| Identity / Account | Purpose | Required IAM Roles |
| :--- | :--- | :--- |
| **Deployer Account** (`gcloud user` or CI/CD SA) | Executes infrastructure creation, Agent Engine deploy, and Cloud Run build | • `roles/aiplatform.admin`<br>• `roles/run.admin`<br>• `roles/iam.serviceAccountUser`<br>• `roles/datastore.owner`<br>• `roles/storage.admin`<br>• `roles/artifactregistry.admin` |
| **Compute Default SA** (`<PROJECT_NUMBER>-compute@developer.gserviceaccount.com`) | Identity used by the Cloud Run Web UI container to query Vertex AI Reasoning Engine, Firestore, and GCS | • `roles/aiplatform.user`<br>• `roles/datastore.owner` (or `roles/datastore.user`)<br>• `roles/storage.objectAdmin` |
| **Agent Engine Runtime SA** (`service-<PROJECT_NUMBER>@gcp-sa-aiplatform-re.iam.gserviceaccount.com`) | Managed identity executed by GCP Vertex AI Agent Engine for sub-agent tools | • `roles/aiplatform.user`<br>• `roles/datastore.owner`<br>• `roles/storage.objectAdmin` |

---

#### 2. Architecture & Tooling Mapping (Standard GCP vs. Antigravity)

| Architectural Component | Standard GCP / CLI Method (No Antigravity) | Antigravity IDE Method |
| :--- | :--- | :--- |
| **Agent Runtime Platform** | GCP Vertex AI Agent Engine (`ReasoningEngine`) | Antigravity Agent Engine |
| **Agent Deployment Command** | `agents-cli deploy --project $PROJECT_ID --region us-central1` | `agy deploy` / Antigravity Agent deploy |
| **Frontend Web Chat UI** | GCP Cloud Run (`gcloud run deploy --source ./frontend`) | Built-in A2UI preview / Cloud Run proxy |
| **Database & Persistence** | GCP Firestore Native Database (`(default)`) | Firestore Native Database |
| **File / Spec Artifact Storage** | Google Cloud Storage Bucket (`gs://$PROJECT_ID-mcp-storage`) | GCS Bucket |
| **Authentication & IAM** | Application Default Credentials (ADC) + GCP IAM Policy Bindings | ADC / OAuth device flow |

---

#### 3. Step-by-Step GCP Deployment Commands

##### Step 1: Enable GCP Services & Set Environment
```bash
export PROJECT_ID="qwiklabs-gcp-01-93bba37b472a"
export REGION="us-central1"
export BUCKET_NAME="${PROJECT_ID}-mcp-storage"

# Set active gcloud project
gcloud config set project $PROJECT_ID

# Enable required GCP APIs
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com
```

##### Step 2: Create Firestore Database & GCS Bucket
```bash
# Create default Firestore Native Database
gcloud firestore databases create --location=$REGION --type=firestore-native || true

# Create GCS Bucket for MCP server storage
gcloud storage buckets create gs://$BUCKET_NAME --location=$REGION || true
```

##### Step 3: Populate `.env` Configuration File
Create/update `.env` in `swagger-mcp-builder/.env` and `frontend/.env`:
```env
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=qwiklabs-gcp-01-93bba37b472a
GOOGLE_CLOUD_LOCATION=us-central1
FIRESTORE_DATABASE=(default)
GCS_BUCKET_NAME=qwiklabs-gcp-01-93bba37b472a-mcp-storage
```

##### Step 4: Seed Initial Firestore Database Collection
```bash
python swagger-mcp-builder/seed_firestore.py
```

##### Step 5: Grant IAM Policy Bindings to Service Accounts
```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

# Grant Datastore & Storage permissions to Cloud Run Compute SA
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/datastore.owner"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud storage buckets add-iam-policy-binding gs://$BUCKET_NAME \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# Grant Datastore & Storage permissions to Vertex AI Agent Engine SA
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
  --role="roles/datastore.owner"

gcloud storage buckets add-iam-policy-binding gs://$BUCKET_NAME \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

##### Step 6: Deploy Agent Backend to Vertex AI Agent Engine
```bash
cd swagger-mcp-builder
pip install google-agents-cli
agents-cli deploy --project $PROJECT_ID --region $REGION
```
*Take note of the returned `Agent Runtime ID` / `AGENT_ENGINE_RESOURCE_NAME` (e.g. `projects/931167782693/locations/us-central1/reasoningEngines/6179338361229017088`).*

##### Step 7: Deploy Web Chat UI Frontend to GCP Cloud Run
```bash
cd ..
gcloud run deploy swagger-mcp-builder-ui \
  --source ./frontend \
  --region $REGION \
  --project $PROJECT_ID \
  --allow-unauthenticated \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},AGENT_ENGINE_RESOURCE_NAME=projects/931167782693/locations/us-central1/reasoningEngines/6179338361229017088,FIRESTORE_DATABASE=(default),GCS_BUCKET_NAME=${BUCKET_NAME}"
```

##### Step 8: Verify Live Service Deployment
Test the live Cloud Run endpoint and Firestore integration:
```bash
curl -s "https://swagger-mcp-builder-ui-${PROJECT_NUMBER}.${REGION}.run.app/api/mcps?strategy=gcp"
```
