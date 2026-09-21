"""AWS Lambda entry point. Wraps the FastAPI app (app/main.py) with Mangum
so API Gateway HTTP API v2 events reach it as ASGI requests. Not used
locally: Docker Compose / plain uvicorn import app.main:app directly.
"""

from mangum import Mangum

from app.main import app

handler = Mangum(app)
