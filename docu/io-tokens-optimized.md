# I/O Token Optimisation

## Problem

Every tool result passes through the LLM twice:
1. As **input** on the next turn (the LLM re-reads it to formulate a reply)
2. As **output** when the LLM re-presents it to the user

For display-only tools like `get_full_menu` (17 000 chars / ~4 000 tokens) and
`list_categories` (2 400 chars / ~600 tokens), the LLM adds no value — it just
forwards text. Running the full menu through the LLM was the dominant cost per session.

---

## Solution

Two complementary techniques:

### 1. Graph short-circuit (skip LLM for display tools)

Added a `prune_display_output` node in the LangGraph graph. After the `tools` node
runs, a conditional edge checks whether ALL tool messages in the batch belong to the
display-only set (`get_full_menu`, `list_categories`). If so, it routes to
`prune_display_output → END` instead of back to `chatbot`.

```
chatbot → tools → after_tools ──[display tool]──▶ prune_display_output → END
                              └──[other tools]──▶ chatbot
```

The LLM is never invoked for these responses — zero output tokens, and the tool
result is never fed back as LLM input on the next turn either.

### 2. State pruning (prevent large results bloating context)

`prune_display_output` does two things atomically:

- Writes the full tool output to module-level `_display_output` (read-and-cleared
  by `get_reply()` after sending to the user)
- Replaces the `ToolMessage` in LangGraph state with a compact stub:

```
[list_categories result sent to user — 2401 chars, not stored in context]
```

This keeps the conversation history clean. The LLM knows the tool was called (the
preceding `AIMessage` tool-call remains), but the bulk content is gone.

### Key implementation files

| File | What changed |
|---|---|
| `ai_waiter.py` | `after_tools()` conditional edge; `prune_display_output()` node; `_display_output` module global; `get_reply()` reads and clears it |
| `console.py` | Uses `get_reply(state)` instead of `extract_text(state['messages'][-1].content)` |
| `server.py` | Same |

---

## Measured impact

Session: greet → list categories → add Blue Lagoon → confirm → place order (9 LLM calls)

### Why input tokens start at 1 318 and keep growing

Every LLM call is stateless — the entire conversation must be re-sent from scratch each
time. The input on every call = **fixed overhead + full message history so far**:

| Component | ~Tokens | Notes |
|---|---|---|
| System prompt | ~750 | Rules, language rules, grounding rules, workflow |
| Tool schemas | ~560 | All 7 tool signatures injected by `bind_tools` |
| Message history | grows | Every user message, assistant reply, tool call, tool result |

So ~1 310 tokens are fixed overhead on **every single call**. The delta between calls
is just the new conversation content added that turn (~30–90 tokens).

### Turn-by-turn breakdown

On every LLM call the full context is re-sent from scratch:

```
in tokens (call N) = system prompt (~750)
                   + tool schemas (~560)
                   + user msg 1 + assistant reply 1 + tool result 1   ← round 1
                   + user msg 2 + assistant reply 2 + tool result 2   ← round 2
                   + ...all prior rounds...
                   + user msg N                                        ← current turn
```

**Delta-in** = everything added by the previous round (user msg + assistant AIMessage +
tool result). This is what grows the context each turn.
**In tokens** = the full re-sent total — what is actually billed.

| Turn | LLM call | In tokens | Delta-in | What delta-in contains | Out tokens | Notes |
|---|---|---|---|---|---|---|
| Greeting | #1 | 1 318 | 1 318 | system prompt + tool schemas + "Hello" | 16 | fixed overhead dominates |
| "what cuisine?" → list_categories | #2 | 1 342 | +24 | user message | 15 | |
| *(short-circuit — no LLM call)* | — | — | +58* | stub added to history | **0** | **list_categories bypasses LLM** |
| "give me Blue Lagoon" → menu_lookup | #3 | 1 400 | +58 | user msg + LLM tool-call msg + stub | 91 | |
| *(lookup result)* → add_to_tray | #4 | 1 460 | +60 | LLM msg + 1-line match result | 85 | |
| *(add result)* → reply | #5 | 1 517 | +57 | LLM msg + tray update line | 24 | |
| "no" → view_tray | #6 | 1 544 | +27 | user msg + LLM reply | 70 | |
| *(tray result)* → reply | #7 | 1 598 | +54 | LLM msg + tray contents | 25 | |
| "yes" → place_order | #8 | 1 626 | +28 | user msg + LLM reply | 32 | |
| *(order result)* → reply | #9 | 1 667 | +41 | LLM msg + order status | 27 | |
| **Session total** | **9 calls** | **13 472** | **1 667** | | **385** | |

*\* The stub (+58) enters context on call #3, not at the short-circuit step itself.*

**Delta-in total (1 667)** = the actual new content generated across the entire session.
**In tokens total (13 472)** = the raw token count re-sent per call — but **this is not
the same as what is billed**. Modern LLM APIs cache repeated input prefixes:

