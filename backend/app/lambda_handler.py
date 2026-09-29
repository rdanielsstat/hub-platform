"""AWS Lambda entry point. Wraps the FastAPI app (app/main.py) with Mangum
so API Gateway HTTP API v2 events reach it as ASGI requests. Not used
locally: Docker Compose / plain uvicorn import app.main:app directly.

CloudFront forwards /api/* to API Gateway with the full path, so the
Lambda sees /api/projects while routes are registered at /projects.
API_BASE_PATH (set to /api in the deployment) tells Mangum to strip
that prefix before routing, leaving the API contract unchanged.
"""

import os

from mangum import Mangum

from app.main import app

handler = Mangum(app, api_gateway_base_path=os.getenv("API_BASE_PATH", "/"))
