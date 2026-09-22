from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import stories, nodes

app = FastAPI(title="Story Continuation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stories.router, prefix="/stories", tags=["stories"])
app.include_router(nodes.router, prefix="/nodes", tags=["nodes"])

@app.get("/health")
def health():
    return {"status": "ok"}