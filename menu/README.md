# Menu

This folder contains the restaurant menu data and the script that converts it to a normalized, relational JSON format.

## Files

| File | Description |
|---|---|
| `scanned-menu.json` | Raw scanned version of the menu (source of truth) |
| `menu.json` | Output of `convert.py` — normalized, camelCase structure |
| `convert.py` | Conversion script (Python) |
| `convert.js` | Conversion script (Node.js, equivalent to `convert.py`) |
| `menu-schema.json` | JSON Schema (draft-07) for `menu.json` |
| `accessor.py` | Python module — loads `menu.json`, exposes `MENU`, `SEARCH_INDEX`, `SECTION_INDEX`, `menu_search`, `menu_section_search`, and `_render_menu` |
| `__init__.py` | Re-exports `MENU`, `menu_search`, and `menu_section_search` as the public `menu` package API |
| `test_accessor.py` | CLI tool — print full menu, fuzzy-search items, or browse/search sections |
| `menu_for_system_prompt.txt` | Pre-rendered menu text for embedding in the LLM system prompt |

---

## Python module (`accessor.py`)

`accessor.py` is the runtime interface between `menu.json` and the rest of the application. All public names are re-exported by `__init__.py`.

### `MENU`

A module-level `dict[int, dict]` loaded once at import time. Keys are item IDs; each value is a flat dict:

```python
{
    "id":           int,   # globally unique item ID
    "name":         str,   # English name, with preparation type appended when present
                           #   e.g. "Gobi Manchurian (dry)"
    "section":      str,   # name of the immediate containing section
    "section_path": str,   # full ancestor path, e.g. "Tasty Starters Manchurian / Chilly"
    "price":        int,   # price in INR
}
```

Typical usage — look up a single item by ID:

```python
from menu import MENU

item = MENU[42]   # {"id": 42, "name": "...", "section": "...", "section_path": "...", "price": ...}
```

### `SEARCH_INDEX`

A module-level `list[tuple[int, str]]` built once at import. Each entry is `(item_id, searchable_string)` where the searchable string is `"{name} {section_path}".lower()`. Used internally by `menu_search`.

### `menu_search(terms, limit=10) -> list[dict]`

Fuzzy-search the menu by English keywords. Returns up to `limit` matching `MENU` entries.

Each term is scored against the words in each item's searchable string using `rapidfuzz.fuzz.ratio` (prefix match scores 95; otherwise best character-level ratio). All terms must score ≥ 70 for an item to be included. Results are sorted by the minimum per-term score descending.

```python
from menu import menu_search

results = menu_search(["masala", "dosa"])
# [{"id": 30, "name": "Masala Dosa", "section_path": "Dosa Treat", "price": 100}, ...]
```

### `SECTION_INDEX`

A module-level `list[dict]` built once at import. Each entry describes one section:

```python
{
    "name":         str,        # section display name
    "path":         str,        # full ancestor path, e.g. "Tasty Starters Manchurian / Chilly"
    "depth":        int,        # 0 = top-level, 1 = nested
    "item_count":   int,        # total items including all sub-sections (recursive)
    "subsections":  list[str],  # direct child section names
    "sample_items": list[str],  # up to 3 item names from this section's direct items
}
```

### `menu_section_search(terms=None) -> list[dict]`

Fuzzy-search menu sections/categories by keyword. Uses identical scoring logic to `menu_search` (all terms ≥ 70, `min`-score sort) against each section's full `path` string. When a parent and its child both match, only the parent is returned.

Pass `None` or `[]` to list all top-level sections (useful for "what food do you have?").

```python
from menu import menu_section_search

# List all top-level categories
menu_section_search([])

# Find sections matching "starters"
menu_section_search(["starters"])
# Returns "Tasty Starters" (41 items, subsections: Manchurian/Chilly, Pepper Dry, Our Special Starters)
# and "Tandoori Starters" (7 items)

# Find a specific nested section
menu_section_search(["manchurian"])
# Returns "Tasty Starters Manchurian / Chilly" (12 items) and "Manchurian Gravy" (7 items)
```

### `_render_menu(initial_indent=0) -> str`

Returns the full menu as a human-readable indented string, suitable for embedding in an LLM system prompt.

