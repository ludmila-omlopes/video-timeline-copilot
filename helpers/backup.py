from __future__ import annotations

import argparse
import os
import zipfile
from datetime import datetime
from pathlib import Path

from helpers.common import safe_filename


# Large files the helpers can rebuild from the sources; left out unless asked for.
REBUILDABLE_DIRS = ("previews", "video_frames", "audio", "contact_sheets")
BACKUP_SUFFIX = ".zip"


def default_backups_dir(edit_dir: Path) -> Path:
    home = Path(os.environ.get("VIDEO_TIMELINE_COPILOT_HOME", Path.home() / ".video-timeline-copilot")).expanduser()
    project = safe_filename(edit_dir.parent.name, "project")
    return home / "backups" / project


def iter_backup_files(edit_dir: Path, *, include_rebuildable: bool) -> list[Path]:
    files = []
    for path in sorted(edit_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(edit_dir)
        if not include_rebuildable and relative.parts and relative.parts[0] in REBUILDABLE_DIRS:
            continue
        files.append(path)
    return files


def create_backup(
    edit_dir: Path,
    backups_dir: Path | None = None,
    *,
    label: str | None = None,
    include_rebuildable: bool = False,
    now: datetime | None = None,
) -> Path:
    if not edit_dir.is_dir():
        raise FileNotFoundError(f"edit folder not found: {edit_dir}")
    destination = backups_dir or default_backups_dir(edit_dir)
    destination.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    suffix = f"_{safe_filename(label)}" if label else ""
    out = destination / f"{safe_filename(edit_dir.parent.name, 'project')}_{stamp}{suffix}{BACKUP_SUFFIX}"
    files = iter_backup_files(edit_dir, include_rebuildable=include_rebuildable)
    if not files:
        raise FileNotFoundError(f"nothing to back up in {edit_dir}")
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=(Path("edit") / path.relative_to(edit_dir)).as_posix())
    return out


def list_backups(edit_dir: Path, backups_dir: Path | None = None) -> list[Path]:
    destination = backups_dir or default_backups_dir(edit_dir)
    if not destination.exists():
        return []
    return sorted(destination.glob(f"*{BACKUP_SUFFIX}"), reverse=True)


def restore_backup(archive_path: Path, edit_dir: Path, *, now: datetime | None = None) -> Path:
    """Extract a backup next to the edit folder. The current edit folder is never overwritten."""
    if not archive_path.exists():
        raise FileNotFoundError(f"backup not found: {archive_path}")
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    target = edit_dir.parent / f"{edit_dir.name}.restored_{stamp}"
    target.mkdir(parents=True, exist_ok=False)
    resolved_target = target.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            parts = Path(member.filename).parts
            relative = Path(*parts[1:]) if parts and parts[0] == "edit" else Path(member.filename)
            destination = (target / relative).resolve()
            if resolved_target != destination and resolved_target not in destination.parents:
                raise ValueError(f"backup entry escapes the restore folder: {member.filename}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(member))
    return target


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Back up the edit folder (transcripts, summaries, plans, EDLs, exports), list backups, or restore one"
    )
    parser.add_argument("--edit-dir", type=Path, required=True)
    parser.add_argument("--backups-dir", type=Path, default=None, help="Defaults to VIDEO_TIMELINE_COPILOT_HOME/backups/<project>")
    parser.add_argument("--label", default=None, help="Short name added to the backup file, e.g. the cut it preserves")
    parser.add_argument("--include-rebuildable", action="store_true", help="Also store previews, frames, stems, and contact sheets")
    parser.add_argument("--list", action="store_true", help="List existing backups, newest first")
    parser.add_argument("--restore", type=Path, default=None, metavar="BACKUP", help="Extract a backup into a new folder beside edit/")
    args = parser.parse_args()

    edit_dir = args.edit_dir.resolve()
    backups_dir = args.backups_dir.resolve() if args.backups_dir else None
    try:
        if args.list:
            backups = list_backups(edit_dir, backups_dir)
            for backup in backups:
                print(backup)
            if not backups:
                print("no backups yet")
            return
        if args.restore is not None:
            target = restore_backup(args.restore.resolve(), edit_dir)
            print(f"restored -> {target}")
            print("the current edit folder was left untouched; copy back what you need")
            return
        out = create_backup(edit_dir, backups_dir, label=args.label, include_rebuildable=args.include_rebuildable)
        print(f"backup -> {out}")
    except (FileNotFoundError, FileExistsError, ValueError, zipfile.BadZipFile) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
