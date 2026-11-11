from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from helpers.common import fold_text, read_json, write_json


TEXT_KEYS = {"footage_summary", "user_context", "language", "editor"}
EDITORS = ("resolve", "premiere", "fcpx", "other")


def context_path(edit_dir: Path) -> Path:
    return edit_dir / "project.json"


def empty_context() -> dict[str, Any]:
    return {
        "version": 1,
        "footage_summary": "",
        "user_context": "",
        "language": None,
        "editor": None,
        "glossary": [],
        "notes": [],
    }


def load_context(edit_dir: Path) -> dict[str, Any]:
    path = context_path(edit_dir)
    context = empty_context()
    if path.exists():
        stored = read_json(path)
        if isinstance(stored, dict):
            context.update(stored)
    return context


def parse_term(raw: str) -> dict[str, Any]:
    """Parse 'Correct Term=misheard one|misheard two' into a glossary entry."""
    term, _, heard = raw.partition("=")
    term = term.strip()
    if not term:
        raise ValueError(f"glossary term is empty in {raw!r}")
    heard_as = [item.strip() for item in heard.split("|") if item.strip()]
    return {"term": term, "heard_as": heard_as}


def add_term(context: dict[str, Any], raw: str) -> None:
    entry = parse_term(raw)
    for existing in context["glossary"]:
        if fold_text(existing.get("term", "")) == fold_text(entry["term"]):
            known = {fold_text(item) for item in existing.get("heard_as") or []}
            existing.setdefault("heard_as", [])
            existing["heard_as"].extend(item for item in entry["heard_as"] if fold_text(item) not in known)
            return
    context["glossary"].append(entry)


def remove_term(context: dict[str, Any], term: str) -> None:
    context["glossary"] = [item for item in context["glossary"] if fold_text(item.get("term", "")) != fold_text(term)]


def set_value(context: dict[str, Any], item: str) -> None:
    key, separator, value = item.partition("=")
    key = key.strip()
    if not separator:
        raise ValueError(f"expected key=value, got {item!r}")
    if key not in TEXT_KEYS:
        raise ValueError(f"unknown context key {key!r}; expected one of {sorted(TEXT_KEYS)}")
    value = value.strip()
    if key == "editor" and value and value not in EDITORS:
        raise ValueError(f"editor must be one of {list(EDITORS)}")
    context[key] = value or None if key in {"language", "editor"} else value


def glossary_terms(context: dict[str, Any]) -> list[str]:
    return [str(item["term"]) for item in context.get("glossary") or [] if item.get("term")]


def glossary_prompt(context: dict[str, Any], limit: int = 40) -> str | None:
    """A short prompt that biases Whisper toward the project's names and terms."""
    terms = glossary_terms(context)[:limit]
    if not terms:
        return None
    return "Glossary: " + ", ".join(terms) + "."


def update_context(
    edit_dir: Path,
    *,
    set_values: list[str] | None = None,
    add_terms: list[str] | None = None,
    remove_terms: list[str] | None = None,
    add_notes: list[str] | None = None,
) -> dict[str, Any]:
    context = load_context(edit_dir)
    for item in set_values or []:
        set_value(context, item)
    for item in add_terms or []:
        add_term(context, item)
    for item in remove_terms or []:
        remove_term(context, item)
    for note in add_notes or []:
        text = note.strip()
        if text:
            context["notes"].append({"date": date.today().isoformat(), "text": text})
    write_json(context_path(edit_dir), context)
    return context


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show or change what is known about this footage folder (stored in edit/project.json)"
    )
    parser.add_argument("--edit-dir", type=Path, required=True)
    parser.add_argument("--set", dest="set_values", action="append", default=[], metavar="KEY=VALUE",
                        help=f"Set one of {sorted(TEXT_KEYS)}")
    parser.add_argument("--add-term", dest="add_terms", action="append", default=[], metavar="TERM[=HEARD|HEARD]",
                        help="Add a name or term, optionally with the ways it gets misheard")
    parser.add_argument("--remove-term", dest="remove_terms", action="append", default=[], metavar="TERM")
    parser.add_argument("--add-note", dest="add_notes", action="append", default=[], metavar="TEXT",
                        help="Record something learned about this project or how the user wants it cut")
    args = parser.parse_args()

    edit_dir = args.edit_dir.resolve()
    try:
        if args.set_values or args.add_terms or args.remove_terms or args.add_notes:
            context = update_context(
                edit_dir,
                set_values=args.set_values,
                add_terms=args.add_terms,
                remove_terms=args.remove_terms,
                add_notes=args.add_notes,
            )
        else:
            context = load_context(edit_dir)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({"path": str(context_path(edit_dir)), "context": context}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
