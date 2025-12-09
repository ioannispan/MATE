"""
Router Module (The Orchestrator).

This module contains the MATE class, which acts as the central hub (Router)
for the Multi-Agent System. It manages the conversation state asynchronously, 
delegates tasks to specialist agents, and streams the final response.
"""

import json
import datetime
import time
from typing import AsyncGenerator, List, Dict, Any, Tuple

# API Clients
from google import genai
from google.genai import types
from openai import AsyncOpenAI

from mate.core.logger import logger
from mate.core.database import get_user_profile_data, get_trails_to_show
from mate.core.utils import extract_json_from_text, call_with_retry, transform_tool_declarations
from mate.config import (
    EventType,
    GOOGLE_GENAI_API_KEY,
    OPENROUTER_API_KEY,
    MODEL_TEMPERATURE,
    MAX_GENERATION_TURNS,
    MAX_RETRIES,
    COSTS
)

# Agent Imports
from mate.orchestration.prompt import ROUTER_PROMPT
from mate.agents.specialist import GeocodingAgent, TrailAgent, MeteoAgent, WebAgent
from mate.orchestration.tool_definitions import ROUTER_TOOLS


class TokenCounter:
    def __init__(self, model):

        # Token accumulators for a specific prompt (over turns)
        self.prompt_input_tokens = 0
        self.prompt_output_tokens = 0

        # Cost accumulators for a specific prompt (over turns)
        self.prompt_input_cost = 0
        self.prompt_output_cost = 0

        # Token accumulators for the whole converstation
        self.conv_input_tokens = 0
        self.conv_output_tokens = 0        

        # Rates
        self.costs = COSTS.get(model, {})        

    def _compute_cost(self, tokens: int, output: bool = False) -> float:
        """
        Compute turn cost in USD using progressive tiered pricing.
        """
        if not self.costs:
            return 0.0
        
        rates = self.costs.get("out_rates") if output else self.costs.get("in_rates")
        thresholds = self.costs.get("out_thresholds") if output else self.costs.get("in_thresholds")

        # Case 1: Flat Rate
        if isinstance(rates, (int, float)):
            return (tokens / 1_000_000) * float(rates)
        
        # Case 2: Tiered Rate
        if isinstance(rates, list):
            if not thresholds or len(rates) - 1 != len(thresholds):
                # Fallback to first rate if config is invalid
                return (tokens / 1_000_000) * rates[0]
            
            total = 0.0
            remaining = tokens
            prev_threshold = 0

            for i, threshold in enumerate(thresholds):
                tier_size = threshold - prev_threshold
                billable = min(remaining, tier_size)
                total += (billable / 1_000_000) * rates[i]
                remaining -= billable
                prev_threshold = threshold
                if remaining <= 0:
                    return total
            
            # Remaining tokens at final rate
            if remaining > 0:
                total += (remaining / 1_000_000) * rates[-1]
            return total
        return 0.0
    
    def prompt_reset(self):
        self.prompt_input_tokens = 0
        self.prompt_output_tokens = 0
        self.prompt_input_cost = 0
        self.prompt_output_cost = 0

    def reset(self):
        self.prompt_reset()
        self.conv_input_tokens = 0
        self.conv_output_tokens = 0

    def add_usage(self, input_toks, output_toks):
        self.prompt_input_tokens += input_toks
        self.prompt_output_tokens += output_toks
        self.conv_input_tokens += input_toks
        self.conv_output_tokens += output_toks
        self.prompt_input_cost += self._compute_cost(input_toks)
        self.prompt_output_cost += self._compute_cost(output_toks, output=True)

class MATE:
    """
    The Multi-Agent Trail Explorer (MATE) Router.

    Attributes:
        api (str): API provider ('gemini' or 'openrouter').
        model (str): Model identifier.
    """

    def __init__(self, api: str, model: str):
        self.name = "Router"
        self.api = api
        self.model = model

        # State (Context)
        self.active_trail_ids: List[str] = []
        self.order_by: str = ""
        self.conversation_history: List[Any] = []
        
        # Configuration
        self.temperature = MODEL_TEMPERATURE
        self.max_turns = MAX_GENERATION_TURNS
        self.system_prompt = ROUTER_PROMPT
        self.tool_declarations = transform_tool_declarations(ROUTER_TOOLS, api)
        
        # Tokens
        self.token_counter = TokenCounter(model)

        # Initialize Client
        if api == "gemini":
            if not GOOGLE_GENAI_API_KEY:
                raise ValueError("Missing GOOGLE_GENAI_API_KEY")
            self.client = genai.Client(api_key=GOOGLE_GENAI_API_KEY)
        else:
            if not OPENROUTER_API_KEY:
                raise ValueError("Missing OPENROUTER_API_KEY")
            self.client = AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1", 
                api_key=OPENROUTER_API_KEY
            )

        logger.info(f"[{self.name}] Instance initialized with api={api} model={model}")

    def reset_conversation(self) -> None:
        """Clears conversation history and token counters."""
        self.conversation_history = []
        self.token_counter.reset()
        self.active_trail_ids = []
        self.order_by = ""

    def _get_agent(self, agent_name: str) -> Any:
        """Factory method to instantiate specialist agents."""
        agents = {
            "GeocodingAgent": GeocodingAgent,
            "TrailAgent": TrailAgent,
            "MeteoAgent": MeteoAgent,
            "WebAgent": WebAgent
        }
        agent_cls = agents.get(agent_name)
        if not agent_cls:
            logger.warning(f"Unknown agent requested: {agent_name}")
            return None
        return agent_cls(self.api, self.model)

    async def _build_context_prompt(self, user_query: str, user_coords: Tuple[float, float], user_id: str) -> str:
        """Constructs the JSON-formatted context string for the system prompt."""
        try:
            user_data = await get_user_profile_data(user_id)
            user_name = user_data.get("display_name", "User")
        except ValueError:
            user_name = "Guest"

        context = {
            "user_location": {"latitude": user_coords[0], "longitude": user_coords[1]},
            "user_info": {"user_id": user_id, "name": user_name},
            "date_time": {
                "iso": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "day_of_week": datetime.datetime.now().strftime("%A"),
            }
        }
        context_str = json.dumps(context, indent=2, ensure_ascii=False)
        
        return f"Context:\n{context_str}\n\nUser Query:\n{user_query}"

    async def stream(self, user_query: str, user_coords: Tuple[float, float], user_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Main entry point for processing a user request.
        Yields streaming events (text chunks, tool calls, errors).
        """

        # Reset prompt token count to zero
        self.token_counter.prompt_reset()

        if self.api == "gemini":
            async for event in self._stream_gemini(user_query, user_coords, user_id):
                yield event
        else:
            async for event in self._stream_openai_compatible(user_query, user_coords, user_id):
                yield event

    # --- GEMINI IMPLEMENTATION ---

    async def _stream_gemini(self, user_query: str, user_coords: Tuple[float, float], user_id: str):
        start_time = time.time()
        
        final_prompt_text = await self._build_context_prompt(user_query, user_coords, user_id)
        self.conversation_history.append(
            types.Content(role="user", parts=[types.Part(text=final_prompt_text)])
        )

        for turn in range(1, self.max_turns + 1):
            logger.info(f"[{self.name}] Turn {turn}/{self.max_turns}")

            config = types.GenerateContentConfig(
                temperature=self.temperature,
                system_instruction=self.system_prompt,
                tools=[types.Tool(function_declarations=self.tool_declarations)]
            )

            # Generate Stream
            stream = await call_with_retry(
                func=lambda: self.client.aio.models.generate_content_stream(
                    model=self.model,
                    contents=self.conversation_history,
                    config=config
                ),
                name=self.name,
                max_retries=MAX_RETRIES
            )

            ongoing_text = ""
            content_parts = []
            tool_calls = []
            
            # Consume Stream
            async for event in stream:
                
                try:
                    candidate = event.candidates[0]
                    content = candidate.content
                    parts = content.parts
                except (AttributeError, IndexError):
                    logger.error(f"[{self.name}] Invalid response structure from the gemini API.")
                    yield {"type": EventType.ERROR, "message": "Invalid API response structure."}
                    continue

                # Update Token Counts
                if hasattr(event, "usage_metadata") and event.usage_metadata:
                    input_toks = getattr(event.usage_metadata, "prompt_token_count", 0) or 0
                    output_toks = getattr(event.usage_metadata, "candidates_token_count", 0) or 0
                    finish_reason = candidate.finish_reason
                    if finish_reason is not None:
                        self.token_counter.add_usage(input_toks, output_toks)

                for part in parts:
                    content_parts.append(part)
                    
                    # Accumulate Text
                    if part.text and not part.thought:
                        ongoing_text += part.text
                        yield {"type": EventType.TEXT, "delta": part.text}

                    # Accumulate Tool Calls
                    if part.function_call:
                        tool_calls.append(part.function_call)

            # --- Turn Decision Logic ---
            
            # Store Assistant Response in History
            self.conversation_history.append(
                types.Content(role="model", parts=content_parts)
            )

            # Case A: Final Response (Text only, no tools)
            if not tool_calls and ongoing_text.strip():
                yield await self._create_final_response(ongoing_text, start_time)
                return

            if not tool_calls:
                logger.info("No text or function_call parts found in model response.")
                yield {"type": EventType.ERROR, "message": "Model returned empty response."}
                return

            # Case B: Execute Tool Calls (Handoffs)
            tool_responses = []
            for call in tool_calls:

                tool_name = call.name
                if tool_name != "handoff_to_agent":
                    logger.error(f"Unknown tool called: {tool_name}")
                    continue

                func_args = extract_json_from_text(call.args)
                agent_name = func_args.get('agent_name')
                instruction = func_args.get('instruction')

                logger.info(f"[{self.name}] Handing off to {agent_name}: {instruction}")
                
                agent = self._get_agent(agent_name)
                if not agent:
                    continue

                # Run the agent
                full_agent_response = ""
                async for chunk in agent.run(instruction):
                    if chunk.get("type") in [EventType.TOOL_CALL, EventType.TOOL_RESULT]:
                        yield chunk # Forward tool events to UI
                    
                    if chunk.get("type") == EventType.AGENT_RESPONSE:

                        # Capture usage
                        input_toks = chunk.get('input_tokens', 0)
                        output_toks = chunk.get('output_tokens', 0)
                        self.token_counter.add_usage(input_toks, output_toks)
                        
                        # Parse embedded JSON in agent response (TrailAgent specific)
                        if agent_name == "TrailAgent":
                            self._handle_trail_agent_state(chunk.get('message', ''))

                        full_agent_response = json.dumps(chunk, default=str)

                # Create the Tool Response Part for Gemini
                tool_responses.append(types.Part.from_function_response(
                    name=tool_name,
                    response={"result": full_agent_response}
                ))

            # Append Tool Outputs to History
            self.conversation_history.append(
                types.Content(role="user", parts=tool_responses)
            )

        yield {"type": EventType.ERROR, "message": "Max conversation turns reached."}

    # --- OPENAI / OPENROUTER IMPLEMENTATION ---

    async def _stream_openai_compatible(self, user_query: str, user_coords: Tuple[float, float], user_id: str):
        start_time = time.time()
        
        # System Prompt Init
        if not self.conversation_history:
            self.conversation_history.append({"role": "system", "content": self.system_prompt})

        final_prompt_text = await self._build_context_prompt(user_query, user_coords, user_id)
        self.conversation_history.append({"role": "user", "content": final_prompt_text})

        for turn in range(1, self.max_turns + 1):
            logger.info(f"[{self.name}] Turn {turn}/{self.max_turns}")

            create_args = {
                "model": self.model,
                "messages": self.conversation_history,
                "tools": self.tool_declarations,
                "parallel_tool_calls": True,
                "stream": True
            }

            # Async API Call
            stream = await call_with_retry(
                lambda: self.client.chat.completions.create(**create_args),
                name=self.name,
                max_retries=MAX_RETRIES,
            )

            ongoing_text = ""
            tool_calls_dict = {}

            async for event in stream:

                # logger.info("NEW EVENT")

                try:
                    choice = event.choices[0]
                    delta = choice.delta
                except:
                    logger.error(f"[{self.name}] Invalid response structure from the {self.api} API.")
                    yield {"type": EventType.ERROR, "message": "Invalid API response structure."}
                    return
                
                # Update Token Counts
                if hasattr(event, "usage") and event.usage:
                    input_toks = getattr(event.usage, "prompt_tokens", 0) or 0
                    output_toks = getattr(event.usage, "completion_tokens", 0) or 0
                    self.token_counter.add_usage(input_toks, output_toks)

                # Stream Text
                if delta.content:
                    ongoing_text += delta.content
                    yield {"type": EventType.TEXT, "delta": delta.content}

                # Stream Tool Calls (fragments)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_dict:
                            tool_calls_dict[idx] = tc
                            # Initialize arguments string if needed
                            if tool_calls_dict[idx].function.arguments is None:
                                tool_calls_dict[idx].function.arguments = ""
                        else:
                            # Append argument fragments
                            if tc.function.arguments:
                                tool_calls_dict[idx].function.arguments += tc.function.arguments

            # --- Turn Decision Logic ---

            # Append Assistant Output to History
            if tool_calls_dict:
                self.conversation_history.append({
                    "role": "assistant",
                    "tool_calls": list(tool_calls_dict.values())
                })
            elif ongoing_text:
                self.conversation_history.append({
                    "role": "assistant",
                    "content": ongoing_text
                })

            # Case A: Final Response (Text only, no tools)
            if not tool_calls_dict and ongoing_text.strip():
                yield await self._create_final_response(ongoing_text, start_time)
                return
            
            if not tool_calls_dict:
                logger.info("No text or function calls found in model response.")
                yield {"type": EventType.ERROR, "message": "No text or function calls found in model response."}
                return
            
            # Case B: Execute Tools
            tool_responses = []
            for call in tool_calls_dict.values():

                tool_name = call.function.name
                if tool_name != "handoff_to_agent":
                    logger.error(f"Unknown tool called: {tool_name}")
                    continue
                
                func_args = extract_json_from_text(call.function.arguments)
                agent_name = func_args.get('agent_name')
                instruction = func_args.get('instruction')

                logger.info(f"[{self.name}] Handing off to {agent_name}: {instruction}")
                
                agent = self._get_agent(agent_name)
                if not agent:
                    continue

                full_agent_response = ""
                async for chunk in agent.run(instruction):
                    if chunk.get("type") in [EventType.TOOL_CALL, EventType.TOOL_RESULT]:
                        yield chunk # Forward tool events to UI
                    
                    if chunk.get("type") == EventType.AGENT_RESPONSE:
                        # Capture usage
                        input_toks = chunk.get('input_tokens', 0)
                        output_toks = chunk.get('output_tokens', 0)
                        self.token_counter.add_usage(input_toks, output_toks)

                        if agent_name == "TrailAgent":
                            self._handle_trail_agent_state(chunk.get('message', ''))

                        full_agent_response = json.dumps(chunk, default=str)

                tool_responses.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": full_agent_response
                })
            
            if tool_responses:
                for output in tool_responses:
                    self.conversation_history.append(output)
            else:
                 yield {"type": EventType.ERROR, "message": "Loop detected: tool called but no execution occurred."}
                 return

        yield {"type": EventType.ERROR, "message": "Max conversation turns reached."}

    # --- HELPERS ---

    def _handle_trail_agent_state(self, message_json_str: str):
        """Extracts trail IDs from TrailAgent response to update Router state."""

        # Use robust parsing from utils
        data = extract_json_from_text(message_json_str)

        if data.get('show_trails'):
            trail_ids = data.get('trail_ids', [])
            order_by = data.get('order_by', "")

            logger.info(f"[{self.name}] Saving {len(trail_ids)} trail IDs ordered by {order_by}")

            self.active_trail_ids = trail_ids
            self.order_by = order_by

    async def _create_final_response(self, text: str, start_time: float) -> Dict[str, Any]:
        """Constructs the final 'end' event with costs and trails."""
        trails = []
        if self.active_trail_ids:
            trails = await get_trails_to_show(self.active_trail_ids, self.order_by)

        input_cost = self.token_counter.prompt_input_cost
        output_cost = self.token_counter.prompt_output_cost
        total_cost = input_cost + output_cost
        
        duration = time.time() - start_time
        logger.info(f"Complete.")
        logger.info(f"Duration: {duration:.2f}s | Cost: ${total_cost:.6f}")
        logger.info(f"Input tokens: {self.token_counter.prompt_input_tokens} (${input_cost:.6f})")
        logger.info(f"Output tokens: {self.token_counter.prompt_output_tokens} (${output_cost:.6f})")

        return {
            "type": EventType.END,
            "message": text,
            "trails": trails,
            "order_by": self.order_by,
            "input_tokens": self.token_counter.prompt_input_tokens,
            "output_tokens": self.token_counter.prompt_output_tokens,
            "cost": total_cost,
            "duration": duration
        }