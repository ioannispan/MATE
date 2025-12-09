"""
Router Tool Definitions Module.

This module contains the JSON schemas for all tools available to the router.
These schemas are compatible with the Google Gemini function calling format.
"""

from typing import List, Dict, Any

# Router Tool
ROUTER_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "handoff_to_agent",
        "description": "Delegates the current task to a specialist agent. Call this when you need specific data (trails, weather, location, web info) before answering the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "enum": ["GeocodingAgent", "TrailAgent", "MeteoAgent", "WebAgent"],
                    "description": "The specific specialist to activate."
                },
                "instruction": {
                    "type": "string",
                    "description": "The full context and specific prompt for the specialist agent. Include relevant coordinates, dates, and user intent. Example: 'Find easy loop trails near coordinates 40.7, -74.0.' instead of just 'Find trails'."
                }
            },
            "required": ["agent_name", "instruction"]
        }
    }
]