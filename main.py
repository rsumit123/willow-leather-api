"""
Willow & Leather - Cricket Management Simulation API
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.api.career import router as career_router
from app.api.auction import router as auction_router
from app.api.season import router as season_router

# Initialize FastAPI app
app = FastAPI(
    title="Willow & Leather",
    description="Cricket Management Simulation Game API",
    version="0.1.0",
)

# CORS middleware for mobile/web frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(career_router, prefix="/api")
app.include_router(auction_router, prefix="/api")
app.include_router(season_router, prefix="/api")


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
