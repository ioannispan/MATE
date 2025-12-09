# MATE: Multi-Agent Trail Explorer Framework

**MATE** is a generic, highly extensible **Multi-Agent System (MAS)** framework designed for building outdoor activity assistants. It uses a **Hub-and-Spoke** architecture to orchestrate specialized agents (Geocoding, Weather, Trails, Web) via a central Router.

This repository provides the **architectural skeleton**. It is designed to be **platform-agnostic**, meaning it does not come with a pre-populated database or specific API implementations. You plug in your own data sources (PostGIS, ElasticSearch, etc.) and API keys.

## 🏗 Architecture

*   **Router (The Hub):** Managed by `mate/orchestration/`. It maintains conversation state, handles LLM streaming, and delegates tasks.
*   **Specialist Agents (The Spokes):**
    *   `GeocodingAgent`: Handles geocoding and location context.
    *   `TrailAgent`: Handles database queries for activities/trails.
    *   `MeteoAgent`: Handles weather forecasting.
    *   `WebAgent`: Handles general knowledge retrieval.
*   **Tools (The Hands):** Defined as JSON schemas in `mate/agents/tools/definitions.py`. Implementations are located in `mate/agents/tools/`.

## 🚀 Getting Started

### 1. Installation
```bash
git clone https://github.com/ioannispan/MATE.git
cd MATE
pip install -e .
```

### 2. Configuration
Copy `.env.example` to `.env` and configure your LLM providers (Google Gemini or OpenRouter/OpenAI).

### 3. Implementation (Required)
Since MATE is a framework, you must implement the "Hands" of the system in `mate/agents/tools/` to make it useful:

1.  **Database Connection:** Edit `mate/core/database.py` to connect to your SQLite/PostgreSQL/Vector DB.
2.  **Trail Logic:** Edit `mate/agents/tools/trail.py` to implement the database query logic.
3.  **Weather:** Edit `mate/agents/tools/meteo.py` to connect to a weather API.
4.  **Geocoding:** Edit `mate/agents/tools/geocoding.py` to connect to a geocoder.
5.  **Web:** Edit `mate/agents/tools/web.py` to connect to a web search service.

### 4. Running
Start the API Server:
```bash
python -m mate.api.api_server
```

Start the Interactive CLI Client:
```bash
python -m mate.api.client
```

## 🧩 Customization
*   **Prompts:** Modify `mate/agents/prompts.py` and `mate/orchestration/prompt.py` to describe your specific database schema to the Agents and the Router.
*   **Tools:** Add new tools in `mate/agents/tools/definitions.py` and register them in `mate/agents/tools/registry.py`.

## 📄 License
MIT
