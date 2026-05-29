# Gemini 2.5 Flash — Cost Breakdown (300 orders)

Pricing source: https://ai.google.dev/pricing (as of 2026-05-30)

---

## How Gemini prompt caching works

Gemini automatically caches the **common prefix** of repeated requests. Because every call in this app starts with the same system prompt (which embeds the full menu), the system prompt + menu tokens (~2,800) are served from cache after the first call in each session — billed at $0.03/1M instead of $0.30/1M.

This is precisely why the menu is embedded in the system prompt rather than fetched via a tool call: it maximises the cacheable prefix.

---

## Per-order conversation model

A typical order flow — greet, browse menu, add 2–3 items, confirm, place — takes roughly **8 LLM turns** (each turn = one API call):

| Turn | Example |
|---|---|
| 1 | Greeting |
| 2 | Customer asks for menu |
| 3 | Customer orders item 1 |
| 4 | Tool call: add_to_tray |
| 5 | Customer orders item 2 |
| 6 | Tool call: view_tray + confirm |
| 7 | Customer confirms |
| 8 | Tool call: place_order |

---

## Token breakdown per turn

| Component | Tokens | Cached? |
|---|---|---|
| System prompt + menu | ~2,800 | Yes — after turn 1 |
| Accumulated conversation history | ~300 avg | No |
| Tool schemas (4 tools) | ~200 | Yes — after turn 1 |
| Model output | ~150 | N/A (output) |

- **Turn 1 (cold):** ~3,300 input tokens billed at full rate
- **Turns 2–8 (warm):** ~3,000 tokens cached + ~300 tokens uncached per turn

---

## 300 orders total

| Metric | Calculation | Total |
|---|---|---|
| API calls | 300 × 8 turns | **2,400 calls** |
| Cold input tokens (turn 1 per order) | 300 × 3,300 | **~990K tokens** |
| Cached input tokens (turns 2–8) | 300 × 7 × 3,000 | **~6.3M tokens** |
| Uncached history tokens (turns 2–8) | 300 × 7 × 300 | **~630K tokens** |
| Output tokens | 2,400 × 150 | **~360K tokens** |

---

## Cost (paid tier)

| | Tokens | Rate | Cost |
|---|---|---|---|
| Cold input | 990K | $0.30 / 1M | **$0.30** |
| Cached input | 6.3M | $0.03 / 1M | **$0.19** |
| Uncached history | 630K | $0.30 / 1M | **$0.19** |
| Output | 360K | $2.50 / 1M | **$0.90** |
| **Total** | | | **~$1.58** |

Compared to ~$3.27 without caching — the embedded menu strategy roughly **halves the cost**.

---

## Notes

- **Free tier** covers this entire workload — Gemini 2.5 Flash has a generous free tier with no per-token charge at low usage.
- At **3,000 orders** (10×), cost is ~$16 with caching vs ~$33 without.
- Caching is automatic for matching prefixes — no code changes needed.
