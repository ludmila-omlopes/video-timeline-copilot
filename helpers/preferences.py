from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from helpers.common import read_json, write_json


CUT_STYLES = ("tight", "social", "highlight", "documentary", "longform")
DEFAULT_CUT_STYLE = "documentary"
FLOAT_KEYS = {"padding", "min_silence"}
KNOWN_KEYS = {"cut_style", *FLOAT_KEYS}


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
    value = float(raw)
    if value < 0:
        raise ValueError(f"{key} must not be negative")
    return value


def update_preferences(
    *,
    set_values: list[str] | None = None,
    unset_keys: list[str] | None = None,
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
    args = parser.parse_args()

    try:
        if args.set_values or args.unset_keys:
            preferences = update_preferences(set_values=args.set_values, unset_keys=args.unset_keys)
        else:
            preferences = load_preferences()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({"path": str(preferences_path()), "preferences": preferences}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
