# Translated Menu Support

## Problem

When a user writes in a regional language (Kannada, Tamil, Telugu etc.), tools returned
English-only menu item names. The LLM then had to re-translate every name in its reply,
burning output tokens proportional to menu size — expensive and slow.

## Solution

Pre-bake translations into `menu.json` at dev time. Tools accept a `lang` parameter and
return names already in the user's language, bypassing LLM translation entirely.

## Pipeline

```
scanned-menu.json → [normalize-menu.py] → normalized-menu.json → [translate.py] → menu.json
```

## Languages Supported

| Code | Language | Status |
|---|---|---|
| `en` | English | always present (source) |
| `kn` | Kannada | pre-existing in `scanned-menu.json` |
| `ta` | Tamil | ✓ 346 names translated |
| `te` | Telugu | ✓ 346 names translated |
| `ml` | Malayalam | ✓ 346 names translated |
| `mr` | Marathi | ✓ 346 names translated |
| `hi` | Hindi | ✓ 346 names translated |
| `ur` | Urdu | ✓ 346 names translated |
| `kok` | Konkani | ✓ 346 names translated |
| `tcy` | Tulu | ✓ 346 names translated |
| `or` | Odia | ✓ 346 names translated |

## Changes Made

### `menu/normalize-menu.py` (renamed from `convert.py`)
- Renamed to clarify its role: normalises structure only, no translation
- Default output changed from `menu.json` → `normalized-menu.json`
- Output contains `en` + `kn` only (same schema as before)

### `menu/translate.py` (new)
- Dev-time script; run manually after menu changes
- Reads `normalized-menu.json`, calls LLM (via `MODEL` from `.env`) once per language
- 346 unique names batched per call — 9 API calls total
- Writes `menu.json` with all 10 languages in `itemText[]` / `sectionText[]`

### `menu/accessor.py`
- `_load_menu()` now reads `itemText[]` and `sectionText[]` to build per-item dicts:
  - `names: {langCode: name}` — localised item name per language
  - `section_paths: {langCode: path}` — localised section path per language
  - `name` and `section_path` (English) kept for backwards compatibility
- `_build_section_index()` similarly adds `names` and `paths` dicts per section
- `format_section_results(results, lang="en")` — new `lang` parameter

### `ai_waiter.py`
- `get_full_menu(lang="en")` — new param; returns names/sections in requested language
- `menu_lookup(terms, lang="en")` — same
- `list_categories(lang="en")` — same; passes `lang` to `format_section_results`
- `SYSTEM_PROMPT` LANGUAGE RULE updated: instructs LLM to pass `lang=` matching user's
  language on every menu tool call

## How It Works at Runtime

1. User writes in Tamil: `"மெனு காட்டு"`
2. LLM detects Tamil, calls `get_full_menu(lang="ta")`
3. Tool returns item names already in Tamil — no LLM translation needed in reply
4. Token cost for full-menu responses drops significantly

## Running the Translation (one-time / after menu edits)

```bash
# Requires MODEL + provider API key in .env
uv run python menu/normalize-menu.py   # → normalized-menu.json
uv run python menu/translate.py        # → menu.json (all 10 languages, ~9 LLM calls)
```
