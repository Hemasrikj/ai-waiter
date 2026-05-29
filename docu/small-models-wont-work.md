# Why Small Local Models Cannot Be Used for This App

---

## What this app demands from the model

The AI waiter is an **agentic application** — the model doesn't just answer questions, it drives a multi-step workflow by calling tools in the right order:

1. Greet the customer
2. Look up the menu
3. Identify item ids from natural language ("two masala dosas")
4. Call `add_to_tray` with the correct id and quantity
5. Call `view_tray` before confirming
6. Call `place_order` only on explicit confirmation
7. Call `check_order_status` when asked

Each step requires the model to decide between responding in prose, calling a specific tool, and outputting valid JSON that matches the tool schema exactly. This is qualitatively harder than answering a question.

---

## Why small models fail at this

### Tool calling is a high-bar capability

Tool calling requires three things to work together:
- **Schema adherence** — output valid JSON matching the exact argument names and types
- **Decision quality** — know *when* to call a tool vs respond in prose
- **Multi-step reasoning** — sequence tool calls correctly across a conversation

Models below ~7 billion parameters frequently fail on all three. Observed failures with `llama3.2:1b` and `llama3.2:3b` in this app:
- Hallucinated fake tool schemas in the response text instead of making real tool calls
- Called `get_menu` on every turn regardless of context
- Dumped raw menu text instead of summarising it as a waiter would
- Ignored tool results and answered from training knowledge instead

### The system prompt is large

The system prompt embeds the full restaurant menu (~2,800 tokens). For a 1b model with limited effective context utilisation, this consumes most of the model's "working memory" before the conversation even starts, leaving little capacity for instruction-following and tool dispatch.

### CPU inference is too slow

Even if a small model could follow instructions correctly, the response time on CPU hardware makes it unusable in practice:

| Model | Size | CPU inference speed | Time per turn |
|---|---|---|---|
| llama3.2:1b | 1.3 GB | ~10 tokens/sec | 15–30 sec |
| llama3.2:3b | 2.0 GB | ~4 tokens/sec | 40–90 sec |

A single order conversation (8 turns) would take 5–12 minutes on an Intel i7 without a GPU — not acceptable for a restaurant ordering app.

---

## The hardware threshold for local models

Local inference becomes viable when a **dedicated GPU** is available. With a GPU, quantized 7b–8b models run at 30–60 tokens/sec and handle tool calling reliably.

| Setup | Viable? | Notes |
|---|---|---|
| CPU only (Intel i7) | No | Too slow, small models too weak |
| Laptop with mid-range GPU (e.g. RTX 3060) | Yes | `qwen2.5:7b` or `llama3.1:8b` would work |
| Desktop with high-end GPU | Yes | Full-size models, fast inference |

---

## Architecture note

The current design is optimised for a capable cloud model. A different architecture would be needed to make small local models work at all — for example, replacing tool calling with a simple intent classifier and hardcoded handlers, with the LLM only doing natural language parsing. That would be a significant rewrite and would reduce the generality of the assistant.

---

## Conclusion

For this application, **Gemini 2.5 Flash is the right choice**:
- Reliable tool calling with no failures
- Fast response times
- Very low cost (~$1.58 per 300 orders with prefix caching)
- Free tier covers early and prototype usage entirely

Local model support remains a future option if GPU hardware becomes available. See [gemini-cost-breakdown.md](gemini-cost-breakdown.md) for the cost analysis.
