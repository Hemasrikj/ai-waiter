# AI Waiter — An Agentic LangGraph Tool-Calling Agent for Restaurant Ordering

An agentic AI waiter backed by a structured restaurant menu. The model autonomously decides when to call tools (add items, view tray, place order) and sequences multi-step actions — it is not a simple question-answer chatbot.

---

## Agent graph

The agent is built with [LangGraph](https://langchain-ai.github.io/langgraph/). The model runs in a loop, calling tools as needed until it has a final response to return to the user.

```mermaid
graph TD
    __start__([__start__]) --> chatbot
    chatbot --> tools
    chatbot --> __end__([__end__])
    tools --> chatbot

    chatbot["chatbot\n─────────────\nLLM + bound tools\n(any provider via MODEL env var)"]
    tools["tools\n─────────────\nadd_to_tray\nview_tray\nplace_order\ncheck_order_status"]
```

Flow: the LLM receives the system prompt and conversation history, then either responds directly (→ `__end__`) or emits a tool call (→ `tools` → back to `chatbot`). This loop continues until no further tool calls are needed.

---

## Getting started

See **[SETUP.md](SETUP.md)** for tooling requirements, environment setup, and repository layout.

---

## Running the AI waiter

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- A Google Gemini API key — required when using `MODEL=google_genai:*`; set in `.env` (see `.env_example`)
- [Ollama](https://ollama.com) running locally — required when using `MODEL=ollama:*`; model must support tool-calling (`llama3.2`, `qwen2.5`, `mistral-nemo` — `gemma3` does not)

### Setup

```bash
uv sync
cp .env_example .env   # then edit MODEL and any required keys
```

### Start the chatbot

```bash
uv run console.py
```

The program starts an interactive terminal session. The waiter greets you, then responds to natural-language input.

### Start Webserver Chatbot

```bash
uv run python server.py
```

Access the chatbot [http://localhost:8000](http://localhost:8000)


### What you can do

| Intent | Example input |
|---|---|
| Browse the menu | `show me the menu` |
| Add items | `I'd like 2 masala dosas and a coffee` |
| Review your tray | `what's in my tray?` |
| Remove an item | `remove the coffee` |
| Place the order | `yes, place the order` |
| Check order status | `what's the status of my order?` |
| Quit | `quit` or `exit` |

### Order status simulation

After placing an order the status advances automatically in the background:

```
placed → preparing (after 1 min) → ready (after 2 min) → served (after 3 min)
```

A notification is printed in the terminal each time the status changes.

### Demo Runs

[demo](./demo/)

---

## Menu data

The restaurant menu lives in `menu/`. Raw scanned data is converted to a
normalised JSON format by `menu/convert.py`.

See **[menu/README.md](menu/README.md)** for:
- Input and output JSON structure
- Field reference (camelCase, multilingual text arrays, availability windows)
- Item splitting rules (dry/gravy variants, slash-choice items)
- How to regenerate `menu/menu.json`

Quick regeneration:
```bash
uv run python menu/convert.py
```
