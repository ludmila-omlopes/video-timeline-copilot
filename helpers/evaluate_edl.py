from __future__ import annotations

import argparse
from pathlib import Path
import sys

from helpers.common import read_json, write_json
from helpers.export_fcpxml import default_fcpxml_path, fcpxml_integrity_issues
from helpers.qa_preview import default_report_path
from helpers.validate_edl import cut_quality_warnings, validate


DEFAULT_MAX_ATTEMPTS = 3


def default_evaluation_path(edl_path: Path) -> Path:
    return edl_path.parent / "qa" / "evaluation_report.json"


def _criterion(name: str, status: str, evidence: list[str] | None = None) -> dict:
    return {
        "name": name,
        "status": status,
        "evidence": evidence or [],
    }


def _qa_blockers(report: dict) -> list[str]:
    checks = report.get("checks") or {}
    blockers = []
    if not checks.get("preview_exists"):
        blockers.append("preview file was not found")
    if not checks.get("duration_matches_edl"):
        blockers.append("preview duration does not match the EDL duration")
    if checks.get("audio_only_regions_found"):
        blockers.append("audio-only regions were detected")
    if checks.get("video_only_regions_found"):
        blockers.append("video-only regions were detected")
    if checks.get("record_gaps_found"):
        blockers.append("record gaps were detected")
    if checks.get("record_overlaps_found"):
        blockers.append("record overlaps were detected")
    if checks.get("short_clips_found"):
        blockers.append("clips shorter than the minimum duration were detected")
    if checks.get("transform_coverage_ok") is False or checks.get("empty_space_risk_found"):
        blockers.append("transform zoom is too low for pan/tilt and may expose empty frame area")
    return blockers


def _qa_warnings(report: dict) -> list[str]:
    checks = report.get("checks") or {}
    warnings = []
    if report.get("preview") and not checks.get("contact_sheet_created"):
        warnings.append("contact sheet was not created; visual spot-check is limited")
    return warnings


def _is_blocking_cut_warning(warning: str) -> bool:
    blocking_fragments = (
        "cuts inside word",
        "keeps only part of",
        "keeps a long",
    )
    return any(fragment in warning for fragment in blocking_fragments)


def _revision_guidance(blockers: list[str], warnings: list[str]) -> list[str]:
    guidance = []
    if any(item.startswith("EDL validation failed") for item in blockers):
        guidance.append("Fix EDL structure, paths, source references, and invalid ranges before exporting again.")
    if any("cut-quality" in item for item in blockers) or any("cut-quality" in item for item in warnings):
        guidance.append("Move cuts to clean word, phrase, pause, or visual transition boundaries.")
    if any("duration" in item for item in blockers):
        guidance.append("Compare record_start values and source ranges against the rendered preview duration.")
    if any("FCPXML integrity" in item for item in blockers):
        guidance.append("Re-export FCPXML from the current EDL and verify visual layers and asset durations before handoff.")
    if any("audio-only" in item or "video-only" in item for item in blockers):
        guidance.append("Inspect source stream types and keep linked audio/video ranges unless the user explicitly asked otherwise.")
    if any("empty frame area" in item or "transform zoom" in item for item in blockers):
        guidance.append("Increase transform zoom or reduce pan/tilt so transformed clips fully cover the timeline frame.")
    if any("record gaps" in item or "record overlaps" in item for item in blockers):
        guidance.append("Make record_start values contiguous so the timeline has no black/silent gaps or overlaps.")
    if any("shorter than the minimum" in item for item in blockers):
        guidance.append("Remove, extend, or merge clips shorter than the minimum duration.")
    if not guidance and blockers:
        guidance.append("Revise the EDL, rerun exports, then run preview QA and evaluation again.")
    return guidance


