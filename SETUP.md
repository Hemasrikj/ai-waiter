# Setup

## Prerequisites

- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** — Python package and project manager
- **A Google Gemini API key** — required when using `MODEL=google_genai:*`; set `GOOGLE_API_KEY` in `.env`
- **[Ollama](https://ollama.com)** — required when using `MODEL=ollama:*`; runs the model locally on your machine

### Install uv

**macOS / Linux**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell)**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

After installation, restart your terminal so `uv` is on your `PATH`.

---

## Project setup

`pyproject.toml` and `uv.lock` are already committed — no `uv init` needed.

```bash
# Install all dependencies from the lockfile
uv sync
```

### Environment variables

Copy `.env_example` to `.env` and fill in as needed:

```bash
cp .env_example .env
```

`.env`:
```
# Required for Gemini
GOOGLE_API_KEY=your-gemini-api-key

# Model to use — any LangChain init_chat_model provider:model string
MODEL=google_genai:gemini-2.5-flash

# Base URL for local model servers (e.g. Ollama); leave blank for cloud providers
MODEL_BASE_URL=
```

The app loads this with `python-dotenv` at startup.

---

## Running the app

### Terminal (console.py)

```bash
uv run console.py           # standard
uv run console.py --trace   # print tool calls, graph nodes, and token usage
```

Interactive terminal session. Type `quit`/`exit` to leave, `restart` to reset.

### Web server (server.py)

```bash
uv run python server.py                      # standard
uv run python server.py --trace              # print tool calls, graph nodes, and token usage
uv run python server.py --trace --port 9000  # custom port
```

Then open **http://localhost:8000** in a browser (or the port you specified).

The server hosts the chat UI and WebSocket backend in a single process. Order status notifications (placed → preparing → ready → served) are pushed to the browser automatically.

> **Note:** The server supports one concurrent user — `ai_waiter.py` uses module-level state for the tray and order.

---

## Local model via Ollama

Ollama runs open-source models locally on your machine. The app uses Ollama's tool-calling API, so the model must support tools.

**Supported models** (tool-calling): `llama3.2`, `qwen2.5`, `mistral-nemo`  
**Not supported**: `gemma3` — it does not support Ollama tool-calling.

### Install Ollama

**macOS**
```bash
brew install ollama
```

**Windows (PowerShell)**
```powershell
irm https://ollama.com/install.ps1 | iex
```

**Linux**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Pull the model and start the server

```bash
ollama pull llama3.2:1b
ollama serve       # starts the local API on http://localhost:11434
```

> On macOS, `ollama serve` runs automatically after `brew install ollama`. You only need to run it manually if it isn't already running.

### Configure `.env` for Ollama

```
MODEL=ollama:llama3.2:1b
MODEL_BASE_URL=http://localhost:11434
```

Then run as normal:

```bash
uv run console.py
uv run python server.py
```

---

## Repository layout

```
ai-waiter-01/
├── console.py            # Terminal entry point — loads .env, runs the interactive loop
├── server.py             # Web entry point — FastAPI + WebSocket backend
├── static/
│   └── index.html        # Browser chat UI (served at /)
├── ai_waiter.py          # Reusable module: system prompt, tools, graph, state
├── ai/
│   └── prompt.md         # System prompt design notes
├── menu/
│   ├── accessor.py       # Runtime module: MENU dict + search APIs
│   ├── __init__.py       # Re-exports MENU as the menu package
│   ├── test_accessor.py  # Smoke-test: run directly to print the rendered menu
│   ├── scanned-menu.json # Raw source menu (edit this to change the menu)
│   ├── normalize-menu.py # Stage 1: scanned-menu.json → normalized-menu.json
│   ├── translate.py      # Stage 2: normalized-menu.json → menu.json (adds translations)
│   ├── normalized-menu.json  # Normalised structure, en + kn only (generated)
│   ├── menu.json         # Final menu with all language translations (generated)
│   ├── menu-schema.json  # JSON Schema for menu.json
│   └── README.md         # Menu data formats, module API, regeneration steps
├── lang-graph-sample/    # LangGraph learning notebooks (reference only)
├── tool/                 # Utility scripts
├── pyproject.toml        # Project metadata and dependencies
└── uv.lock               # Pinned dependency lockfile
```

---

## Regenerating the menu

Menu processing is a two-stage pipeline:

```
scanned-menu.json  →  [normalize-menu.py]  →  normalized-menu.json
                                                       ↓
                                              [translate.py]  →  menu.json
```

```bash
# Stage 1: normalise structure, IDs, timings, and name casing
uv run python menu/normalize-menu.py

# Stage 2: add translations for 10 Indian languages (uses MODEL + provider key from .env)
uv run python menu/translate.py
```

See **[menu/README.md](menu/README.md)** for full details on the menu data format and module API.

---

## Dependencies

Managed by `uv` via `pyproject.toml`:

| Package | Purpose |
|---|---|
| `langgraph` | Stateful agent graph (chatbot loop, tool dispatch) |
| `langchain` | LLM abstraction, tool definitions |
| `langchain-google-genai` | Google Gemini model integration |
| `langchain-ollama` | Local Ollama model integration |
| `python-dotenv` | Loads API keys from `.env` |
| `fastapi` | Web framework for the chatbot server (HTTP + WebSocket) |
| `uvicorn[standard]` | ASGI server for running FastAPI |
