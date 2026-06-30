from fastapi import FastAPI
from models import Feedback

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Welcome to LegalMind API"}