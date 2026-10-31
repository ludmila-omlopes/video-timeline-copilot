from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers.cli import COMMANDS
from helpers.punch_ins import (
    apply_punch_ins,
    focus_transform,
    lua_command,
    plan_punch_ins,
)
from helpers.transforms import resolve_transform


def ranges(*spans: tuple[float, float], source: str = "A001") -> list[dict]:
    record = 0.0
    items = []
    for start, end in spans:
        items.append({"source": source, "source_start": start, "source_end": end, "record_start": record})
        record += end - start
    return items


def test_punch_ins_command_is_registered() -> None:
    assert COMMANDS["punch-ins"][0] == "helpers.punch_ins"


def test_levels_alternate_at_every_cut() -> None:
    items = ranges((0, 3), (5, 8), (10, 13), (15, 18))
    assert plan_punch_ins(items, texts=["a"] * 4) == [1.0, 1.12, 1.0, 1.12]


def test_short_question_gets_closer_punch_in_without_repeating() -> None:
    items = ranges((0, 3), (5, 8), (10, 13), (15, 18))
    texts = ["frase", "qual cor você acha?", "isso é incrível!", "frase"]

    plan = plan_punch_ins(items, texts=texts)

    assert plan[1] == 1.25
    assert plan[2] != plan[1]
    assert all(left != right for left, right in zip(plan, plan[1:]))


def test_continuous_ranges_keep_their_zoom() -> None:
    items = ranges((0, 3), (3.0, 6), (8, 10))
    assert plan_punch_ins(items, texts=["a", "b", "c"]) == [1.0, 1.0, 1.12]


def test_explicit_emphasis_flag_wins() -> None:
    items = ranges((0, 3), (5, 8))
    items[1]["emphasis"] = True
    assert plan_punch_ins(items, texts=["a", "sem pergunta"]) == [1.0, 1.25]


def test_focus_transform_keeps_the_eyes_in_place() -> None:
    transform = focus_transform(1.25, (0.55, 0.33), 3840, 2160)

    assert transform == {"zoom": 1.25, "pan": -48.0, "tilt": -91.8}
    resolved = resolve_transform(transform, 3840, 2160)
    assert resolved.zoom == pytest.approx(1.25)
    assert not resolved.zoom_was_adjusted


def write_edl(tmp_path: Path, *, resolution: list[int]) -> Path:
    (tmp_path / "raw").mkdir()
    (tmp_path / "edit" / "transcripts").mkdir(parents=True)
    (tmp_path / "raw" / "take.mp4").write_bytes(b"")
    (tmp_path / "edit" / "transcripts" / "take.json").write_text(
        json.dumps({"words": [{"start": 5.2, "end": 5.6, "text": "sério?"}]}), encoding="utf-8"
    )
    items = ranges((0, 3), (5, 8), (10, 13))
    items[2]["transform"] = {"zoom": 1.5}
    edl = {
        "version": 1,
        "project_name": "Talking head",
        "fps": 30,
        "timelines": [
            {"name": "Main", "resolution": resolution, "sources": {"A001": "raw/take.mp4"}, "ranges": items}
        ],
    }
    path = tmp_path / "edit" / "edl.json"
    path.write_text(json.dumps(edl), encoding="utf-8")
    return path


def test_apply_writes_transforms_and_keeps_existing_ones(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path, resolution=[1920, 1080])
    lua_path = tmp_path / "edit" / "punch_ins.lua"

    result = apply_punch_ins(edl_path, lua_path=lua_path)

    items = json.loads(edl_path.read_text(encoding="utf-8"))["timelines"][0]["ranges"]
    assert items[0]["transform"]["zoom"] == 1.0
    assert items[1]["transform"]["zoom"] == 1.25
    assert items[2]["transform"] == {"zoom": 1.5}
    assert result["timelines"][0]["changed"] == 2
    lua = lua_path.read_text(encoding="utf-8")
    assert lua.startswith("Z={{1.0,")
    assert "SetProperty('Tilt'" in lua


def test_vertical_timelines_are_skipped_by_default(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path, resolution=[1080, 1920])

    result = apply_punch_ins(edl_path)

    assert "skipped" in result["timelines"][0]
    items = json.loads(edl_path.read_text(encoding="utf-8"))["timelines"][0]["ranges"]
    assert "transform" not in items[0]


def test_lua_command_checks_clip_count() -> None:
    command = lua_command([{"zoom": 1.0, "pan": 0.0, "tilt": 0.0}])
    assert "clip count differs" in command