| Provider / Model | Caching behaviour |
|---|---|
| **Gemini 2.5 Flash** (this app) | Implicit context caching — automatically caches repeated prefixes at no extra setup. Cached tokens are charged at a significantly reduced rate (~75–80% discount). The system prompt + tool schemas (~1 310 tokens) are identical on every call and will typically be served from cache after the first call. |
| **OpenAI GPT-4o / o-series** | Automatic prompt caching for prefixes ≥ 1 024 tokens. Cached tokens billed at 50% of normal input rate. |
| **Anthropic Claude** | Explicit prompt caching — requires `cache_control` markers in the request. Not automatic. |
| **Ollama (local)** | No billing; KV-cache re-use is model/runtime dependent but has no cost impact. |

So the **effective billed cost** for this app (Gemini 2.5 Flash) is lower than
`13 472` raw tokens suggest — the ~1 310 fixed overhead is likely cached after call #1
and charged at the reduced rate for calls #2–#9.

The `in tokens` figure in the trace still reflects the **full context size sent**,
which matters for latency and context-window limits regardless of caching.

> **Note:** Caching behaviour and pricing change frequently. Verify current rates at
> [Google AI pricing](https://ai.google.dev/pricing) before cost planning.

### Estimated saving from optimisation

Without optimisation, `list_categories` (2 401 chars ≈ 600 tokens) would have been:
- Fed back to the LLM as input → **~600 extra input tokens** on call #3
- Re-presented by the LLM as output → **~600 extra output tokens**
- Carried in context for all remaining 6 calls → **~600 × 6 = 3 600 extra input tokens**

**Total saving this session: ~600 + 600 + 3 600 = ~4 800 tokens**

For `get_full_menu` (~4 000 tokens) the saving would be proportionally larger (~30 000
tokens over a similar session).

**Without optimisation**, the LLM would have had to re-present all 26 sections after
`list_categories` returned — adding roughly **~600 output tokens** for that one reply,
plus those same ~600 tokens bloating every subsequent turn's input context.

---

## Scope

Display tools short-circuit:
- `get_full_menu` — 339 items, ~17 000 chars
- `list_categories` — 26 sections, ~2 400 chars

Decision-required tools always go through the LLM (needed for confirmation, follow-up,
error handling):
- `menu_lookup`, `add_to_tray`, `view_tray`, `place_order`, `check_order_status`

---

## Example session and trace

### Conversation

```
User:    what cuisine you have?
Waiter:  [lists 26 categories]

User:    give me Blue Lagoon - 1 no
Waiter:  Okay, I've added 1 Blue Lagoon to your tray. Is there anything else I can get for you?

User:    no
Waiter:  Your current tray has 1 Blue Lagoon for a total of ₹135. Would you like to place this order?

User:    yes
Waiter:  Your order has been placed! The current status is "placed". I'll let you know as soon as there are any updates.
```

### Trace (`uv run server.py --trace`)

```
[trace] llm call #1
[trace] tokens  in=1318 out=16  (session total in=1318 out=16 calls=1)
[trace] llm call #2
[trace] tokens  in=1342 out=15  (session total in=2660 out=31 calls=2)
[trace] tool → list_categories  args: {'lang': 'en'}
[trace] tool ← content='Found 26 section(s):\n  [Hot Beverages] — 6 item(s)...' name='list_categories'
[trace] llm call #3
[trace] tokens  in=1400 out=91  (session total in=4060 out=122 calls=3)
[trace] tool → menu_lookup  args: {'terms': ['Blue Lagoon'], 'lang': 'en'}
[trace] tool ← content='Found 1 match(es):\n  [363] Blue Lagoon (Mocktails) — ₹135' name='menu_lookup'
[trace] llm call #4
[trace] tokens  in=1460 out=85  (session total in=5520 out=207 calls=4)
[trace] tool → add_to_tray  args: {'quantity': 1, 'item_id': 363}
[trace] tool ← content='Tray updated: 1× Blue Lagoon (₹135 each).' name='add_to_tray'
[trace] llm call #5
[trace] tokens  in=1517 out=24  (session total in=7037 out=231 calls=5)
[trace] llm call #6
[trace] tokens  in=1544 out=70  (session total in=8581 out=301 calls=6)
[trace] tool → view_tray  args: {}
[trace] tool ← content='Current tray:\n  1× Blue Lagoon — ₹135 × 1 = ₹135\nTotal: ₹135' name='view_tray'
[trace] llm call #7
[trace] tokens  in=1598 out=25  (session total in=10179 out=326 calls=7)
[trace] llm call #8
[trace] tokens  in=1626 out=32  (session total in=11805 out=358 calls=8)
[trace] tool → place_order  args: {}
[trace] tool ← content="Order placed! Status: placed. I'll keep you updated as it progresses." name='place_order'
[trace] llm call #9
[trace] tokens  in=1667 out=27  (session total in=13472 out=385 calls=9)
```

Note there is no LLM call between `list_categories` returning and `menu_lookup` being
called — that is the short-circuit in action. The categories text was sent directly to
the user without any LLM involvement.
