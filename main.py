"""
Willow & Leather - Cricket Management Simulation API
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.api.career import router as career_router
from app.api.auction import router as auction_router
from app.api.season import router as season_router
from app.api.match import router as match_router

# Initialize FastAPI app
app = FastAPI(
    title="Willow & Leather",
    description="Cricket Management Simulation Game API",
    version="0.1.0",
)

# CORS origins - configurable via environment variable
default_origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
]

# Add custom origins from environment (comma-separated)
extra_origins = os.environ.get("CORS_ORIGINS", "")
if extra_origins:
    default_origins.extend([o.strip() for o in extra_origins.split(",") if o.strip()])

# CORS middleware for mobile/web frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=default_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(career_router, prefix="/api")
app.include_router(auction_router, prefix="/api")
app.include_router(season_router, prefix="/api")
app.include_router(match_router, prefix="/api")


@app.on_event("startup")
def startup_event():
    """Initialize database on startup"""
    init_db()


@app.get("/")
def root():
    """Health check endpoint"""
    return {
        "name": "Willow & Leather API",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/api/health")
def health_check():
    """API health check"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
