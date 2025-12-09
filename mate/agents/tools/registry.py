"""
Tool Registry Module.

This module maps string tool names (requested by LLMs) to the actual Python
function implementations. It acts as the central dispatch for tool execution.
"""

from typing import Dict, Any, Callable, Awaitable
from mate.core.logger import logger
from mate.agents.tools import geocoding, trail, meteo, web

# Map tool names to Async Functions
TOOL_REGISTRY: Dict[str, Callable[..., Awaitable[Any]]] = {
    # Navigation
    "geocode": geocoding.geocode,
    "reverse_geocode": geocoding.reverse_geocode,
    
    # Trail
    "execute_trail_query": trail.execute_trail_query,
    "get_trail_count": trail.get_trail_count,
    "get_trail_details_by_id": trail.get_trail_details_by_id,
    "get_comments": trail.get_comments,
    "get_waypoints": trail.get_waypoints,
    
    # Meteo
    "get_daily_forecast": meteo.get_daily_forecast,
    "get_hourly_forecast": meteo.get_hourly_forecast,
    "get_sunrise_sunset_times": meteo.get_sunrise_sunset_times,
    
    # Web
    "search_web_for_hiking_info": web.search_web_for_hiking_info,
}


async def execute_tool(name: str, args: Dict[str, Any]) -> Any:
    """
    Dispatches tool calls to the appropriate function asynchronously.

    Args:
        name (str): The name of the tool to execute.
        args (Dict[str, Any]): The arguments to pass to the tool.

    Returns:
        Any: The result of the tool execution.

    Raises:
        ValueError: If the tool name is not found in the registry.
        Exception: Propagates any exception raised by the tool function.
    """
    if name not in TOOL_REGISTRY:
        error_msg = f"Tool '{name}' not found in registry."
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    func = TOOL_REGISTRY[name]
    return await func(**args)