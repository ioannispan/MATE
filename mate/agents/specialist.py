"""
Specialist Agents Module.

This module defines the concrete implementations of the Specialist Agents.
Each agent inherits from BaseAgent and is initialized with its specific
prompt and toolset.
"""

from mate.agents.base_agent import BaseAgent
from mate.agents.tools.definitions import (
    TRAIL_TOOLS, 
    GEOCODING_TOOLS, 
    METEO_TOOLS, 
    WEB_TOOLS
)
from mate.agents.prompts import (
    TRAIL_AGENT_PROMPT, 
    GEOCODING_AGENT_PROMPT, 
    METEO_AGENT_PROMPT, 
    WEB_AGENT_PROMPT
)


class GeocodingAgent(BaseAgent):
    """
    Agent responsible for Geocoding and Location resolution.
    """
    def __init__(self, api: str, model: str):
        super().__init__(
            api=api, 
            model=model, 
            name="GeocodingAgent", 
            system_prompt=GEOCODING_AGENT_PROMPT, 
            tool_declarations=GEOCODING_TOOLS
        )


class TrailAgent(BaseAgent):
    """
    Agent responsible for Database queries regarding trails and statistics.
    """
    def __init__(self, api: str, model: str):
        super().__init__(
            api=api, 
            model=model, 
            name="TrailAgent", 
            system_prompt=TRAIL_AGENT_PROMPT, 
            tool_declarations=TRAIL_TOOLS
        )


class MeteoAgent(BaseAgent):
    """
    Agent responsible for Weather and Sun phase information.
    """
    def __init__(self, api: str, model: str):
        super().__init__(
            api=api, 
            model=model, 
            name="MeteoAgent", 
            system_prompt=METEO_AGENT_PROMPT, 
            tool_declarations=METEO_TOOLS
        )


class WebAgent(BaseAgent):
    """
    Agent responsible for general internet knowledge (Safety, Regulations, etc.).
    """
    def __init__(self, api: str, model: str):
        super().__init__(
            api=api, 
            model=model, 
            name="WebAgent", 
            system_prompt=WEB_AGENT_PROMPT, 
            tool_declarations=WEB_TOOLS
        )