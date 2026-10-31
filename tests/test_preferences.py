from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers.cli import COMMANDS
from helpers.draft_silence_cut import STYLE_DEFAULTS, first_number
from helpers.preferences import (
    CUT_STYLES,
    DEFAULT_CUT_STYLE,
    cut_style,
    load_preferences,
    preferences_path,
    update_preferences,
)


def test_preferences_command_is_registered() -> None:
    assert COMMANDS["preferences"][0] == "helpers.preferences"


def test_cut_styles_match_draft_silence_cut_presets() -> None:
    assert set(CUT_STYLES) == set(STYLE_DEFAULTS)


def test_tight_style_keeps_less_air_than_social() -> None:
    assert STYLE_DEFAULTS["tight"]["padding"] < STYLE_DEFAULTS["social"]["padding"]
    assert STYLE_DEFAULTS["tight"]["min_silence"] < STYLE_DEFAULTS["social"]["min_silence"]


def test_preferences_live_under_the_tool_home(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEO_TIMELINE_COPILOT_HOME", str(tmp_path))
    assert preferences_path() == tmp_path / "preferences.json"
    assert load_preferences() == {}
    assert cut_style() == DEFAULT_CUT_STYLE


def test_set_and_unset_preferences(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEO_TIMELINE_COPILOT_HOME", str(tmp_path))

    saved = update_preferences(set_values=["cut_style=tight", "padding=0.04"])

    assert saved == {"cut_style": "tight", "padding": 0.04}
    assert json.loads((tmp_path / "preferences.json").read_text(encoding="utf-8")) == saved
    assert cut_style() == "tight"

    assert update_preferences(unset_keys=["padding"]) == {"cut_style": "tight"}
    assert update_preferences(set_values=["punch_ins=false"])["punch_ins"] is False
    assert update_preferences(set_values=["background_blur=true"])["background_blur"] is True


@pytest.mark.parametrize(
    "item",
    ["cut_style=fast", "unknown=1", "padding=-0.1", "padding", "punch_ins=maybe"],
)
def test_invalid_preferences_are_rejected(tmp_path: Path, monkeypatch, item: str) -> None:
    monkeypatch.setenv("VIDEO_TIMELINE_COPILOT_HOME", str(tmp_path))
    with pytest.raises(ValueError):
        update_preferences(set_values=[item])


def test_unknown_saved_style_falls_back_to_default() -> None:
    assert cut_style({"cut_style": "fast"}) == DEFAULT_CUT_STYLE


def test_first_number_prefers_explicit_then_saved_then_preset() -> None:
    assert first_number(None, 0.04, 0.12) == 0.04
    assert first_number(0.2, 0.04, 0.12) == 0.2
    assert first_number(None, None, 0.12) == 0.12
