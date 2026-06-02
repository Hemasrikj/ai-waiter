import json
from pathlib import Path

from rapidfuzz import process as fuzz_process, fuzz

def _load_menu() -> dict[int, dict]:
    menu_path = Path(__file__).parent / "menu.json"
    raw = json.loads(menu_path.read_text(encoding="utf-8"))

    items: dict[int, dict] = {}

    def _walk(sections, ancestor_path="", ancestor_paths=None):
        if ancestor_paths is None:
            ancestor_paths = {}
        for section in sections:
            section_name = section["name"]
            full_path = f"{ancestor_path} {section_name}".strip()

            # Build per-language section paths for this level
            section_names_by_lang = {e["langCode"]: e["name"] for e in section.get("sectionText", [])}
            full_paths_by_lang = {}
            for lang, sname in section_names_by_lang.items():
                parent = ancestor_paths.get(lang, "")
                full_paths_by_lang[lang] = f"{parent} {sname}".strip() if parent else sname

            for item in section.get("item", []):
                prep = item.get("preparationType")
                display_name = item["name"]
                if prep:
                    display_name = f"{display_name} ({prep})"

                # Build per-language names dict
                names_by_lang = {e["langCode"]: e["name"] for e in item.get("itemText", [])}
                if prep:
                    names_by_lang = {lang: f"{n} ({prep})" for lang, n in names_by_lang.items()}

                items[item["id"]] = {
                    "id": item["id"],
                    "name": display_name,           # English — backwards compat
                    "section": section_name,         # English — backwards compat
                    "section_path": full_path,       # English — backwards compat
                    "names": names_by_lang,
                    "section_paths": full_paths_by_lang,
                    "price": item["price"],
                }
            _walk(section.get("section", []), full_path, full_paths_by_lang)

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
    # Flatten multi-word terms into individual words so "Litchi Spacral" → ["litchi", "spacral"]
    query_terms = [w for t in terms if t for w in t.lower().split()]
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

    def _walk(section_list, ancestor_path="", ancestor_paths=None, depth=0):
        if ancestor_paths is None:
            ancestor_paths = {}
        for section in section_list:
            name = section["name"]
            path = f"{ancestor_path} {name}".strip()

            section_names_by_lang = {e["langCode"]: e["name"] for e in section.get("sectionText", [])}
            paths_by_lang = {}
            for lang, sname in section_names_by_lang.items():
                parent = ancestor_paths.get(lang, "")
                paths_by_lang[lang] = f"{parent} {sname}".strip() if parent else sname

            direct_item_names_by_lang: dict[str, list[str]] = {}
            for it in section.get("item", []):
                it_names = {e["langCode"]: e["name"] for e in it.get("itemText", [])}
                if it.get("preparationType"):
                    it_names = {lc: f"{n} ({it['preparationType']})" for lc, n in it_names.items()}
                for lc, n in it_names.items():
                    direct_item_names_by_lang.setdefault(lc, []).append(n)
            subsection_entries = [
                {"name": s["name"], "names": {e["langCode"]: e["name"] for e in s.get("sectionText", [])}, "item_count": _count_items(s)}
                for s in section.get("section", [])
            ]
            sections.append({
                "name": name,
                "path": path,
                "names": section_names_by_lang,
                "paths": paths_by_lang,
                "depth": depth,
                "item_count": _count_items(section),
                "subsections": subsection_entries,
                "sample_items": direct_item_names_by_lang,
            })
            _walk(section.get("section", []), path, paths_by_lang, depth + 1)

    _walk(raw["section"])
    return sections


SECTION_INDEX: list[dict] = _build_section_index()


def format_section_results(results: list[dict], lang: str = "en") -> str:
    """Format a list of section dicts (from menu_section_search) into a human-readable string.
    Returns only the section lines — no header — so callers can prepend their own."""
    lines = []
    for section in results:
        path = section["paths"].get(lang, section["path"])
        lines.append(f"  [{path}] — {section['item_count']} item(s)")
        if section["subsections"]:
            sub_str = ", ".join(
                f"{s['names'].get(lang, s['name'])} ({s['item_count']})"
                for s in section["subsections"]
            )
            lines.append(f"    Subsections: {sub_str}")
        sample = section["sample_items"]
        if isinstance(sample, dict):
            sample_names = sample.get(lang, sample.get("en", []))[:3]
        else:
            sample_names = sample[:3]
        if sample_names:
            lines.append(f"    Includes: {', '.join(sample_names)}")
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
