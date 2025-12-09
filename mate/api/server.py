import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Dict, List

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from mate.orchestration.router import MATE

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("MATE API")


# -------------------------
# Session Management
# -------------------------

class SessionManager:
    """
    Manages active MATE instances for different chat sessions.
    Stores instances in-memory.
    """
    def __init__(self):
        # Key: "user_id:chat_id", Value: { "instance": MATE, "last_accessed": timestamp }
        self._sessions: Dict[str, Dict] = {}
        # Configuration
        self.default_api = "gemini"
        self.default_model = "gemini-2.5-flash"
        self.session_timeout = 3600  # 1 hour timeout

    def get_or_create_session(self, user_id: str, chat_id: str) -> MATE:
        """Retrieves an existing MATE instance or creates a new one."""
        session_key = f"{user_id}:{chat_id}"
        
        # Cleanup old sessions occasionally
        if len(self._sessions) > 100:
            self._cleanup_stale_sessions()

        if session_key in self._sessions:
            logger.info(f"Resuming session: {session_key}")
            self._sessions[session_key]["last_accessed"] = time.time()
            return self._sessions[session_key]["instance"]

        # Create new instance
        logger.info(f"Creating new session: {session_key}")
        new_instance = MATE(api=self.default_api, model=self.default_model)
        
        self._sessions[session_key] = {
            "instance": new_instance,
            "last_accessed": time.time()
        }
        return new_instance

    def reset_session(self, user_id: str, chat_id: str) -> bool:
        """Resets the conversation history for a specific session."""
        session_key = f"{user_id}:{chat_id}"
        if session_key in self._sessions:
            self._sessions[session_key]["instance"].reset_conversation()
            self._sessions[session_key]["last_accessed"] = time.time()
            return True
        return False

    def _cleanup_stale_sessions(self):
        """Removes sessions inactive for longer than session_timeout."""
        now = time.time()
        keys_to_delete = [
            k for k, v in self._sessions.items() 
            if now - v["last_accessed"] > self.session_timeout
        ]
        for k in keys_to_delete:
            del self._sessions[k]
        logger.info(f"Cleaned up {len(keys_to_delete)} stale sessions.")


# Global Session Manager
session_manager = SessionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager."""
    logger.info("Initializing API Server...")
    # Any startup logic (db checks, etc) goes here
    yield
    logger.info("Shutting down API Server...")


# Initialize FastAPI app
app = FastAPI(
    title="Multi-Agent Trail Explorer API",
    description="AI-powered hiking and outdoor trail assistant",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create a router for database endpoints
db_router = APIRouter(prefix="/api/db", tags=["database"])
app.include_router(db_router)


# -------------------------
# Request/Response Models
# -------------------------

class QueryRequest(BaseModel):
    """Request model for queries."""
    query: str = Field(..., description="User's natural language query", min_length=1, max_length=1000)
    latitude: float = Field(..., description="User's latitude", ge=-90, le=90)
    longitude: float = Field(..., description="User's longitude", ge=-180, le=180)
    user_id: str = Field(..., description="Unique user identifier", min_length=1, max_length=50)
    chat_id: str = Field(..., description="Unique chat identifier", min_length=1, max_length=50)

    @field_validator('query')
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        if not v or v.strip() == "":
            raise ValueError("Query cannot be empty")
        return v.strip()

class HealthResponse(BaseModel):
    status: str
    message: str

class ConversationAction(BaseModel):
    user_id: str = Field(..., description="User identifier")
    chat_id: str = Field(..., description="Chat identifier")

class TrailSummary(BaseModel):
    trail_id: str
    title: str
    # Add more as needed

class TrailsResponse(BaseModel):
    trails: List[TrailSummary]
    count: int


# -------------------------
# API Endpoints
# -------------------------

@app.get("/", response_model=HealthResponse)
async def root():
    return {
        "status": "online",
        "message": "Multi-Agent Trail Explorer API is running"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {
        "status": "healthy",
        "message": f"System ready. Active sessions: {len(session_manager._sessions)}"
    }


@app.post("/api/query-stream")
async def query_stream(request: QueryRequest):
    """
    Stream the system's response for a specific chat session.
    Automatically creates a new session if (user_id, chat_id) is new.
    """
    
    # 1. Get the specific MATE instance for this session
    try:
        system_instance = session_manager.get_or_create_session(request.user_id, request.chat_id)
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail="Failed to initialize chat session")

    # 2. Define the generator
    async def event_stream():
        try:
            # Note: system_instance.stream is async
            async for event in system_instance.stream(
                user_query=request.query,
                user_coords=(request.latitude, request.longitude),
                user_id=request.user_id
            ):
                # Convert event to SSE format
                yield f"data: {json.dumps(event)}\n\n"
                await asyncio.sleep(0) # Not strictly necessary if underlying stream yields control, but good safety
        except Exception as e:
            logger.error(f"Streaming error for {request.user_id}:{request.chat_id}: {e}", exc_info=True)
            error_event = {"type": "error", "message": "Error during streaming"}
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/reset")
async def reset_conversation(request: ConversationAction):
    """
    Reset conversation history for a specific chat session.
    """
    success = session_manager.reset_session(request.user_id, request.chat_id)
    
    if success:
        logger.info(f"Conversation reset for {request.user_id}:{request.chat_id}")
        return {
            "status": "success",
            "message": "Conversation history cleared"
        }
    else:
        # If session doesn't exist, we can just say success (idempotent) or create it empty
        logger.info(f"Reset called for non-existent session {request.user_id}:{request.chat_id}")
        return {
            "status": "success",
            "message": "Session created/cleared"
        }


# -------------------------
# Database Endpoints
# -------------------------

@db_router.get("/trails_in_bbox", response_model=TrailsResponse)
async def get_trails_in_bbox(
    min_lat: float = Query(..., description="Minimum latitude"),
    min_lon: float = Query(..., description="Minimum longitude"),
    max_lat: float = Query(..., description="Maximum latitude"),
    max_lon: float = Query(..., description="Maximum longitude"),
):
    """
    Fetch trail details for trails inside a bounding box.
    """
    logger.warning("get_trails_in_bbox is not implemented in this abstract framework.")
    
    # TODO: Implement Spatial SQL query here matching your database
    
    return TrailsResponse(trails=[], count=0)


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


if __name__ == "__main__":
    uvicorn.run(
        "mate.api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )