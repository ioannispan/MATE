"""
Base Agent Module.

This module defines the BaseAgent class, which serves as the wrapper for 
LLM interactions. It abstracts the differences between Google's GenAI SDK 
and OpenAI-compatible APIs (like OpenRouter), handling conversation history, 
tool execution loops, and token usage tracking asynchronously.
"""

import json
from typing import List, Dict, Any, AsyncGenerator

# API Clients
from google import genai
from google.genai import types
from openai import AsyncOpenAI

from mate.config import (
    EventType,
    GOOGLE_GENAI_API_KEY, 
    OPENROUTER_API_KEY, 
    MODEL_TEMPERATURE, 
    MAX_GENERATION_TURNS, 
    MAX_RETRIES
)
from mate.core.utils import extract_json_from_text, call_with_retry, transform_tool_declarations
from mate.core.logger import logger
from mate.agents.tools.registry import execute_tool


class BaseAgent:
    """
    A generic agent class supporting both Gemini and OpenAI-compatible APIs asynchronously.

    Attributes:
        api (str): The API provider ('gemini' or 'openrouter').
        model (str): The model identifier string.
        name (str): The name of the agent (for logging).
        system_prompt (str): The system instruction for the agent.
        conversation_history (List): Stores the chat history.
    """

    def __init__(
        self, 
        api: str, 
        model: str, 
        name: str, 
        system_prompt: str, 
        tool_declarations: List[Dict[str, Any]]
    ):
        """
        Initialize the BaseAgent.

        Args:
            api (str): 'gemini' or 'openrouter'.
            model (str): Model ID (e.g., 'gemini-2.5-flash').
            name (str): Agent alias.
            system_prompt (str): Instructions for the LLM.
            tool_declarations (List[Dict]): The list of tool definitions.
        """
        self.api = api
        self.model = model
        self.name = name
        self.system_prompt = system_prompt
        
        # Transform tools based on the target API structure
        self.tool_declarations = transform_tool_declarations(tool_declarations, api)

        # Context specific result holders (Used by TrailAgent)
        self.trail_ids: List[Any] = []
        self.order_by: str = ""
        
        # Adjust temperature for reasoning models if detected
        self.temperature = MODEL_TEMPERATURE
        self.max_turns = MAX_GENERATION_TURNS
        self.conversation_history: List[Any] = []
        
        # Metrics
        self.input_tokens = 0
        self.output_tokens = 0

        # Initialize Client
        if api == "gemini":
            if not GOOGLE_GENAI_API_KEY:
                raise ValueError("GOOGLE_GENAI_API_KEY is not set.")
            self.client = genai.Client(api_key=GOOGLE_GENAI_API_KEY)
        else:
            if not OPENROUTER_API_KEY:
                raise ValueError("OPENROUTER_API_KEY is not set.")
            self.client = AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1", 
                api_key=OPENROUTER_API_KEY
            )

        logger.info(f"[{self.name}] Agent initialized with api={api} model={model}")

    async def run(self, user_prompt: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Executes a conversation turn based on user input asynchronously.

        Args:
            user_prompt (str): The user's input message.

        Yields:
            Dict[str, Any]: Events keys like 'type', 'agent', 'message', 'error'.
        """
        if self.api == "gemini":
            async for chunk in self._run_gemini(user_prompt):
                yield chunk
        else:
            async for chunk in self._run_openai_compatible(user_prompt):
                yield chunk

    async def _run_gemini(self, user_prompt: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Internal loop for Google GenAI SDK."""
        
        self.conversation_history.append(
            types.Content(role="user", parts=[types.Part(text=user_prompt)])
        )

        for turn in range(1, self.max_turns + 1):
            logger.debug(f"[{self.name}] Turn {turn}/{self.max_turns}")

            # Configure Generation
            config = types.GenerateContentConfig(
                temperature=self.temperature,
                system_instruction=self.system_prompt,
                tools=[types.Tool(function_declarations=self.tool_declarations)]
            )

            # Async API Call
            response = await call_with_retry(
                func=lambda: self.client.aio.models.generate_content(
                    model=self.model,
                    contents=self.conversation_history,
                    config=config
                ),
                name=self.name,
                max_retries=MAX_RETRIES
            )

            # Update Metrics
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                self.input_tokens += getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                self.output_tokens += getattr(response.usage_metadata, "candidates_token_count", 0) or 0

            try:
                candidate = response.candidates[0]
                content = candidate.content
                parts = content.parts
            except (AttributeError, IndexError):
                logger.error(f"[{self.name}] Invalid response structure from the gemini API.")
                yield {"type": EventType.ERROR, "message": "Invalid API response structure."}
                return

            self.conversation_history.append(content)

            # 1. Process Text
            text_parts = [p.text for p in parts if p.text]

            # 2. Process Function Calls
            tool_calls = [p.function_call for p in parts if p.function_call]

            # Case A: Final natural-language response
            if text_parts and not tool_calls:
                final_message = "\n".join(text_parts)
                yield self._create_final_response(final_message)
                return

            if not tool_calls:
                logger.warning(f"[{self.name}] No text or function_call parts found.")
                yield {"type": EventType.ERROR, "message": "Model returned empty response."}
                continue

            # Case B: Execute Tools
            tool_responses = []
            for call in tool_calls:
                tool_name = call.name
                yield {"type": EventType.TOOL_CALL, "name": tool_name}
                
                func_args = extract_json_from_text(call.args)

                # Execute logic
                try:
                    logger.info(f"[{self.name}] Executing tool: {tool_name} with args: {func_args}")
                    result = await execute_tool(tool_name, func_args)

                    # Capture specific state for TrailAgent
                    if tool_name == "execute_trail_query" and result.get("status") == "ok":
                        self.trail_ids = result.get("trail_ids", [])
                        self.order_by = result.get("order_by", "")

                    result_json = json.dumps(result, default=str, ensure_ascii=False)
                    logger.info(f"[{self.name}] Tool result: {result_json[:500]}")
                except Exception as e:
                    logger.error(f"[{self.name}] Tool Execution Error ({tool_name}): {e}")
                    result_json = json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

                tool_responses.append(types.Part.from_function_response(
                    name=call.name,
                    response={"result": result_json}
                ))
                
                yield {"type": EventType.TOOL_RESULT, "name": tool_name}

            # Append tool outputs to history so the model sees them next turn
            self.conversation_history.append(types.Content(role="user", parts=tool_responses))

        logger.warning(f"[{self.name}] Max turns reached.")
        yield {"type": EventType.ERROR, "message": "Max turns reached without final response."}

    async def _run_openai_compatible(self, user_prompt: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Internal loop for OpenAI/OpenRouter APIs."""

        # Inject system prompt on first run
        if not self.conversation_history:
            self.conversation_history.append({"role": "system", "content": self.system_prompt})

        self.conversation_history.append({
            "role": "user",
            "content": user_prompt
        })

        for turn in range(1, self.max_turns + 1):
            logger.debug(f"[{self.name}] Turn {turn}/{self.max_turns}")

            create_args = {
                "model": self.model,
                "messages": self.conversation_history,
                "tools": self.tool_declarations,
                "parallel_tool_calls": True
            }
            
            # NOTE: "reasoning_effort" is experimental and model-dependent.
            # It may cause 400 errors on models that don't support it.
            if self.api == "openrouter":
                create_args["reasoning_effort"] = "high"

            # Async API Call
            response = await call_with_retry(
                func=lambda: self.client.chat.completions.create(**create_args),
                name=self.name,
                max_retries=MAX_RETRIES
            )

            # Update Tokens
            if hasattr(response, "usage") and response.usage:
                self.input_tokens += getattr(response.usage, "prompt_tokens", 0) or 0
                self.output_tokens += getattr(response.usage, "completion_tokens", 0) or 0

            try:
                choice = response.choices[0]
                message = choice.message
            except (AttributeError, IndexError):
                logger.error(f"[{self.name}] Invalid response structure from the {self.api} API.")
                yield {"type": EventType.ERROR, "message": "Invalid API response structure."}
                return

            # Safely serialize message for history
            msg_content = (
                message.model_dump() 
                if hasattr(message, "model_dump") 
                else {"role": "assistant", "content": message.content}
            )
            self.conversation_history.append(msg_content)

            # Case A: Final Response (Stop)
            if choice.finish_reason == "stop":
                content = getattr(message, "content", None)
                reasoning = getattr(message, "reasoning", None)

                # Determine candidate final message
                final_message = content if content not in (None, "") else reasoning

                # Validate final_message
                if not final_message:
                    logger.error(f"[{self.name}] Received a stop signal but no content or reasoning in message.")
                    yield {"type": EventType.ERROR, "message": "API returned no message content."}
                    return
                
                yield self._create_final_response(final_message)
                return
            
            # Case B: Tool Calls
            elif choice.finish_reason == "tool_calls":
                tool_calls = getattr(message, "tool_calls", []) or []

                if not tool_calls:
                    logger.warning(f"[{self.name}] Finish reason is tool_calls but list is empty.")
                    yield {"type": EventType.ERROR, "message": "Empty tool_calls list."}
                    continue

                for call in tool_calls:
                    tool_name = call.function.name
                    yield {"type": EventType.TOOL_CALL, "name": tool_name}

                    func_args = extract_json_from_text(call.function.arguments)

                    try:
                        logger.info(f"[{self.name}] Executing tool: {tool_name} with args: {func_args}")
                        result = await execute_tool(tool_name, func_args)

                        if tool_name == "execute_trail_query" and result.get("status") == "ok":
                            self.trail_ids = result.get("trail_ids", [])
                            self.order_by = result.get("order_by", "")

                        result_json = json.dumps(result, default=str, ensure_ascii=False)
                        logger.info(f"[{self.name}] Tool result: {result_json[:500]}")
                    except Exception as e:
                        logger.error(f"[{self.name}] Tool Error ({tool_name}): {e}")
                        result_json = json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
                        
                    yield {"type": EventType.TOOL_RESULT, "name": tool_name}

                    tool_response = {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result_json,
                    }
                    self.conversation_history.append(tool_response)
            
            else:
                logger.error(f"[{self.name}] Unknown finish reason: {choice.finish_reason}")
                yield {"type": EventType.ERROR, "message": f"Unknown finish reason: {choice.finish_reason}"}
                return

        logger.warning(f"[{self.name}] Max turns reached.")
        yield {"type": EventType.ERROR, "message": "Max turns reached without final response."}

    def _create_final_response(self, message: str) -> Dict[str, Any]:
        """Create the final agent response dictionary."""
        return {
            "type": EventType.AGENT_RESPONSE,
            "agent": self.name,
            "message": message,
            "trail_ids": self.trail_ids,
            "order_by": self.order_by,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens
        }