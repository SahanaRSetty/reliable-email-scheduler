from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.emails import router as email_router
from app.core.config import settings
from app.core.database import engine
from app.core.redis import redis_client
from app.worker.tasks import test_task

app = FastAPI(
    title="Reliable Email Scheduler API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
    session_cookie="reliable_email_session",
    max_age=60 * 60 * 24 * 7,
    same_site="lax",
    https_only=False,
)


app.include_router(email_router)
app.include_router(auth_router)

@app.get("/")
def root():
    return {
        "message": "Reliable Email Scheduler API is running"
    }


@app.get("/health/database")
def database_health():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        value = result.scalar()

    return {
        "database": "connected",
        "test": value,
    }

@app.get("/health/redis")
def redis_health():
    redis_client.ping()

    return {
        "redis": "connected",
    }

@app.post("/test/celery")
def test_celery():
    task = test_task.delay("Hello from FastAPI")

    return {
        "message": "Task submitted",
        "task_id": task.id,
    }