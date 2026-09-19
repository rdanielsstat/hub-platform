from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.seed import seed
from app.db.store import store
from app.routers import auth, health, notes, projects

app = FastAPI(title="Hub API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(notes.router)

seed(store)
