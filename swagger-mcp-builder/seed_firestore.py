import os
import datetime
from google.cloud import firestore
from dotenv import load_dotenv

# Load GCP project dynamically from .env
load_dotenv()
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), ".env")))
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")))

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
DATABASE_ID = os.environ.get("FIRESTORE_DATABASE", "(default)")
db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID) if PROJECT_ID else firestore.Client()

COLLECTION_NAME = "mcp_servers"

seed_data = [
    {
        "id": "petstore_mcp",
        "server_name": "petstore_mcp",
        "title": "Swagger Petstore API",
        "base_url": "https://petstore.swagger.io/v2",
        "status": "running",
        "total_tools": 20,
        "target_app": "Java Spring Boot Petstore Application",
        "environment": "dev",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    },
    {
        "id": "inventory_service_mcp",
        "server_name": "inventory_service_mcp",
        "title": "Enterprise Java Inventory Management Service",
        "base_url": "http://inventory.internal.company.com:8080/v3/api-docs",
        "status": "ready",
        "total_tools": 14,
        "target_app": "Java Quarkus Inventory Service",
        "environment": "staging",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    },
    {
        "id": "user_auth_mcp",
        "server_name": "user_auth_mcp",
        "title": "Java Spring Security Auth & User Service",
        "base_url": "http://auth.internal.company.com:8081",
        "status": "stopped",
        "total_tools": 8,
        "target_app": "Java Spring Security Microservice",
        "environment": "prod",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    },
    {
        "id": "fakeapi_mcp",
        "server_name": "fakeapi_mcp",
        "title": "Fake REST API Gateway",
        "base_url": "https://fakerestapi.azurewebsites.net",
        "status": "ready",
        "total_tools": 12,
        "target_app": "Java Spring Boot Application",
        "environment": "dev",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    },
    {
        "id": "payment_service_mcp",
        "server_name": "payment_service_mcp",
        "title": "Payment Gateway API",
        "base_url": "https://payment.company.com/api/v1",
        "status": "stopped",
        "total_tools": 14,
        "target_app": "Java Spring Boot Payment Service",
        "environment": "dev",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
]

def seed_database():
    print(f"Seeding Firestore collection '{COLLECTION_NAME}' in project '{PROJECT_ID}'...")
    collection_ref = db.collection(COLLECTION_NAME)
    for item in seed_data:
        doc_id = item["id"]
        collection_ref.document(doc_id).set(item)
        print(f"  ✓ Seeded document: {doc_id} -> {item['title']}")
    print("Firestore database seeding completed successfully!")

if __name__ == "__main__":
    seed_database()
