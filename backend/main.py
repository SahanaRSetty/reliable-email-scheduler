from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def root():
    return {"message": "Reliable Email Scheduler API is running"}