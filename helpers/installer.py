from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


TOOL_NAME = "video-timeline-copilot"
REPO_URL = "https://github.com/ludmila-omlopes/video-timeline-copilot.git"
DEFAULT_REF = "main"
MANAGED_MARKER = ".video-timeline-copilot-managed"


def default_home() -> Path:
    return Path(os.environ.get("VIDEO_TIMELINE_COPILOT_HOME", Path.home() / ".video-timeline-copilot")).expanduser()


def package_spec(repo: str, ref: str, transcribe: bool) -> str:
    extra = "[transcribe]" if transcribe else ""
    suffix = f"@{ref}" if ref else ""
    return f"{TOOL_NAME}{extra} @ git+{repo}{suffix}"


def run(args: list[str], *, check: bool = True, capture: bool = False, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        check=check,
        capture_output=capture,
        text=True,
        cwd=cwd,
    )


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def repo_dir(home: Path) -> Path:
    return home / "repo"


def sync_repo(home: Path, repo: str, ref: str) -> Path:
    if not command_exists("git"):
        raise RuntimeError("git is required to install agent skills from GitHub")

    home.mkdir(parents=True, exist_ok=True)
    destination = repo_dir(home)
    if not (destination / ".git").exists():
        print(f"Cloning skill source into {destination}")
        run(["git", "clone", repo, str(destination)])
    else:
        run(["git", "-C", str(destination), "remote", "set-url", "origin", repo])
        run(["git", "-C", str(destination), "fetch", "origin"])

    if ref:
        run(["git", "-C", str(destination), "checkout", ref])
        if ref == "main":
            run(["git", "-C", str(destination), "pull", "--ff-only", "origin", "main"])

    if not (destination / "SKILL.md").exists():
        raise RuntimeError(f"expected SKILL.md in {destination}")
    return destination


def skill_targets(agent: str) -> list[Path]:
    normalized = agent.lower()
    valid = {"all", "claude", "codex", "none"}
    if normalized not in valid:
        raise ValueError(f"unsupported --agent value: {agent}")
    if normalized == "none":
        return []

    targets: list[Path] = []
    if normalized in {"all", "claude"}:
        targets.append(Path.home() / ".claude" / "skills" / TOOL_NAME)
    if normalized in {"all", "codex"}:
        targets.append(Path.home() / ".agents" / "skills" / TOOL_NAME)
        targets.append(Path.home() / ".codex" / "skills" / TOOL_NAME)
    return targets


def is_managed_copy(path: Path) -> bool:
    return (path / MANAGED_MARKER).exists()


def is_managed_link(path: Path, source: Path) -> bool:
    try:
        return path.exists() and path.resolve() == source.resolve()
    except OSError:
        return False


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def copy_skill(source: Path, target: Path) -> None:
    remove_path(target)
    ignore = shutil.ignore_patterns(".git", ".venv", "__pycache__", "*.pyc", "edit", "test_video", "build", "dist", "*.egg-info")
    shutil.copytree(source, target, ignore=ignore)
    (target / MANAGED_MARKER).write_text(str(source), encoding="utf-8")


def link_skill(source: Path, target: Path) -> None:
    remove_path(target)
    target.symlink_to(source, target_is_directory=True)


def register_skills(source: Path, agent: str, *, copy: bool, force: bool) -> None:
    for target in skill_targets(agent):
        target.parent.mkdir(parents=True, exist_ok=True)
        managed = is_managed_link(target, source) or is_managed_copy(target)
        if target.exists() and not managed and not force:
            print(f"Skill target already exists, leaving unchanged: {target}")
            print("  Re-run with --force to replace it.")
            continue

        if copy:
            copy_skill(source, target)
            print(f"Copied skill -> {target}")
            continue

        try:
            link_skill(source, target)
            print(f"Linked skill -> {target}")
        except OSError as exc:
            print(f"Could not create link for {target}: {exc}")
            print("Falling back to copying skill files.")
            copy_skill(source, target)
            print(f"Copied skill -> {target}")


def check_ffmpeg(skip: bool) -> None:
    if skip:
        return
    ffmpeg = command_exists("ffmpeg")
    ffprobe = command_exists("ffprobe")
    print(f"{'OK' if ffmpeg else 'MISSING'} ffmpeg")
    print(f"{'OK' if ffprobe else 'MISSING'} ffprobe")
    if not ffmpeg or not ffprobe:
        print("Install FFmpeg and ensure ffmpeg/ffprobe are on PATH before running media workflows.")


def install(args: argparse.Namespace) -> None:
    source = sync_repo(args.home, args.repo, args.ref)
    register_skills(source, args.agent, copy=args.copy, force=args.force)
    check_ffmpeg(args.skip_ffmpeg_check)
    print("")
    print("video-timeline-copilot skill registration is ready.")
    print("Try: vtc --help")


def update(args: argparse.Namespace) -> None:
    if not command_exists("uv"):
        raise RuntimeError("uv is required to update the installed CLI")
    spec = package_spec(args.repo, args.ref, not args.no_transcribe)
    print(f"Updating CLI with uv: {spec}")
    run(["uv", "tool", "install", "--force", spec])
    install(args)


def doctor(args: argparse.Namespace) -> None:
    print(f"{'OK' if command_exists('uv') else 'MISSING'} uv")
    print(f"{'OK' if command_exists('git') else 'MISSING'} git")
    print(f"{'OK' if command_exists('vtc') else 'MISSING'} vtc CLI")
    check_ffmpeg(args.skip_ffmpeg_check)
    for target in skill_targets(args.agent):
        print(f"{'OK' if (target / 'SKILL.md').exists() else 'MISSING'} skill {target}")


def uninstall(args: argparse.Namespace) -> None:
    for target in skill_targets(args.agent):
        if target.exists():
            remove_path(target)
            print(f"Removed skill -> {target}")
    print("")
    print("Skill registrations removed.")
    print(f"To remove the CLI, run: uv tool uninstall {TOOL_NAME}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install video-timeline-copilot for Claude and Codex")
    subparsers = parser.add_subparsers(dest="command", required=False)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--agent", choices=["all", "claude", "codex", "none"], default="all")
        subparser.add_argument("--repo", default=REPO_URL)
        subparser.add_argument("--ref", default=DEFAULT_REF)
        subparser.add_argument("--home", type=Path, default=default_home())
        subparser.add_argument("--copy", action="store_true", help="Copy skill files instead of linking")
        subparser.add_argument("--force", action="store_true", help="Replace existing managed skill folders")
        subparser.add_argument("--skip-ffmpeg-check", action="store_true")

    install_parser = subparsers.add_parser("install", help="Register the agent skill")
    add_common(install_parser)

    update_parser = subparsers.add_parser("update", help="Reinstall the CLI with uv and refresh skill registrations")
    add_common(update_parser)
    update_parser.add_argument("--no-transcribe", action="store_true", help="Install without the transcribe extra")

    doctor_parser = subparsers.add_parser("doctor", help="Check local dependencies and skill registrations")
    doctor_parser.add_argument("--agent", choices=["all", "claude", "codex", "none"], default="all")
    doctor_parser.add_argument("--skip-ffmpeg-check", action="store_true")

    uninstall_parser = subparsers.add_parser("uninstall", help="Remove skill registrations")
    uninstall_parser.add_argument("--agent", choices=["all", "claude", "codex", "none"], default="all")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "install"
    try:
        if command == "install":
            install(args)
        elif command == "update":
            update(args)
        elif command == "doctor":
            doctor(args)
        elif command == "uninstall":
            uninstall(args)
        else:
            parser.error(f"unknown command: {command}")
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