```python
from menu.accessor import _render_menu

print(_render_menu())
print(_render_menu(initial_indent=4))  # indent everything by 4 spaces
```

---

## Smoke-testing and search (`test_accessor.py`)

`test_accessor.py` is a CLI tool for printing, searching, and browsing the menu. Always run it with `uv run` from the project root.

### Print full menu

```bash
uv run menu/test_accessor.py menu
```

Prints all items grouped by section. Useful to regenerate `menu_for_system_prompt.txt`:

```bash
uv run menu/test_accessor.py menu > menu/menu_for_system_prompt.txt
```

### Print search index

```bash
uv run menu/test_accessor.py index
```

Dumps all `SEARCH_INDEX` entries — useful for debugging why a term does or doesn't match.

### Fuzzy item search

```bash
uv run menu/test_accessor.py search <terms>
```

Pass one or more English keywords. Scores each term against item names and their full ancestor section path using `rapidfuzz.fuzz.ratio` (threshold 70).

```bash
uv run menu/test_accessor.py search masala dosa
# Found 10 match(es) for 'masala dosa':
#   [30] Masala Dosa (Dosa Treat) — ₹100
#   [34] Paper Massla Dosa (Dosa Treat) — ₹140
#   [36] Butter Masala Dosa (Dosa Treat) — ₹115
#   ...

uv run menu/test_accessor.py search gobi manchurian
# Found 10 match(es) for 'gobi manchurian':
#   [73] Gobi (dry) (Tasty Starters Manchurian / Chilly) — ₹190
#   ...

uv run menu/test_accessor.py search coffee
# Found 2 match(es) for 'coffee':
#   [2] Coffee (Hot Beverages) — ₹32
#   [358] Cold Coffee (Milk Shakes) — ₹110
```

### List all sections

```bash
uv run menu/test_accessor.py sections
```

Lists all 26 top-level sections with item counts, subsections, and sample items.

### Fuzzy section search

```bash
uv run menu/test_accessor.py section-search <terms>
```

Searches section names and paths using the same scoring logic as item search.

```bash
uv run menu/test_accessor.py section-search starters
# Found 2 section(s) for 'starters':
#   [Tasty Starters] — 41 item(s)
#     Subsections: Manchurian / Chilly, Pepper Dry, Our Special Starters
#   [Tandoori Starters] — 7 item(s)
#     Includes: Paneer Tikka, Mushroom Tikka, Baby Corn Tikka

uv run menu/test_accessor.py section-search manchurian
# Found 2 section(s) for 'manchurian':
#   [Tasty Starters Manchurian / Chilly] — 12 item(s)
#     Includes: Gobi (dry), Gobi (gravy), Baby Corn (dry)
#   [Manchurian Gravy] — 7 item(s)
#     Includes: Veg. Ball Manchurian, ...
```

---

## System prompt text (`menu_for_system_prompt.txt`)

`menu_for_system_prompt.txt` is a pre-rendered snapshot of the full menu, ready to paste or `read()` directly into an LLM system prompt. Regenerate after any change to `menu.json`:

```bash
uv run menu/test_accessor.py menu > menu/menu_for_system_prompt.txt
```

---

## Input structure (`scanned-menu.json`)

The source file has a single top-level `menu` object whose keys are section identifiers. Each section carries its display names, an optional availability window, and either a flat `items` array or a `sub_sections` object containing further sections.

```
{
  "menu": {
    "<SECTION_KEY>": {
      "section_name":          string,            // display name in English
      "section_name_kannada":  string,            // display name in Kannada
      "timings":               string | absent,   // e.g. "8 am to 10 pm"
                                                  //   or "12 noon to 3.30 pm - 7 pm to 10.30 pm"
      "items": [                                  // present when section has no sub-sections
        {
          "name":           string,
          "name_kannada":   string,
          "price":          number,               // regular price (INR)
          "timings":        string | absent       // item-level override
        }
      ],
      "sub_sections": {                           // present instead of items (e.g. TASTY_STARTERS)
        "<SUB_SECTION_KEY>": {
          "sub_section_name":          string,
          "sub_section_name_kannada":  string | absent,
          "items": [
            {
              "name":          string,
              "name_kannada":  string,
              "price":         number,            // used when preparation type is not applicable
              "price_dry":     number,            // used when item has dry variant
              "price_gravy":   number             // used when item has gravy variant
            }
          ]
        }
      }
    }
  }
}
```

