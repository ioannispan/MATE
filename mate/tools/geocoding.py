"""
Navigation Tool Implementation (Template).
"""

from typing import Dict, Any
from mate.core.logger import logger

async def geocode(location: str, max_results: int = 3) -> Dict[str, Any]:
    """
    Convert a place name to coordinates.
    """
    logger.info(f"Mock Geocoding for: {location}")
    
    # TODO: Connect to Google Maps / Mapbox / OpenCage
    
    # Returning mock data so the system doesn't crash during initial testing
    return {
        "status": "ambiguous",
        "message": "Mock Data - Implement real geocoding in tools/navigation.py",
        "candidates": [
            {"name": "Mock Location A", "latitude": 40.7128, "longitude": -74.0060},
            {"name": "Mock Location B", "latitude": 34.0522, "longitude": -118.2437}
        ]
    }

async def reverse_geocode(latitude: float, longitude: float) -> Dict[str, Any]:
    """
    Convert coordinates to a place name.
    """
    return {
        "status": "found",
        "candidates": [f"Mock Address at {latitude}, {longitude}"]
    }