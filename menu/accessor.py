import json
from pathlib import Path


def _load_menu() -> dict[int, dict]:
    menu_path = Path(__file__).parent / "menu.json"
    raw = json.loads(menu_path.read_text(encoding="utf-8"))

    items: dict[int, dict] = {}

    def _walk(sections, parent_name=None):
        for section in sections:
            section_name = section["name"]
            for item in section.get("item", []):
                prep = item.get("preparationType")
                display_name = item["name"]
                if prep:
                    display_name = f"{display_name} ({prep})"
                items[item["id"]] = {
                    "id": item["id"],
                    "name": display_name,
                    "section": section_name,
                    "price": item["price"],
                }
            _walk(section.get("section", []))

    _walk(raw["section"])
    return items


MENU: dict[int, dict] = _load_menu()


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
