from __future__ import annotations

import json
from pathlib import Path

from helpers.cli import COMMANDS
from helpers.evaluate_edl import default_evaluation_path, evaluate_edl
from helpers.qa_preview import default_report_path


def write_edl(tmp_path: Path, *, source_exists: bool = True) -> Path:
    raw_dir = tmp_path / "raw"
    edit_dir = tmp_path / "edit"
    raw_dir.mkdir()
    edit_dir.mkdir()
    if source_exists:
        (raw_dir / "clip.mp4").write_bytes(b"")
    edl = {
        "version": 1,
        "project_name": "Evaluation Test",
        "fps": 30,
        "timelines": [
            {
                "name": "Main",
                "resolution": [1920, 1080],
                "sources": {"A001": "raw/clip.mp4"},
                "ranges": [
                    {
                        "source": "A001",
                        "source_start": 0.0,
                        "source_end": 2.0,
                        "record_start": 0.0,
                    }
                ],
            }
        ],
    }
    edl_path = edit_dir / "edl.json"
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    return edl_path


def write_qa_report(edl_path: Path, *, duration_matches: bool = True) -> Path:
    report = {
        "edl": str(edl_path),
        "timeline": "Main",
        "preview": str(edl_path.parent / "previews" / "Evaluation_Test_preview.mp4"),
        "contact_sheet": str(edl_path.parent / "qa" / "contact_sheet.jpg"),
        "expected_duration": 2.0,
        "actual_duration": 2.0 if duration_matches else 3.0,
        "duration_delta": 0.0 if duration_matches else 1.0,
        "checks": {
            "preview_exists": True,
            "duration_matches_edl": duration_matches,
            "audio_only_regions_found": False,
            "video_only_regions_found": False,
            "record_gaps_found": False,
            "contact_sheet_created": True,
        },
        "audio_only_regions": [],
        "video_only_regions": [],
        "gaps": [],
        "cut_count": 1,
        "source_count": 1,
    }
    path = default_report_path(edl_path)
    path.parent.mkdir()
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def test_evaluate_command_is_registered() -> None:
    assert COMMANDS["evaluate-edl"] == ("helpers.evaluate_edl", "Evaluate an EDL before final handoff")


def test_evaluate_edl_passes_with_clean_validation_and_preview_qa(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path)
    qa_path = write_qa_report(edl_path)

    report = evaluate_edl(edl_path, qa_report_path=qa_path, require_preview=True)

    assert report["status"] == "pass"
    assert report["blockers"] == []
    assert report["remaining_attempts"] == 2
    assert default_evaluation_path(edl_path).exists()


def test_evaluate_edl_requires_preview_when_requested(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path)

    report = evaluate_edl(edl_path, require_preview=True)

    assert report["status"] == "needs_revision"
    assert any("preview QA report is required" in item for item in report["blockers"])


def test_evaluate_edl_blocks_after_max_attempts(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path, source_exists=False)

    report = evaluate_edl(edl_path, attempt=3, max_attempts=3)

    assert report["status"] == "blocked"
    assert report["max_attempts_reached"] is True
    assert any("does not exist" in item for item in report["blockers"])


def test_evaluate_edl_flags_preview_qa_failures(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path)
    qa_path = write_qa_report(edl_path, duration_matches=False)

    report = evaluate_edl(edl_path, qa_report_path=qa_path, require_preview=True)

    assert report["status"] == "needs_revision"
    assert any("duration does not match" in item for item in report["blockers"])