### Input notes

- There are 26 top-level sections. Only `TASTY_STARTERS` uses `sub_sections`; all others use `items` directly.
- `timings` is a free-text string and may describe two shifts separated by ` - ` (e.g. `"12 noon to 3.30 pm - 7 pm to 10.30 pm"`).
- Items in `MANCHURIAN_CHILLY` have `price_dry` and `price_gravy` instead of `price`.
- All other items have a single `price`.

---

## Output structure (`menu.json`)

The output is a fully embedded hierarchy. Every section and item carries a globally unique `id`. Text (display names) is separated into `sectionText` / `itemText` arrays keyed by `langCode`. All field names use camelCase.

```
{
  "languages": [
    { "code": "en", "name": "English" },
    { "code": "kn", "name": "Kannada" }
  ],
  "section": [
    {
      "id":           number,         // globally unique across sections and items
      "parentId":     number | null,  // null for top-level; parent section id for nested
      "sectionKey":   string,         // e.g. "TASTY_STARTERS"
      "name":         string,         // English display name (shortcut — same as sectionText[en])
      "displayOrder": number,
      "startTime":    string,         // "HH:MM" 24-hour; "00:00" when always available
      "endTime":      string,         // "HH:MM" 24-hour; "23:59" when always available
      "sectionText": [
        { "langCode": "en", "name": string },
        { "langCode": "kn", "name": string }
      ],
      "item": [
        {
          "id":              number,
          "name":            string,          // English display name (shortcut — same as itemText[en])
          "displayOrder":    number,
          "preparationType": null | "dry" | "gravy",
          "startTime":       string,
          "endTime":         string,
          "itemText": [
            { "langCode": "en", "name": string },
            { "langCode": "kn", "name": string }
          ],
          "price": number
        }
      ],
      "section": [ ... ]   // nested child sections — same shape, recursively
    }
  ]
}
```

### Output notes

- **Global IDs** — sections and items share one incrementing counter, so `id` is unique across the entire document.
- **`name` shortcut** — both Section and Item carry a top-level `name` field with the English display name, duplicating the `en` entry in `sectionText` / `itemText`.
- **Self-referencing sections** — child sections are embedded under the parent's `section` array and also carry `parentId`.
- **Timings** — free-text timing strings are parsed to `startTime` / `endTime` in 24-hour `HH:MM`. Two-shift timings use the first shift's start and the last shift's end. Missing timings default to `00:00` / `23:59` (always available).
- **Localization** — all display strings live in `sectionText` / `itemText`. Adding a new language requires only inserting additional `{ langCode, name }` entries.

### Item splitting rules

Source items are expanded into multiple output items in two cases:

| Rule | Trigger | Result |
|---|---|---|
| **Slash choice** | `name` contains ` / ` (e.g. `"Coffee / Tea"`) | Split into 2 items — one per variant — sharing the same `displayOrder` and `price`. Kannada name is split on ` /` accordingly. |
| **Dry / gravy** | Item has both `price_dry` and `price_gravy` fields | Split into 2 items with `preparationType: "dry"` and `preparationType: "gravy"`, each with its own price. |

---

## Schema (`menu-schema.json`)

`menu-schema.json` is a [JSON Schema draft-07](https://json-schema.org/specification-links#draft-7) description of `menu.json`.

Validate the output after regeneration using [ajv-cli](https://github.com/ajv-validator/ajv-cli):

```bash
npm install -g ajv-cli
ajv validate -s menu/menu-schema.json -d menu/menu.json
```

Or with Python ([jsonschema](https://python-jsonschema.readthedocs.io)):

```bash
uv add --dev jsonschema
uv run python -c "
import json, jsonschema
schema = json.load(open('menu/menu-schema.json'))
data   = json.load(open('menu/menu.json'))
jsonschema.validate(data, schema)
print('valid')
"
```

---

## Running the conversion

```bash
# Reads scanned-menu.json, writes menu.json (both in this folder)
uv run python menu/convert.py

# Explicit paths
uv run python menu/convert.py <input.json> <output.json>
uv run python menu/convert.py menu/scanned-menu.json menu/menu.json
```
