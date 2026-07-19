from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.auth_router import router as auth_router
from routers.case_router import router as case_router
from routers.review_router import router as review_router
from routers.users_router import router as users_router

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
app.include_router(review_router)
app.include_router(users_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Welcome to LegalMind API"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
