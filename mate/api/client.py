"""
Interactive API Client.

This script provides a command-line interface to interact with the MATE API server.
It handles session management (chat_id), streaming responses, and displaying
tool execution states.
"""

import requests
import json
import traceback
import uuid
import sys
from typing import Generator, Dict, Any
from mate.config import EventType

# Configuration
API_BASE_URL = "http://localhost:8000"
TEST_USER_ID = "17891762"
TEST_LOCATION = {
    "latitude": 35.513840,  # Chania, Crete
    "longitude": 24.017399
}


class AgentAPIClient:
    """
    Synchronous client for interacting with the Agent API via Server-Sent Events (SSE).
    """
    
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
    
    def health_check(self) -> Dict[str, Any]:
        """Check if the API is healthy."""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Health check failed: {e}")
    
    def query_stream(
        self,
        query: str,
        chat_id: str,
        latitude: float = TEST_LOCATION["latitude"],
        longitude: float = TEST_LOCATION["longitude"],
        user_id: str = TEST_USER_ID,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Send a query to the agent and yield streaming events.
        
        Args:
            query (str): The user's message.
            chat_id (str): Unique session identifier.
            latitude (float): User's current latitude.
            longitude (float): User's current longitude.
            user_id (str): User identifier.
            
        Yields:
            Dict: Parsed JSON events from the server.
        """
        payload = {
            "query": query,
            "chat_id": chat_id,
            "latitude": latitude,
            "longitude": longitude,
            "user_id": user_id
        }
        
        # SSE Request
        with self.session.post(
            f"{self.base_url}/api/query-stream",
            json=payload,
            stream=True,
            timeout=60  # Long timeout for LLM generation
        ) as resp:
            
            resp.raise_for_status()

            for raw_line in resp.iter_lines(decode_unicode=True):
                if raw_line is None:
                    continue

                line = raw_line.strip()
                if not line:
                    continue

                # Parse SSE format "data: {...}"
                if not line.startswith("data: "):
                    continue

                data = line[len("data: "):]

                if not data or data == "[DONE]":
                    continue

                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    print(f"\n⚠️ JSON decode failed: {data}\n", file=sys.stderr)
    
    def reset_conversation(self, chat_id: str, user_id: str = TEST_USER_ID) -> Dict[str, Any]:
        """Reset conversation history for the specific session."""
        payload = {
            "user_id": user_id,
            "chat_id": chat_id
        }
        response = self.session.post(
            f"{self.base_url}/api/reset",
            json=payload,
            timeout=5
        )
        response.raise_for_status()
        return response.json()


def interactive_streaming_mode():
    """Run the interactive CLI loop."""
    client = AgentAPIClient()
    
    # Generate an initial session ID
    current_chat_id = str(uuid.uuid4())[:8]

    print("\n" + "="*80)
    print("MULTI-AGENT TRAIL EXPLORER - INTERACTIVE CLIENT")
    print("="*80)
    
    # Check server health
    try:
        health = client.health_check()
        print(f"✅ Server Status: {health.get('status')} | {health.get('message')}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        print(f"Ensure server is running at {API_BASE_URL}")
        return

    print(f"🔹 Session ID: {current_chat_id}")
    print(f"🔹 User ID:    {TEST_USER_ID}")
    print("-" * 80)
    print("Commands:")
    print("  /reset  - Clear context for current chat")
    print("  /new    - Start a brand new chat session")
    print("  /quit   - Exit")
    print("="*80 + "\n")
    
    while True:
        try:
            user_input = input(f"\n[{current_chat_id}] You: ").strip()
            
            if not user_input:
                continue
            
            # --- Command Handling ---
            if user_input.lower() in ['/quit', '/exit']:
                print("\n👋 Goodbye!")
                break
            
            if user_input.lower() == '/reset':
                result = client.reset_conversation(chat_id=current_chat_id)
                print(f"\n🧹 {result['message']}\n")
                continue

            if user_input.lower() == '/new':
                current_chat_id = str(uuid.uuid4())[:8]
                print(f"\n✨ Switched to new session: {current_chat_id}\n")
                continue
            
            # --- Streaming Response ---
            print("\nAssistant: ", end="", flush=True)
            
            tool_active = False
            
            for event in client.query_stream(user_input, chat_id=current_chat_id):
                event_type = event.get("type")

                # Handle Errors
                if event_type == EventType.ERROR:
                    print(f"\n❌ Error: {event.get('message')}")
                    continue

                # Handle Text Delta
                if event_type == EventType.TEXT:
                    print(f"{event['delta']}", end="", flush=True)
                
                # Handle Tool Execution Visibility
                elif event_type == EventType.TOOL_CALL:
                    if not tool_active:
                        print("\n", end="") # Break line from text
                        tool_active = True
                    print(f"  🔧 Calls {event['name']}...", end="\r", flush=True)
                
                elif event_type == EventType.TOOL_RESULT:
                    print(f"  ✅ {event['name']} done.      ") # Overwrite previous line
                
                # Handle End of Stream
                elif event_type == EventType.END:
                    print("\n") # Final newline
                    
                    trails = event.get('trails', [])
                    if trails:
                        print(f"📍 Found {len(trails)} trails (Sorted by: {event.get('order_by')})")
                        for t in trails[:3]:
                            print(f"   - {t.get('title')} ({t.get('trail_distance_km')}km)")
                        if len(trails) > 3:
                            print("   ... and more.")

                    # Metrics
                    duration = event.get('duration', 0.0)
                    cost = event.get('cost', 0.0)
                    in_tok = event.get('input_tokens', 0)
                    out_tok = event.get('output_tokens', 0)
                    print(f"\n📊 Metrics: {duration:.2f}s | ${cost:.6f} | {in_tok} in | {out_tok} out")

        except KeyboardInterrupt:
            print("\n\n👋 Interrupted.")
            break
        
        except Exception as e:
            print(f"\n❌ Client Error: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    interactive_streaming_mode()