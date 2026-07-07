from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.auth_router import router as auth_router
from routers.case_router import router as case_router

app = FastAPI(title="LegalMind API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(case_router)


@app.get("/")
def root():
    return {"message": "Welcome to LegalMind API"}


@app.get("/health")
def health():
    return {"status": "ok"}
