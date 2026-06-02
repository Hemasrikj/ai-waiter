"""
Translate all item and section names from normalized-menu.json into 9 Indian languages.
Reads:  menu/normalized-menu.json
Writes: menu/menu.json

Usage:
    uv run python menu/translate.py

Requires: MODEL and the relevant provider API key in .env (same as the waiter).
One LLM call is made per target language — 9 calls total, all names batched per call.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage

load_dotenv()

_dir = Path(__file__).parent
IN_PATH  = _dir / "normalized-menu.json"
OUT_PATH = _dir / "menu.json"

TARGET_LANGUAGES = [
    ("ta",  "Tamil"),
    ("te",  "Telugu"),
    ("ml",  "Malayalam"),
    ("mr",  "Marathi"),
    ("hi",  "Hindi"),
    ("ur",  "Urdu"),
    ("kok", "Konkani"),
    ("tcy", "Tulu"),
    ("or",  "Odia"),
]


def _collect_names(data: dict) -> list[str]:
    """Walk normalized-menu.json and collect all unique English display names."""
    names: set[str] = set()

    def _walk_sections(sections):
        for section in sections:
            for entry in section.get("sectionText", []):
                if entry["langCode"] == "en":
                    names.add(entry["name"])
            for item in section.get("item", []):
                for entry in item.get("itemText", []):
                    if entry["langCode"] == "en":
                        names.add(entry["name"])
            _walk_sections(section.get("section", []))

    _walk_sections(data["section"])
    return sorted(names)


def _translate_batch(names: list[str], lang_code: str, lang_name: str, llm) -> dict[str, str]:
    """Send one batched LLM call; return {english: translation} dict."""
    prompt = (
        f"Translate these South Indian restaurant menu item and section names to {lang_name}.\n"
        f"Return ONLY a valid JSON object mapping each English name to its {lang_name} translation.\n"
        f"Rules:\n"
        f"- Preserve brand names and proper nouns that have no standard {lang_name} equivalent.\n"
        f"- Use transliteration (not translation) for widely-known food terms if a translation would be unrecognisable.\n"
        f"- Do not add any explanation or markdown — only the JSON object.\n\n"
        f"Names:\n{json.dumps(names, ensure_ascii=False)}"
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    text = response.content.strip()
    # Strip markdown code fences if the model wraps the JSON
    if text.startswith("```"):
        text = "\n".join(
            line for line in text.splitlines()
            if not line.startswith("```")
        ).strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"  WARNING: JSON parse failed for {lang_name}: {exc}", file=sys.stderr)
        print(f"  Raw response (first 200 chars): {text[:200]}", file=sys.stderr)
        result = {}
    return result


def _inject_translations(data: dict, translations: dict[str, dict[str, str]]) -> None:
    """
    Mutate data in-place, adding translated entries to itemText/sectionText arrays.
    translations: {lang_code: {english_name: translated_name}}
    """
    def _inject_text_array(text_array: list, lang_code: str, lang_translations: dict):
        en_name = next((e["name"] for e in text_array if e["langCode"] == "en"), None)
        if en_name and en_name in lang_translations:
            # Only add if not already present
            if not any(e["langCode"] == lang_code for e in text_array):
                text_array.append({"langCode": lang_code, "name": lang_translations[en_name]})

    def _walk_sections(sections):
        for section in sections:
            for lang_code, lang_translations in translations.items():
                _inject_text_array(section.get("sectionText", []), lang_code, lang_translations)
            for item in section.get("item", []):
                for lang_code, lang_translations in translations.items():
                    _inject_text_array(item.get("itemText", []), lang_code, lang_translations)
            _walk_sections(section.get("section", []))

    _walk_sections(data["section"])


def main():
    model_name = os.getenv("MODEL")
    if not model_name:
        print("ERROR: MODEL env var not set. Add MODEL=... to .env", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {IN_PATH}")
    data = json.loads(IN_PATH.read_text(encoding="utf-8"))

    names = _collect_names(data)
    print(f"Collected {len(names)} unique English names to translate")

    llm = init_chat_model(model_name)
    translations: dict[str, dict[str, str]] = {}

    for lang_code, lang_name in TARGET_LANGUAGES:
        print(f"Translating to {lang_name} ({lang_code})...", end=" ", flush=True)
        result = _translate_batch(names, lang_code, lang_name, llm)
        translations[lang_code] = result
        print(f"{len(result)} names translated")

    _inject_translations(data, translations)

    # Update languages array
    existing_codes = {l["code"] for l in data.get("languages", [])}
    lang_display = {
        "ta": "Tamil", "te": "Telugu", "ml": "Malayalam", "mr": "Marathi",
        "hi": "Hindi", "ur": "Urdu", "kok": "Konkani", "tcy": "Tulu", "or": "Odia",
    }
    for code, name in lang_display.items():
        if code not in existing_codes:
            data["languages"].append({"code": code, "name": name})

    OUT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")
    print(f"Languages in output: {[l['code'] for l in data['languages']]}")


if __name__ == "__main__":
    main()
