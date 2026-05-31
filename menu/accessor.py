import json
from pathlib import Path

from rapidfuzz import process as fuzz_process, fuzz

def _load_menu() -> dict[int, dict]:
    menu_path = Path(__file__).parent / "menu.json"
    raw = json.loads(menu_path.read_text(encoding="utf-8"))

    items: dict[int, dict] = {}

    def _walk(sections, ancestor_path=""):
        for section in sections:
            section_name = section["name"]
            full_path = f"{ancestor_path} {section_name}".strip()
            for item in section.get("item", []):
                prep = item.get("preparationType")
                display_name = item["name"]
                if prep:
                    display_name = f"{display_name} ({prep})"
                items[item["id"]] = {
                    "id": item["id"],
                    "name": display_name,
                    "section": section_name,
                    "section_path": full_path,
                    "price": item["price"],
                }
            _walk(section.get("section", []), full_path)

    _walk(raw["section"])
    return items


MENU: dict[int, dict] = _load_menu()


def _build_search_index() -> list[tuple[int, str]]:
    """Each entry: (item_id, searchable_string) — item name + full ancestor section path, lowercased."""
    return [
        (item["id"], f"{item['name']} {item['section_path']}".lower())
        for item in MENU.values()
    ]


SEARCH_INDEX: list[tuple[int, str]] = _build_search_index()


def menu_search(terms: list[str], limit: int = 10) -> list[dict]:
    """Fuzzy-search the menu by English keywords. Returns up to `limit` matching MENU entries."""
    query = " ".join(terms).lower()
    hits = fuzz_process.extract(
        query,
        {item_id: text for item_id, text in SEARCH_INDEX},
        scorer=fuzz.token_set_ratio,
        limit=limit,
        score_cutoff=55,
    )
    matched_ids = [item_id for _text, _score, item_id in hits]
    return [MENU[item_id] for item_id in matched_ids]


def _render_menu(initial_indent: int = 0) -> str:
    raw = json.loads((Path(__file__).parent / "menu.json").read_text(encoding="utf-8"))
    lines = []

    def _walk(sections, depth=0):
        indent = " " * (initial_indent + depth)
        item_indent = " " * (initial_indent + depth + 1)
        for section in sections:
            lines.append(f"{indent}{section['name']}:")
            for item in section.get("item", []):
                prep = item.get("preparationType")
                name = f"{item['name']} ({prep})" if prep else item["name"]
                lines.append(f"{item_indent}[{item['id']}] {name} — ₹{item['price']}")
            _walk(section.get("section", []), depth + 1)
            if depth == 0:
                lines.append("")

    _walk(raw["section"])
    return "\n".join(lines)
