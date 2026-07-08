from __future__ import annotations

import json
from pathlib import Path

from helpers.cli import COMMANDS
from helpers.evaluate_edl import default_evaluation_path, evaluate_edl
from helpers.export_fcpxml import default_fcpxml_path
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


def write_qa_report(
    edl_path: Path,
    *,
    duration_matches: bool = True,
    transform_coverage_ok: bool = True,
) -> Path:
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
            "transform_coverage_ok": transform_coverage_ok,
            "empty_space_risk_found": not transform_coverage_ok,
            "contact_sheet_created": True,
        },
        "audio_only_regions": [],
        "video_only_regions": [],
        "transform_coverage_issues": [] if transform_coverage_ok else [{"range_index": 0}],
        "gaps": [],
        "cut_count": 1,
        "source_count": 1,
    }
    path = default_report_path(edl_path)
    path.parent.mkdir()
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def write_minimal_fcpxml(
    edl_path: Path,
    *,
    asset_duration: str = "10s",
    primary_src_enable: str = "all",
    layer_count: int = 0,
) -> Path:
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    source = (edl_path.parent.parent / edl["timelines"][0]["sources"]["A001"]).resolve().as_uri()
    layers = "\n".join(
        f'                <asset-clip name="Layer {index + 1}" ref="a1" lane="{index + 1}" '
        'offset="0s" start="0s" duration="2s" format="r1" srcEnable="video" />'
        for index in range(layer_count)
    )
    path = default_fcpxml_path(edl_path, edl)
    path.write_text(
        f"""<?xml version="1.0" encoding="utf-8"?>
<fcpxml version="1.13">
  <resources>
    <format id="r1" name="FFVideoFormat1920x1080" frameDuration="1/30s" width="1920" height="1080" />
    <asset id="a1" name="clip" start="0s" duration="{asset_duration}" hasVideo="1" hasAudio="1" format="r1">
      <media-rep kind="original-media" src="{source}" />
    </asset>
  </resources>
  <library>
    <event name="{edl["project_name"]}">
      <project name="{edl["timelines"][0]["name"]}">
        <sequence format="r1" duration="2s" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">
          <spine>
            <asset-clip name="Clip" ref="a1" offset="0s" start="0s" duration="2s" format="r1" srcEnable="{primary_src_enable}">
{layers}
            </asset-clip>
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
""",
        encoding="utf-8",
    )
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


def test_evaluate_edl_flags_stale_fcpxml_asset_duration(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path)
    write_minimal_fcpxml(edl_path, asset_duration="1s")
    qa_path = write_qa_report(edl_path)

    report = evaluate_edl(edl_path, qa_report_path=qa_path, require_preview=True)

    assert report["status"] == "needs_revision"
    assert any("declares 1.000s" in item for item in report["blockers"])


def test_evaluate_edl_flags_missing_fcpxml_visual_layers(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path)
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    edl["timelines"][0]["ranges"][0]["visual_layers"] = [
        {
            "name": "Facecam",
            "source_rect": {"x": 0, "y": 0, "width": 0.25, "height": 0.25},
            "dest_rect": {"x": 0, "y": 0, "width": 1, "height": 0.4},
        },
        {
            "name": "Gameplay",
            "source_rect": {"x": 0, "y": 0.2, "width": 1, "height": 0.8},
            "dest_rect": {"x": 0, "y": 0.45, "width": 1, "height": 0.55},
        },
    ]
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    write_minimal_fcpxml(edl_path, asset_duration="10s", primary_src_enable="all", layer_count=0)
    qa_path = write_qa_report(edl_path)

    report = evaluate_edl(edl_path, qa_report_path=qa_path, require_preview=True)

    assert report["status"] == "needs_revision"
    assert any("expected 1 connected visual layer clips" in item for item in report["blockers"])


def test_evaluate_edl_flags_transform_coverage_failure(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path)
    qa_path = write_qa_report(edl_path, transform_coverage_ok=False)

    report = evaluate_edl(edl_path, qa_report_path=qa_path, require_preview=True)

    assert report["status"] == "needs_revision"
    assert any("empty frame area" in item for item in report["blockers"])


def test_evaluate_edl_blocks_record_gap(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path)
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    edl["timelines"][0]["ranges"].append(
        {"source": "A001", "source_start": 3.0, "source_end": 4.0, "record_start": 3.0}
    )
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    qa_path = write_qa_report(edl_path)

    report = evaluate_edl(edl_path, qa_report_path=qa_path, require_preview=True)

    assert report["status"] == "needs_revision"
    assert any("record gap" in item for item in report["blockers"])


def test_evaluate_edl_blocks_half_second_clip(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path)
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    edl["timelines"][0]["ranges"][0]["source_end"] = 0.5
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    qa_path = write_qa_report(edl_path)

    report = evaluate_edl(edl_path, qa_report_path=qa_path, require_preview=True)

    assert report["status"] == "needs_revision"
    assert any("shorter than the minimum" in item for item in report["blockers"])


def test_evaluate_edl_blocks_long_transcript_gap(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path)
    transcript_dir = edl_path.parent / "transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "clip.json").write_text(
        json.dumps(
            {
                "words": [
                    {"start": 0.5, "end": 1.0, "text": "before"},
                    {"start": 1.9, "end": 2.0, "text": "after"},
                ]
            }
        ),
        encoding="utf-8",
    )
    qa_path = write_qa_report(edl_path)

    report = evaluate_edl(edl_path, qa_report_path=qa_path, require_preview=True)

    assert report["status"] == "needs_revision"
    assert any("transcript gap" in item for item in report["blockers"])


def test_evaluate_edl_blocks_partial_sentence_by_default(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path)
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    edl["timelines"][0]["ranges"][0]["source_start"] = 0.6
    edl["timelines"][0]["ranges"][0]["source_end"] = 1.5
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    transcript_dir = edl_path.parent / "transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "clip.json").write_text(
        json.dumps(
            {
                "words": [
                    {"start": 0.0, "end": 0.2, "text": "Please"},
                    {"start": 0.3, "end": 0.5, "text": "do"},
                    {"start": 0.6, "end": 0.8, "text": "not"},
                    {"start": 0.9, "end": 1.2, "text": "cut"},
                    {"start": 1.3, "end": 1.5, "text": "phrases."},
                ]
            }
        ),
        encoding="utf-8",
    )
    qa_path = write_qa_report(edl_path)

    report = evaluate_edl(edl_path, qa_report_path=qa_path, require_preview=True)

    assert report["status"] == "needs_revision"
    assert any("keeps only part of sentence" in item for item in report["blockers"])


def test_evaluate_edl_blocks_cuts_inside_words_by_default(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path)
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    edl["timelines"][0]["ranges"][0]["source_start"] = 0.5
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    transcript_dir = edl_path.parent / "transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "clip.json").write_text(
        json.dumps({"words": [{"start": 0.0, "end": 1.0, "text": "hello"}]}),
        encoding="utf-8",
    )
    qa_path = write_qa_report(edl_path)

    report = evaluate_edl(edl_path, qa_report_path=qa_path, require_preview=True)

    assert report["status"] == "needs_revision"
    assert any("cuts inside word" in item for item in report["blockers"])
