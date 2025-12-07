"""
Tool Definitions Module.

This module contains the JSON schemas for all tools available to the agents.
These schemas are compatible with Google Gemini and OpenAI function calling formats.
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

# Geocoding Agent Tools
GEOCODING_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "reverse_geocode",
        "description": "Resolve GPS (lat, lon) to a descriptive place name/address.",
        "parameters": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number"},
                "longitude": {"type": "number"}
            },
            "required": ["latitude", "longitude"]
        }
    },
    {
        "name": "geocode",
        "description": "Resolve place name to GPS coordinates (lat, lon). Returns bounding box and ambiguity status.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "Place name (e.g. 'Mount Olympus')."}
            },
            "required": ["location"]
        }
    }
]

# Trail Agent Tools
TRAIL_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "execute_trail_query",
        "description": "Primary Search. Finds trails matching criteria and updates the 'Active Context' with these IDs for subsequent analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "where": {"type": "string", "description": "SQL WHERE clause (no 'WHERE') using '?' placeholders."},
                "sql_params": {"type": "array", "items": {}, "description": "Values for placeholders."},
                "order_by": {"type": "string", "description": "SQL ORDER BY clause (no 'ORDER BY')."},
                "limit": {"type": "integer", "default": 20}
            },
            "required": ["where", "sql_params"]
        }
    },
    {
        "name": "get_trail_count",
        "description": "Quick integer count of trails matching criteria. Does not update Active Context.",
        "parameters": {
            "type": "object",
            "properties": {
                "where": {"type": "string"},
                "sql_params": {"type": "array", "items": {}}
            },
            "required": ["where", "sql_params"]
        }
    },
    {
        "name": "get_trail_details_by_id",
        "description": "Fetches stats/columns for the given trails.",
        "parameters": {
            "type": "object",
            "properties": {
                "trail_ids": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "List of specific trail_ids to fetch details."
                },
                "fields": {
                    "type": "array", 
                    "items": {"type": "string"}, 
                    "description": "Columns to fetch."
                }
            },
            "required": ["trail_ids", "fields"]
        }
    },
    {
        "name": "get_comments",
        "description": "Fetches user reviews/ratings for the given trails.",
        "parameters": {
            "type": "object",
            "properties": {
                "trail_ids": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "List of specific trail_ids to fetch comments."
                },
            },
            "required": ["trail_ids"]
        }
    },
    {
        "name": "get_waypoints",
        "description": "Fetches POIs (waterfalls, summits) for the given trails.",
        "parameters": {
            "type": "object",
            "properties": {
                "trail_ids": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "List of specific trail_ids to fetch waypoints."
                },
            },
            "required": ["trail_ids"]
        }
    }
]


# Meteo Agent Tools
METEO_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_daily_forecast",
        "description": "Daily summaries (Temp/Rain). Max 16 days.",
        "parameters": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
                "start_date": {"type": "string", "format": "date"},
                "end_date": {"type": "string", "format": "date"},
                "variables": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["latitude", "longitude", "start_date", "end_date"]
        }
    },
    {
        "name": "get_hourly_forecast",
        "description": "Granular hourly data. Use only for specific timing queries.",
        "parameters": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
                "start_date": {"type": "string", "format": "date"},
                "end_date": {"type": "string", "format": "date"}
            },
            "required": ["latitude", "longitude", "start_date", "end_date"]
        }
    },
    {
        "name": "get_sunrise_sunset_times",
        "description": "Get daylight hours.",
        "parameters": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
                "start_date": {"type": "string", "format": "date"},
                "end_date": {"type": "string", "format": "date"}
            },
            "required": ["latitude", "longitude", "start_date", "end_date"]
        }
    }
]

# Web Agent Tools
WEB_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "search_web_for_hiking_info",
        "description": "Search web for factual info, regulations, gear. NO TRAIL ROUTES.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "3-8 word factual query."},
                "max_results": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    }
]