def evaluate_edl(
    edl_path: Path,
    *,
    qa_report_path: Path | None = None,
    out_path: Path | None = None,
    attempt: int = 1,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    require_preview: bool = False,
    strict_cut_warnings: bool = False,
) -> dict:
    edl_path = edl_path.resolve()
    qa_report = (qa_report_path or default_report_path(edl_path)).resolve()
    output = (out_path or default_evaluation_path(edl_path)).resolve()
    attempt = max(1, attempt)
    max_attempts = max(1, max_attempts)

    blockers: list[str] = []
    warnings: list[str] = []
    criteria = []

    validation_errors = validate(edl_path)
    if validation_errors:
        blockers.extend(f"EDL validation failed: {error}" for error in validation_errors)
        criteria.append(_criterion("export_validity", "fail", validation_errors))
    else:
        criteria.append(_criterion("export_validity", "pass"))

    cut_warnings = [] if validation_errors else cut_quality_warnings(edl_path)
    blocking_cut_warnings = [
        warning for warning in cut_warnings if strict_cut_warnings or _is_blocking_cut_warning(warning)
    ]
    nonblocking_cut_warnings = [warning for warning in cut_warnings if warning not in blocking_cut_warnings]
    if blocking_cut_warnings:
        blockers.extend(f"cut-quality warning: {warning}" for warning in blocking_cut_warnings)
        criteria.append(_criterion("clip_boundaries", "fail", cut_warnings))
        warnings.extend(f"cut-quality warning: {warning}" for warning in nonblocking_cut_warnings)
    elif nonblocking_cut_warnings:
        warnings.extend(f"cut-quality warning: {warning}" for warning in nonblocking_cut_warnings)
        criteria.append(_criterion("clip_boundaries", "warn", nonblocking_cut_warnings))
    else:
        criteria.append(_criterion("clip_boundaries", "pass"))

    fcpxml_path = default_fcpxml_path(edl_path)
    if validation_errors:
        criteria.append(_criterion("fcpxml_integrity", "not_checked", ["EDL validation failed"]))
    elif fcpxml_path.exists():
        fcpxml_issues = fcpxml_integrity_issues(edl_path, fcpxml_path)
        if fcpxml_issues:
            blockers.extend(f"FCPXML integrity failed: {issue}" for issue in fcpxml_issues)
            criteria.append(_criterion("fcpxml_integrity", "fail", fcpxml_issues))
        else:
            criteria.append(_criterion("fcpxml_integrity", "pass"))
    else:
        warnings.append(f"FCPXML integrity was not checked because no FCPXML exists: {fcpxml_path}")
        criteria.append(_criterion("fcpxml_integrity", "not_checked", [f"missing FCPXML: {fcpxml_path}"]))

    qa_payload = None
    if qa_report.exists():
        qa_payload = read_json(qa_report)
        qa_failures = _qa_blockers(qa_payload)
        qa_notes = _qa_warnings(qa_payload)
        blockers.extend(f"preview QA failed: {item}" for item in qa_failures)
        warnings.extend(f"preview QA warning: {item}" for item in qa_notes)
        criteria.append(_criterion("technical_preview", "fail" if qa_failures else "pass", qa_failures))
        criteria.append(
            _criterion(
                "audio_continuity",
                "fail" if any("audio-only" in item or "video-only" in item for item in qa_failures) else "pass",
                qa_failures,
            )
        )
    elif require_preview:
        blockers.append(f"preview QA report is required but missing: {qa_report}")
        criteria.append(_criterion("technical_preview", "fail", [f"missing QA report: {qa_report}"]))
        criteria.append(_criterion("audio_continuity", "not_checked"))
    else:
        warnings.append(f"preview QA was not checked because no report exists: {qa_report}")
        criteria.append(_criterion("technical_preview", "not_checked", [f"missing QA report: {qa_report}"]))
        criteria.append(_criterion("audio_continuity", "not_checked"))

    criteria.extend(
        [
            _criterion("prompt_alignment", "agent_review_required"),
            _criterion("pacing", "agent_review_required"),
            _criterion("visual_coherence", "agent_review_required"),
        ]
    )

    status = "pass" if not blockers else "needs_revision"
    exhausted = bool(blockers) and attempt >= max_attempts
    if exhausted:
        status = "blocked"

    report = {
        "edl": str(edl_path),
        "qa_report": str(qa_report),
        "status": status,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "remaining_attempts": max(0, max_attempts - attempt),
        "max_attempts_reached": exhausted,
        "criteria": criteria,
        "blockers": blockers,
        "warnings": warnings,
        "revision_guidance": _revision_guidance(blockers, warnings),
        "agent_review_required": [
            "Confirm the edit matches the user's prompt and intended story.",
            "Confirm pacing, clip order, and repeated-take choices feel intentional.",
            "Review the preview/contact sheet when available for obvious visual framing or continuity problems.",
        ],
        "user_summary": (
            "Evaluation passed; final handoff can proceed after agent review."
            if status == "pass"
            else "Evaluation found issues to revise before final handoff."
            if status == "needs_revision"
            else "Evaluation still fails after the allowed attempts; stop and report the blockers to the user."
        ),
        "qa": qa_payload,
    }
    write_json(output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate an EDL before final handoff")
    parser.add_argument("edl", type=Path)
    parser.add_argument("--qa-report", type=Path, default=None, help="QA report path; defaults to edit/qa/preview_report.json")
    parser.add_argument("--out", type=Path, default=None, help="Output evaluation JSON path")
    parser.add_argument("--attempt", type=int, default=1, help="Current evaluation attempt number")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS, help="Maximum revision attempts")
    parser.add_argument("--require-preview", action="store_true", help="Fail when preview QA has not been run")
    parser.add_argument("--strict-cut-warnings", action="store_true", help="Treat cut-quality warnings as blockers")
    args = parser.parse_args()

    report = evaluate_edl(
        args.edl,
        qa_report_path=args.qa_report,
        out_path=args.out,
        attempt=args.attempt,
        max_attempts=args.max_attempts,
        require_preview=args.require_preview,
        strict_cut_warnings=args.strict_cut_warnings,
    )
    print(f"evaluation {report['status']} -> {args.out or default_evaluation_path(args.edl.resolve())}")
    if report["blockers"]:
        for blocker in report["blockers"]:
            print(f"BLOCKER: {blocker}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
