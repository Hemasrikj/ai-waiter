# Plan: Replace inline menu in system prompt with `menu_lookup` tool

## Context

System prompt currently embeds the full rendered menu (~2437 tokens for 339 items across 29 sections).
Total system prompt is ~2600+ tokens. This is the root cause of small local model failure — they get overwhelmed.

Goal: remove the menu from the system prompt entirely, add a `menu_lookup` tool the LLM calls to
find items by keyword, cutting system prompt to ~400–500 tokens.

## Is RAG the right fit?

**No — 339 items is too small for vector RAG.** Classic RAG (embeddings + cosine similarity) is designed
for thousands-to-millions of documents. For 339 named items:

- Fuzzy/keyword matching is equally accurate, zero ML dependencies, microseconds latency
- The LLM already handles multilingual: it extracts English terms from any language query, then calls the tool
- No embedding model download, no FAISS, no sentence-transformers needed

**Recommended approach: fuzzy string matching with `rapidfuzz`** (or `difflib` as zero-dependency fallback).

## How it works

1. **At startup**, build an in-memory index: for each item, concatenate `name + full_ancestor_path` → one searchable string per item.
2. **`menu_lookup(terms)`** takes a list of English keywords the LLM extracted (e.g. `["dosa", "masala"]` or `["coffee"]`), fuzzy-scores them against the index, returns top-N matches with `id`, `name`, `section`, `price`.
3. **System prompt shrinks**: remove `_render_menu()`, replace with a short instruction: *"Use menu_lookup to find items before adding to tray. Pass English keywords."*

## Multilingual flow (no change needed in LLM)

```
User (Tamil): "ஒரு மசால் தோசை வேண்டும்"
LLM (already multilingual): understands → calls menu_lookup(["masala", "dosa"])
menu_lookup → returns [id=30, "Masala Dosa", "Dosa Treat", ₹110]
LLM → calls add_to_tray(item_id=30, quantity=1)
```

The menu JSON already has `itemText` with `langCode: "kn"` (Kannada) entries — these can optionally
be included in the search index for direct native-script matching if needed later.

## Files to change

### `menu/accessor.py`
- Add `build_search_index()` → returns `list[tuple[int, str]]` (item_id, searchable_string)
- Export `SEARCH_INDEX` at module load

### `ai_waiter.py`
- Add `menu_lookup` tool using `rapidfuzz.process.extract` (falls back to `difflib.get_close_matches`)
- Remove `_render_menu()` from `SYSTEM_PROMPT`
- Shorten system prompt to ~15 lines: role, workflow steps, instruction to use `menu_lookup`
- Add `menu_lookup` to `tools` list

### `pyproject.toml`
- Add `rapidfuzz` as optional dependency (graceful fallback to difflib if absent)

## `menu_lookup` tool signature

```python
@tool
def menu_lookup(terms: list[str]) -> str:
    """Search the menu by item name, section name, or type (English keywords).
    Returns up to 10 matching items with their IDs, names, sections, and prices.
    Always call this before add_to_tray to get the correct item_id."""
```

Returns a compact text block, e.g.:
```
Found 3 matches:
  [30] Masala Dosa (Dosa Treat) — ₹110
  [31] Plain Dosa (Dosa Treat) — ₹90
  [33] Set Dosa (Dosa Treat) — ₹100
```

## Search index construction

The menu has up to 3 levels: `Top Section > Sub-section > item name`.
Example: item [73] "Gobi" lives under `Tasty Starters > Manchurian / Chilly`.

Each item's search string = `"{item_name} {full_section_path_all_ancestors}"` → lowercased.
The `_walk` in `accessor.py` already recurses — extend it to accumulate the **full ancestor path**
(space-separated, no `>` punctuation) into each item's search string.

Examples of resulting search strings:
- `[73]` → `"gobi tasty starters manchurian chilly"`
- `[30]` → `"masala dosa dosa treat"`
- `[92]` → `"crispy honey potato tasty starters our special starters"`

Query: join all terms → fuzzy match with `token_set_ratio` scorer, threshold 60, top 10 results.

This way `menu_lookup(["manchurian"])` returns all Manchurian variants (dry + gravy sections),
and `menu_lookup(["starters", "gobi"])` narrows to gobi items under starters.

## Token savings

| Before | After |
|--------|-------|
| ~2600 tokens system prompt | ~450 tokens system prompt |
| Full menu always in context | Menu fetched only when needed |
| Breaks small models | Small models handle short prompts |

## Verification

1. Run `python console.py`, type "do you have masala dosa?" → LLM calls `menu_lookup(["masala","dosa"])`, gets id back, no hallucinated ids
2. Type in Tamil/Kannada/Hindi → LLM translates internally, tool returns correct English match
3. Confirm `add_to_tray` uses returned item_id correctly
4. Check token count: `len(SYSTEM_PROMPT.split()) * 1.3` should be < 500
