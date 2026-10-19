import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Horizon Veridian WorkOS API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        frontend_url,
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy", "service": "workos"}


@app.get("/api/health", tags=["Health"])
async def api_health():
    return {"status": "healthy", "service": "workos"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("WORKOS_PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
