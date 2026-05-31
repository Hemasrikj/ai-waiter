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


def _build_section_index() -> list[dict]:
    """Build a flat list of all sections with hierarchy metadata."""
    raw = json.loads((Path(__file__).parent / "menu.json").read_text(encoding="utf-8"))
    sections: list[dict] = []

    def _count_items(section) -> int:
        total = len(section.get("item", []))
        for sub in section.get("section", []):
            total += _count_items(sub)
        return total

    def _walk(section_list, ancestor_path="", depth=0):
        for section in section_list:
            name = section["name"]
            path = f"{ancestor_path} {name}".strip()
            direct_item_names = [
                (f"{it['name']} ({it['preparationType']})" if it.get("preparationType") else it["name"])
                for it in section.get("item", [])
            ]
            subsection_names = [
                {"name": s["name"], "item_count": _count_items(s)}
                for s in section.get("section", [])
            ]
            sections.append({
                "name": name,
                "path": path,
                "depth": depth,
                "item_count": _count_items(section),
                "subsections": subsection_names,
                "sample_items": direct_item_names[:3],
            })
            _walk(section.get("section", []), path, depth + 1)

    _walk(raw["section"])
    return sections


SECTION_INDEX: list[dict] = _build_section_index()


def format_section_results(results: list[dict]) -> str:
    """Format a list of section dicts (from menu_section_search) into a human-readable string.
    Returns only the section lines — no header — so callers can prepend their own."""
    lines = []
    for section in results:
        lines.append(f"  [{section['path']}] — {section['item_count']} item(s)")
        if section["subsections"]:
            sub_str = ", ".join(f"{s['name']} ({s['item_count']})" for s in section["subsections"])
            lines.append(f"    Subsections: {sub_str}")
        if section["sample_items"]:
            lines.append(f"    Includes: {', '.join(section['sample_items'])}")
    return "\n".join(lines)


def menu_section_search(terms: list[str] | None = None) -> list[dict]:
    """Search menu sections/categories by keyword using the same scoring as menu_search.
    Returns all top-level sections when terms is empty — useful for listing all categories."""
    if not terms:
        return [s for s in SECTION_INDEX if s["depth"] == 0]

    query_terms = [t.lower() for t in terms if t]
    scored: list[tuple[float, dict]] = []
    for section in SECTION_INDEX:
        words = section["path"].lower().split()
        scores = [_term_score(term, words) for term in query_terms]
        if all(s >= 70 for s in scores):
            scored.append((min(scores), section))

    scored.sort(reverse=True, key=lambda x: x[0])

    # deduplicate: if both a parent and its child match, keep only the parent
    seen_paths: set[str] = set()
    results: list[dict] = []
    for _, section in scored:
        if not any(section["path"].startswith(p + " ") for p in seen_paths):
            seen_paths.add(section["path"])
            results.append(section)
    return results


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
