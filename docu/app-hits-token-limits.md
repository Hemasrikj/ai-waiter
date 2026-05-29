# Why the App Hits Gemini Free Tier Limits Quickly

---

## Symptom

After one or two conversations, the app throws:

```
RESOURCE_EXHAUSTED
```

The session is dead for the rest of the day.

---

## Root cause: free tier limits are very tight

The Gemini 2.5 Flash free tier is intended for occasional development testing — not even light app usage. Commonly enforced limits:

| Limit | Free tier |
|---|---|
| Requests per minute (RPM) | ~10 |
| Requests per day (RPD) | ~250–500 |
| Tokens per minute (TPM) | Low (exact value shown in AI Studio) |

All three limits are enforced independently. Hitting any one of them triggers `RESOURCE_EXHAUSTED`.

---

## Why this app burns quota fast

A single user message does not equal one API call. The LangGraph agent loop fires **multiple calls per user turn**:

```
User message
  → call 1: chatbot decides to call a tool
  → call 2: tool result fed back, chatbot generates reply
  (sometimes call 3 if a second tool is needed)
```

A typical order conversation of 5 user messages can trigger **10–15 API calls** and **30,000–50,000 tokens** — enough to exhaust the free daily quota in a single session.

The large system prompt (~2,800 tokens including the full menu) compounds this: every API call carries the full prefix, burning through the tokens-per-minute limit quickly even when the request count is low.

---

## The fix: enable billing

At the actual usage cost (~$1.58 per 300 orders — see [gemini-cost-breakdown.md](gemini-cost-breakdown.md)), billing is essentially free in practice. The free tier is not viable for anything beyond a few isolated test calls.

### Steps

1. Go to [AI Studio](https://aistudio.google.com) → Settings → Billing
2. Link a Google Cloud billing account
3. Optionally set a budget alert at $5 — you will almost certainly never hit it

Once billing is enabled, limits jump to levels suitable for real usage (e.g. 1,000 RPM, millions of tokens per day).

---

## Workaround while still on the free tier

If you need to test without billing, space out calls manually and keep sessions short:
- One or two exchanges per run, then wait a few minutes before the next
- Use `restart` to reset state without starting a new process (saves one greeting call)
- Check your current quota usage at [aistudio.google.com/rate-limit](https://aistudio.google.com/rate-limit)
