"""
Configuration Module.

This module defines global configuration settings.
Use the .env file to set secrets.
"""

import os
from enum import Enum
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# --- LLM Providers ---
GOOGLE_GENAI_API_KEY: Optional[str] = os.getenv("GOOGLE_GENAI_API_KEY")
OPENROUTER_API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")

# --- Search & Tools ---
SERP_API_KEY: Optional[str] = os.getenv("SERP_API_KEY")

# --- App Settings ---
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
DEFAULT_USER_AGENT: str = "MATE-Framework/1.0"
DEFAULT_TIMEOUT: int = 10
DB_FILENAME: str = "mate.db" # Default placeholder

# --- Model Configuration ---
MODEL_TEMPERATURE: float = 0.1
MAX_GENERATION_TURNS: int = 10
MAX_RETRIES: int = 3

# --- Definitions for Event Types ---
class EventType(str, Enum):
    """Event types yielded during agent execution."""
    AGENT_RESPONSE = "agent_response"
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    END = "end"

# --- Cost Tracking (Template) ---
# Define your model costs here to enable cost tracking in the Router.
COSTS: Dict[str, Dict[str, Any]] = {
    "gemini-2.5-flash": {"in": 0.0, "out": 0.0},
    "gpt-4o-mini": {"in": 0.0, "out": 0.0}
}