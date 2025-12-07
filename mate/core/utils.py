"""
Utility Functions Module.

This module contains helper functions for asynchronous API communication, 
JSON parsing, and non-blocking retry logic.
"""

import json
import random
import httpx
import asyncio
import html
from typing import Any, Dict, List, Optional, Union, Callable, Awaitable

from mate.config import DEFAULT_USER_AGENT, DEFAULT_TIMEOUT
from mate.core.logger import logger


def transform_tool_declarations(
    tools: List[Dict[str, Any]], 
    api: str
) -> Optional[List[Dict[str, Any]]]:
    """
    Converts Gemini-style tool definitions into OpenAI-compatible function tools.

    If the API is 'gemini', returns the tools as-is.
    If the API is 'openrouter' (or other OpenAI compatible), wraps them in the
    {"type": "function", "function": ...} schema.

    Args:
        tools (List[Dict]): The list of raw tool definitions.
        api (str): The target API identifier ("gemini" or "openrouter").

    Returns:
        Optional[List[Dict]]: The transformed tool definitions or None.
    """
    if api.lower() == "gemini":
        return tools

    transformed = []
    for t in tools:
        # OpenAI expects the 'function' key wrapping the definition
        transformed.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {})
            }
        })
    return transformed


async def http_get_json(
    url: str, 
    headers: Optional[Dict[str, str]] = None, 
    timeout: int = DEFAULT_TIMEOUT
) -> Any:
    """
    Performs an asynchronous HTTP GET request and parses the JSON response.

    Args:
        url (str): The target URL.
        headers (Optional[Dict]): Custom headers. Defaults to User-Agent only.
        timeout (int): Request timeout in seconds.

    Returns:
        Any: The parsed JSON response (dict or list).

    Raises:
        RuntimeError: If the network call fails or JSON is invalid.
    """
    final_headers = headers or {"User-Agent": DEFAULT_USER_AGENT}
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(url, headers=final_headers)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP {e.response.status_code} error for {url}")
            raise RuntimeError(f"HTTP GET failed: {e}")
        except httpx.RequestError as e:
            logger.error(f"Network error for {url}: {e}")
            raise RuntimeError(f"Network error: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from {url}")
            raise RuntimeError(f"Invalid JSON response: {e}")


async def retry_operation(
    func: Callable[..., Awaitable[Any]],
    retries: int = 2, 
    delay: float = 1.0, 
    *args: Any, 
    **kwargs: Any
) -> Any:
    """
    Generic wrapper to retry async functions on failure.

    Args:
        func (Callable): The function to execute.
        retries (int): Number of retry attempts.
        delay (float): Seconds to wait between retries.
        *args, **kwargs: Arguments to pass to `func`.

    Returns:
        Any: The result of `func`.
    """
    last_exc = None
    for attempt in range(1, retries + 2):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exc = e
            logger.warning(f"Operation failed (Attempt {attempt}/{retries+1}): {e}")
            if attempt <= retries:
                await asyncio.sleep(delay)
    
    if last_exc:
        raise last_exc


def extract_json_from_text(raw_input: Union[str, Dict, List, Any]) -> Dict[str, Any]:
    """
    Robustly extracts and parses a JSON object from various input formats.

    This is useful for handling LLM outputs which might be:
    1. A clean JSON string.
    2. A Markdown code block (```json ... ```).
    3. Natural language mixed with JSON.
    4. A pre-parsed Dictionary (pass-through).

    It also automatically unescapes HTML entities in string values (e.g., 
    fixing '&gt;' to '>' in SQL queries).

    Args:
        raw_input: The input data from the LLM.

    Returns:
        Dict[str, Any]: The parsed dictionary. Returns empty dict on total failure.
    """
    extracted_data: Dict[str, Any] = {}

    # Case 1: Already a dict
    if isinstance(raw_input, dict):
        extracted_data = raw_input
    
    # Case 2: List/Tuple (e.g. key-value pairs)
    elif isinstance(raw_input, (list, tuple)):
        extracted_data = dict(raw_input)
    
    # Case 3: String parsing
    elif isinstance(raw_input, str):
        # Clean markdown code blocks if present
        cleaned_input = raw_input.strip()
        if cleaned_input.startswith("```"):
            # Remove first line (```json) and last line (```)
            lines = cleaned_input.splitlines()
            if len(lines) >= 2:
                if lines[0].startswith("```"): lines = lines[1:]
                if lines[-1].startswith("```"): lines = lines[:-1]
                cleaned_input = "\n".join(lines)

        # Try direct parsing first
        try:
            extracted_data = json.loads(cleaned_input)
        except json.JSONDecodeError:
            # Fallback: Heuristic parsing for messy output
            # Looks for valid { ... } blocks and merges them
            brace_stack = 0
            start_idx: Optional[int] = None
            
            for i, ch in enumerate(raw_input):
                if ch == '{':
                    if brace_stack == 0:
                        start_idx = i
                    brace_stack += 1

                elif ch == '}':
                    brace_stack -= 1
                    if brace_stack == 0 and start_idx is not None:
                        candidate = raw_input[start_idx:i+1]
                        try:
                            obj = json.loads(candidate)
                            if isinstance(obj, dict):
                                extracted_data.update(obj)  # Merge found objects
                        except json.JSONDecodeError:
                            pass
                        start_idx = None
    
    # Post-Processing: General Cleanup
    # Recursively or iteratively clean string values. 
    # Here we do a shallow pass which covers 99% of tool argument cases.
    for key, value in extracted_data.items():
        if isinstance(value, str):
            # Unescape HTML (fixes SQL 'where' clauses like "x &gt; 10")
            extracted_data[key] = html.unescape(value)

    return extracted_data


async def call_with_retry(
    func: Callable[[], Awaitable[Any]],
    name: str, 
    max_retries: int
) -> Any:
    """
    Executes an Async LLM API call with exponential backoff.

    Specifically handles 429 (Too Many Requests) and 503 (Service Unavailable).

    Args:
        func (Callable): Lambda function wrapping the API call.
        name (str): Agent name for logging.
        max_retries (int): Maximum retry attempts.

    Returns:
        Any: The API response.

    Raises:
        RuntimeError: If all retries fail.
    """
    for attempt in range(1, max_retries + 1):
        try:
            return await func()
        except Exception as e:
            err_msg = str(e)
            # Check for common rate limit or server overload status codes
            if "503" in err_msg or "429" in err_msg:
                # Exponential backoff with jitter: 2^attempt + random(0-1)
                wait = min(2 ** attempt + random.random(), 30)
                logger.warning(f"[{name}] API Error: {e}. Retrying in {wait:.1f}s...")
                await asyncio.sleep(wait)
            else:
                # Raise immediately for non-transient errors (e.g., 400 Bad Request)
                raise e
    
    raise RuntimeError(f"[{name}] Failed after {max_retries} retries.")