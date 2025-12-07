# MATE: Multi-Agent Trail Explorer Framework

**MATE** is a generic, highly extensible **Multi-Agent System (MAS)** framework designed for building outdoor activity assistants. It uses a **Hub-and-Spoke** architecture to orchestrate specialized agents (Geocoding, Weather, Trails, Web) via a central Router.

This repository provides the **architectural skeleton**. It is designed to be **platform-agnostic**, meaning it does not come with a pre-populated database or specific API implementations. You plug in your own data sources (PostGIS, ElasticSearch, etc.) and API keys.

## 🏗 Architecture

*   **Router (The Hub):** Managed by `mate.router`. It maintains conversation state, handles LLM streaming, and delegates tasks.
*   **Specialist Agents (The Spokes):**
    *   `GeocodingAgent`: Handles geocoding and location context.
    *   `TrailAgent`: Handles database queries for activities/trails.
    *   `MeteoAgent`: Handles weather forecasting.
    *   `WebAgent`: Handles general knowledge retrieval.
*   **Tools (The Hands):** Defined as JSON schemas in `mate/tools/definitions.py`. Implementations are located in `mate/tools/`.

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
Since MATE is a framework, you must implement the "Hands" of the system in `mate/tools/` to make it useful:

1.  **Database Connection:** Edit `mate/core/database.py` to connect to your SQLite/PostgreSQL/Vector DB.
2.  **Trail Logic:** Edit `mate/tools/trail.py` to implement `execute_trail_query`.
3.  **Weather:** Edit `mate/tools/meteo.py` to connect to a weather API (e.g., OpenMeteo).
4.  **Geocoding:** Edit `mate/tools/geocoding.py` to connect to a geocoder (e.g., Google Maps, Mapbox).
5.  **Web:** Edit `mate/tools/web.py` to connect to a web search service (e.g., SerpAPI).

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
*   **Prompts:** Modify `mate/agents/prompts.py` to describe your specific database schema to the Agents.
*   **Tools:** Add new tools in `mate/tools/definitions.py` and register them in `mate/tools/registry.py`.

## 📄 License
MIT
