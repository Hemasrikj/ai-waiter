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


def _term_score(term: str, words: list[str]) -> float:
    """Score how well a single query term matches a list of words from an index entry.

    Returns 95 for a prefix match, otherwise the best character-level ratio (0–100).
    """
    for word in words:
        if word.startswith(term):
            return 95.0
    best = fuzz_process.extractOne(term, words, scorer=fuzz.ratio)
    return best[1] if best else 0.0


def menu_search(terms: list[str], limit: int = 10) -> list[dict]:
    """Fuzzy-search the menu by English keywords. Returns up to `limit` matching MENU entries."""
    query_terms = [t.lower() for t in terms if t]
    if not query_terms:
        return []

    scored: list[tuple[float, int]] = []
    for item_id, text in SEARCH_INDEX:
        words = text.split()
        scores = [_term_score(term, words) for term in query_terms]
        if all(s >= 70 for s in scores):
            scored.append((min(scores), item_id))

    scored.sort(reverse=True)
    return [MENU[item_id] for _, item_id in scored[:limit]]


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
