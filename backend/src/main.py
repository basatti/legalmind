from fastapi import FastAPI

from routers.case_router import router as case_router

app = FastAPI(title="LegalMind API")
app.include_router(case_router)


@app.get("/")
def root():
    return {"message": "Welcome to LegalMind API"}


@app.get("/health")
def health():
    return {"status": "ok"}
