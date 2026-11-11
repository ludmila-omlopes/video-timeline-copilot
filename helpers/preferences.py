from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from datetime import date

from helpers.common import read_json, write_json


CUT_STYLES = ("tight", "social", "highlight", "documentary", "longform")
DEFAULT_CUT_STYLE = "documentary"
FLOAT_KEYS = {"padding", "min_silence"}
BOOL_KEYS = {"punch_ins", "background_blur"}
EDITORS = ("resolve", "premiere", "fcpx", "other")
TEXT_KEYS = {"language", "whisper_model"}
KNOWN_KEYS = {"cut_style", "editor", *FLOAT_KEYS, *BOOL_KEYS, *TEXT_KEYS}


def preferences_path() -> Path:
    home = Path(os.environ.get("VIDEO_TIMELINE_COPILOT_HOME", Path.home() / ".video-timeline-copilot")).expanduser()
    return home / "preferences.json"


def load_preferences(path: Path | None = None) -> dict[str, Any]:
    target = path or preferences_path()
    if not target.exists():
        return {}
    data = read_json(target)
    return data if isinstance(data, dict) else {}


def parse_value(key: str, raw: str) -> Any:
    if key not in KNOWN_KEYS:
        raise ValueError(f"unknown preference {key!r}; expected one of {sorted(KNOWN_KEYS)}")
    if key == "cut_style":
        if raw not in CUT_STYLES:
            raise ValueError(f"cut_style must be one of {list(CUT_STYLES)}")
        return raw
    if key == "editor":
        if raw not in EDITORS:
            raise ValueError(f"editor must be one of {list(EDITORS)}")
        return raw
    if key in TEXT_KEYS:
        if not raw:
            raise ValueError(f"{key} must not be empty")
        return raw
    if key in BOOL_KEYS:
        lowered = raw.lower()
        if lowered not in {"true", "false"}:
            raise ValueError(f"{key} must be true or false")
        return lowered == "true"
    value = float(raw)
    if value < 0:
        raise ValueError(f"{key} must not be negative")
    return value


def update_preferences(
    *,
    set_values: list[str] | None = None,
    unset_keys: list[str] | None = None,
    add_notes: list[str] | None = None,
    forget_notes: list[int] | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    target = path or preferences_path()
    preferences = load_preferences(target)
    for item in set_values or []:
        key, separator, raw = item.partition("=")
        if not separator:
            raise ValueError(f"expected key=value, got {item!r}")
        key = key.strip()
        preferences[key] = parse_value(key, raw.strip())
    for key in unset_keys or []:
        preferences.pop(key.strip(), None)
    notes = [item for item in preferences.get("notes") or [] if isinstance(item, dict)]
    for index in sorted(set(forget_notes or []), reverse=True):
        if not 1 <= index <= len(notes):
            raise ValueError(f"no note number {index}; there are {len(notes)}")
        notes.pop(index - 1)
    for note in add_notes or []:
        text = note.strip()
        if text:
            notes.append({"date": date.today().isoformat(), "text": text})
    if notes or "notes" in preferences:
        preferences["notes"] = notes
    write_json(target, preferences)
    return preferences


def cut_style(preferences: dict[str, Any] | None = None) -> str:
    style = (preferences if preferences is not None else load_preferences()).get("cut_style")
    return style if style in CUT_STYLES else DEFAULT_CUT_STYLE


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show or change saved editing preferences (stored in VIDEO_TIMELINE_COPILOT_HOME/preferences.json)"
    )
    parser.add_argument("--set", dest="set_values", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--unset", dest="unset_keys", action="append", default=[], metavar="KEY")
    parser.add_argument("--add-note", dest="add_notes", action="append", default=[], metavar="TEXT",
                        help="Remember something about how this user likes to edit, across projects")
    parser.add_argument("--forget-note", dest="forget_notes", action="append", default=[], type=int, metavar="NUMBER",
                        help="Remove a saved note by its 1-based position")
    args = parser.parse_args()

    try:
        if args.set_values or args.unset_keys or args.add_notes or args.forget_notes:
            preferences = update_preferences(
                set_values=args.set_values,
                unset_keys=args.unset_keys,
                add_notes=args.add_notes,
                forget_notes=args.forget_notes,
            )
        else:
            preferences = load_preferences()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({"path": str(preferences_path()), "preferences": preferences}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
