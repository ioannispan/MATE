"""
Database Core Module (Abstract).

This module defines the interface for database interactions.
Implement `get_trails_to_show` to format your data for the UI/API response.
"""

from typing import List, Dict, Any
from mate.core.logger import logger

async def get_db_connection(db_path: str = ""):
    """
    Placeholder for database connection factory.
    Implement this using aiosqlite, asyncpg, or your preferred driver.
    """
    raise NotImplementedError("Configure your DB connection in mate/core/database.py")

async def get_user_profile_data(user_id: str) -> Dict[str, Any]:
    """
    Mock user profile. Connect to your Auth system in production.
    """
    # Mock return to allow system to start
    return {
        "user_id": user_id,
        "display_name": f"Guest {user_id[-4:]}"
    }

async def get_trails_to_show(trail_ids: List[str], order_by: str) -> List[Dict[str, Any]]:
    """
    Hydrate trail IDs into full objects for the API response.
    """
    logger.warning("get_trails_to_show is not implemented. Returning empty list.")
    # TODO: Fetch real data based on IDs
    return []