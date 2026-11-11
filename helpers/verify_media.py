from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from helpers.common import read_json, resolve_relative, write_json
from helpers.inventory import file_fingerprint


MTIME_TOLERANCE_SECONDS = 2.0


def check_item(item: dict) -> dict:
    path = Path(item["path"])
    record = {"path": str(path), "name": path.name, "status": "ok"}
    if not path.exists():
        record["status"] = "missing"
        return record
    current = file_fingerprint(path)
    known_size = item.get("size")
    known_mtime = item.get("mtime")
    if known_size is None and known_mtime is None:
        record["status"] = "unverified"
        return record
    size_changed = known_size is not None and current.get("size") != known_size
    mtime_changed = known_mtime is not None and abs(float(current.get("mtime", 0.0)) - float(known_mtime)) > MTIME_TOLERANCE_SECONDS
    if size_changed or (mtime_changed and known_size is None):
        record["status"] = "changed"
        record["indexed_size"] = known_size
        record["current_size"] = current.get("size")
    return record


def find_candidates(name: str, size: int | None, search_root: Path, edit_dir: Path) -> list[Path]:
    """Files with the same name (and size, when known) elsewhere under the search root."""
    matches = []
    if not search_root.exists():
        return matches
    edit_dir = edit_dir.resolve()
    for folder, directories, files in os.walk(search_root):
        directories[:] = [item for item in directories if not item.startswith(".")]
        current = Path(folder).resolve()
        if current == edit_dir or edit_dir in current.parents:
            directories[:] = []
            continue
        if name in files:
            candidate = current / name
            if size is None or candidate.stat().st_size == size:
                matches.append(candidate)
    return sorted(matches)


def edl_source_issues(edl_path: Path) -> list[dict]:
    edl = read_json(edl_path)
    root = edl_path.parent.parent
    issues = []
    for timeline_index, timeline in enumerate(edl.get("timelines") or []):
        for source_id, source_path in (timeline.get("sources") or {}).items():
            resolved = resolve_relative(source_path, root)
            if not resolved.exists():
                issues.append(
                    {"timeline": timeline.get("name") or timeline_index, "source": source_id, "path": str(resolved), "status": "missing"}
                )
    return issues


def verify(edit_dir: Path, *, search_root: Path | None = None, edl_path: Path | None = None) -> dict:
    index_path = edit_dir / "media_index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"media index not found: {index_path}; run `vtc inventory` first")
    index = read_json(index_path)
    root = Path(search_root or index.get("root") or edit_dir.parent)
    records = []
    for item in [*(index.get("media") or []), *(index.get("images") or [])]:
        if not item.get("path"):
            continue
        record = check_item(item)
        if record["status"] == "missing":
            candidates = find_candidates(Path(item["path"]).name, item.get("size"), root, edit_dir)
            record["candidates"] = [str(candidate) for candidate in candidates]
        records.append(record)

    edl_issues = edl_source_issues(edl_path) if edl_path else []
    missing = [record for record in records if record["status"] == "missing"]
    changed = [record for record in records if record["status"] == "changed"]
    return {
        "edit_dir": str(edit_dir),
        "search_root": str(root),
        "ok": not missing and not changed and not edl_issues,
        "counts": {
            "ok": sum(record["status"] in {"ok", "unverified"} for record in records),
            "missing": len(missing),
            "changed": len(changed),
        },
        "media": records,
        "suggested_relinks": [
            {"from": record["path"], "to": record["candidates"][0]}
            for record in missing
            if len(record.get("candidates") or []) == 1
        ],
        "edl_issues": edl_issues,
    }


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def apply_relinks(edit_dir: Path, relinks: list[dict], edl_paths: list[Path]) -> int:
    """Point the media index (and EDL sources) at the files' new locations."""
    mapping = {os.path.normcase(str(Path(item["from"]).resolve())): Path(item["to"]) for item in relinks}
    if not mapping:
        return 0
    index_path = edit_dir / "media_index.json"
    index = read_json(index_path)
    updated = 0
    for item in [*(index.get("media") or []), *(index.get("images") or [])]:
        key = os.path.normcase(str(Path(item.get("path", "")).resolve()))
        if key in mapping:
            item["path"] = str(mapping[key])
            item.update(file_fingerprint(mapping[key]))
            updated += 1
    write_json(index_path, index)

    for edl_path in edl_paths:
        edl = read_json(edl_path)
        root = edl_path.parent.parent
        touched = False
        for timeline in edl.get("timelines") or []:
            for source_id, source_path in list((timeline.get("sources") or {}).items()):
                key = os.path.normcase(str(resolve_relative(source_path, root).resolve()))
                if key in mapping:
                    timeline["sources"][source_id] = _relative_or_absolute(mapping[key], root)
                    touched = True
        if touched:
            write_json(edl_path, edl)
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check that every indexed source still exists and has not changed since it was analyzed"
    )
    parser.add_argument("--edit-dir", type=Path, required=True)
    parser.add_argument("--edl", type=Path, default=None, help="Also check the sources this EDL references")
    parser.add_argument("--search-root", type=Path, default=None, help="Where to look for moved files; defaults to the footage root")
    parser.add_argument(
        "--relink",
        action="store_true",
        help="Apply the suggested relinks. Only after the user confirmed the new locations.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    edit_dir = args.edit_dir.resolve()
    edl_path = args.edl.resolve() if args.edl else None
    try:
        report = verify(edit_dir, search_root=args.search_root, edl_path=edl_path)
        if args.relink and report["suggested_relinks"]:
            count = apply_relinks(edit_dir, report["suggested_relinks"], [edl_path] if edl_path else [])
            print(f"relinked {count} source(s)")
            report = verify(edit_dir, search_root=args.search_root, edl_path=edl_path)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    out = edit_dir / "qa" / "media_report.json"
    write_json(out, report)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for record in report["media"]:
            line = f" {record['status']:<10} {record['name']}"
            if record["status"] == "missing" and record.get("candidates"):
                line += "  found at: " + "; ".join(record["candidates"])
            if record["status"] == "changed":
                line += "  the file changed after it was indexed; its transcript and analysis may be stale"
            print(line)
        for issue in report["edl_issues"]:
            print(f" missing    EDL source {issue['source']} -> {issue['path']}")
        counts = report["counts"]
        print(f"media check: {counts['ok']} ok, {counts['missing']} missing, {counts['changed']} changed -> {out}")
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
