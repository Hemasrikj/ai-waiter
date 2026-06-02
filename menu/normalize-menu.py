"""
Normalise scanned-menu.json to the structured normalized-menu.json format.

Usage:
    python menu/normalize-menu.py [input.json] [output.json]

Defaults: scanned-menu.json → normalized-menu.json (same directory as this script).
"""

import json
import re
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

_dir = Path(__file__).parent
args = sys.argv[1:]
menu_path = Path(args[0]) if len(args) > 0 else _dir / "scanned-menu.json"
out_path  = Path(args[1]) if len(args) > 1 else _dir / "normalized-menu.json"

# ── Timing parser ─────────────────────────────────────────────────────────────

def _parse_half(raw: str) -> str | None:
    s = raw.strip().lower()
    if s in ("12 noon", "noon"):
        return "12:00"
    m = re.match(r"^(\d+)(?:[.:,](\d+))?\s*(am|pm)$", s)
    if not m:
        return None
    h   = int(m.group(1))
    min_ = int(m.group(2)) if m.group(2) else 0
    if m.group(3) == "am":
        if h == 12:
            h = 0
    else:
        if h != 12:
            h += 12
    return f"{h:02d}:{min_:02d}"


def _parse_timing(raw: str | None) -> dict:
    if not raw:
        return {"startTime": "00:00", "endTime": "23:59"}

    # Two-shift timings: "12 noon to 3.30 pm - 7 pm to 10.30 pm"
    # Use widest window: first shift start → last shift end.
    shifts = re.split(r"\s*-\s*", raw)
    parsed = []
    for shift in shifts:
        parts = re.split(r"\s+to\s+", shift, flags=re.IGNORECASE)
        if len(parts) != 2:
            continue
        start = _parse_half(parts[0])
        end   = _parse_half(parts[1])
        if start and end:
            parsed.append((start, end))

    if not parsed:
        print(f"  WARN: could not parse timing \"{raw}\", defaulting to 00:00-23:59",
              file=sys.stderr)
        return {"startTime": "00:00", "endTime": "23:59"}

    return {"startTime": parsed[0][0], "endTime": parsed[-1][1]}

# ── Name helpers ──────────────────────────────────────────────────────────────

def _to_mixed_case(s: str | None) -> str | None:
    """Title-case a string only when every alpha character is uppercase."""
    if not s or not re.search(r"[a-zA-Z]", s):
        return s
    if s != s.upper():
        return s  # already mixed-case — leave untouched
    return re.sub(r"\b[a-z]", lambda m: m.group().upper(), s.lower())


_slash_split_count = 0

def _split_slash_variants(src: dict) -> list[dict]:
    """
    Items whose English name contains ' / ' represent a customer choice between
    two variants at the same price.  Split them into separate items so each
    can be ordered or displayed independently.
    """
    global _slash_split_count
    SEP_EN, SEP_KN = " / ", " /"

    if SEP_EN not in src["name"]:
        return [src]

    _slash_split_count += 1
    en_parts = src["name"].split(SEP_EN)
    kn_parts = src.get("name_kannada", "").split(SEP_KN) if src.get("name_kannada") else []

    return [
        {**src,
         "name": en_parts[i].strip(),
         "name_kannada": (kn_parts[i].strip() if i < len(kn_parts) else None) or None}
        for i in range(len(en_parts))
    ]

# ── ID sequence ───────────────────────────────────────────────────────────────

_id_seq = 0

def _next_id() -> int:
    global _id_seq
    _id_seq += 1
    return _id_seq

# ── Builders ──────────────────────────────────────────────────────────────────

def _build_items(items_array: list) -> list:
    result = []
    for idx, src in enumerate(items_array or []):
        timing       = _parse_timing(src.get("timings"))
        display_order = idx + 1

        if src.get("price_dry") is not None and src.get("price_gravy") is not None:
            # Item offered in two preparation styles at different prices
            for prep_type, price in [("dry", src["price_dry"]), ("gravy", src["price_gravy"])]:
                for variant in _split_slash_variants(src):
                    en_name = _to_mixed_case(variant["name"])
                    kn_name = variant.get("name_kannada")
                    item_text = [{"langCode": "en", "name": en_name}]
                    if kn_name:
                        item_text.append({"langCode": "kn", "name": kn_name})
                    result.append({
                        "id":              _next_id(),
                        "name":            en_name,
                        "displayOrder":    display_order,
                        "preparationType": prep_type,
                        "startTime":       timing["startTime"],
                        "endTime":         timing["endTime"],
                        "itemText":        item_text,
                        "price":           price,
                    })
        else:
            # Single price; may still be a slash-separated choice
            for variant in _split_slash_variants(src):
                en_name = _to_mixed_case(variant["name"])
                kn_name = variant.get("name_kannada")
                item_text = [{"langCode": "en", "name": en_name}]
                if kn_name:
                    item_text.append({"langCode": "kn", "name": kn_name})
                result.append({
                    "id":              _next_id(),
                    "name":            en_name,
                    "displayOrder":    display_order,
                    "preparationType": None,
                    "startTime":       timing["startTime"],
                    "endTime":         timing["endTime"],
                    "itemText":        item_text,
                    "price":           src.get("price"),
                })
    return result


def _build_section(key: str, src: dict, display_order: int, parent_id: int | None) -> dict:
    id_      = _next_id()
    timing   = _parse_timing(src.get("timings"))
    en_name  = _to_mixed_case(src.get("section_name") or src.get("sub_section_name") or key)
    kn_name  = src.get("section_name_kannada") or src.get("sub_section_name_kannada")

    section_text = [{"langCode": "en", "name": en_name}]
    if kn_name:
        section_text.append({"langCode": "kn", "name": kn_name})

    child_sections = [
        _build_section(sub_key, sub_src, sub_idx + 1, id_)
        for sub_idx, (sub_key, sub_src) in enumerate(src.get("sub_sections", {}).items())
    ]

    return {
        "id":           id_,
        "parentId":     parent_id,
        "sectionKey":   key,
        "name":         en_name,
        "displayOrder": display_order,
        "startTime":    timing["startTime"],
        "endTime":      timing["endTime"],
        "sectionText":  section_text,
        "item":         _build_items(src.get("items", [])),
        "section":      child_sections,
    }

# ── Main ──────────────────────────────────────────────────────────────────────

menu = json.loads(menu_path.read_text(encoding="utf-8"))["menu"]

languages = [
    {"code": "en", "name": "English"},
    {"code": "kn", "name": "Kannada"},
]

sections = [
    _build_section(key, src, idx + 1, None)
    for idx, (key, src) in enumerate(menu.items())
]

out_path.write_text(
    json.dumps({"languages": languages, "section": sections}, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

# ── Summary ───────────────────────────────────────────────────────────────────

def _count(sections):
    total_sec = total_items = 0
    for s in sections:
        total_sec  += 1
        total_items += len(s["item"])
        sub_sec, sub_items = _count(s["section"])
        total_sec  += sub_sec
        total_items += sub_items
    return total_sec, total_items

total_sections, total_items = _count(sections)
print(f"Input  : {menu_path}")
print(f"Output : {out_path}")
print(f"  languages   : {len(languages)}")
print(f"  sections    : {total_sections} (all levels)")
print(f"  items       : {total_items}")
print(f"  slash splits: {_slash_split_count} source items expanded into pairs")
