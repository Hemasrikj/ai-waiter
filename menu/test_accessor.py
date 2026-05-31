import sys
from accessor import _render_menu, menu_search, menu_section_search, format_section_results, SEARCH_INDEX


def fuzzy_search(query: str) -> str:
    terms = query.split()
    results = menu_search(terms)
    if not results:
        return f"No matches for: {query!r}"
    lines = [f"Found {len(results)} match(es) for {query!r}:"]
    for item in results:
        lines.append(f"  [{item['id']}] {item['name']} ({item['section_path']}) — ₹{item['price']}")
    return "\n".join(lines)


def section_search(query: str) -> str:
    terms = query.split() if query else []
    results = menu_section_search(terms if terms else None)
    if not results:
        return f"No sections found for: {query!r}"
    label = "all top-level sections" if not terms else repr(query)
    return f"Found {len(results)} section(s) for {label}:\n{format_section_results(results)}"


def print_search_index() -> str:
    lines = [f"SEARCH_INDEX ({len(SEARCH_INDEX)} entries):"]
    for item_id, text in SEARCH_INDEX:
        lines.append(f"  [{item_id}] {text}")
    return "\n".join(lines)


def print_usage():
    print("Usage:")
    print("  uv run menu/test_accessor.py menu                    — print full menu")
    print("  uv run menu/test_accessor.py index                   — print SEARCH_INDEX")
    print("  uv run menu/test_accessor.py search <terms>          — fuzzy item search (e.g. search masala dosa)")
    print("  uv run menu/test_accessor.py sections                — list all top-level sections")
    print("  uv run menu/test_accessor.py section-search <terms>  — fuzzy section search (e.g. section-search starters)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_usage()
    elif sys.argv[1] == "menu":
        print(_render_menu())
    elif sys.argv[1] == "index":
        print(print_search_index())
    elif sys.argv[1] == "search":
        if len(sys.argv) < 3:
            print("Provide search terms. Example: python test_accessor.py search paneer")
        else:
            query = " ".join(sys.argv[2:])
            print(fuzzy_search(query))
    elif sys.argv[1] == "sections":
        print(section_search(""))
    elif sys.argv[1] == "section-search":
        if len(sys.argv) < 3:
            print("Provide search terms. Example: python test_accessor.py section-search starters")
        else:
            query = " ".join(sys.argv[2:])
            print(section_search(query))
    else:
        print_usage()
