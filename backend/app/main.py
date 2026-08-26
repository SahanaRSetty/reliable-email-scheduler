from fastapi import FastAPI
from sqlalchemy import text

from app.core.database import engine


app = FastAPI(
    title="Reliable Email Scheduler API",
    version="0.1.0",
)


@app.get("/")
def root():
    return {"message": "Reliable Email Scheduler API is running"}


@app.get("/health/database")
def database_health():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        value = result.scalar()

    return {
        "database": "connected",
        "test": value,
    }