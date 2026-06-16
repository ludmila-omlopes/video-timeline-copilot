from __future__ import annotations

from pathlib import Path

from helpers import installer


def test_package_spec_uses_tool_name_extra_repo_and_ref() -> None:
    assert installer.package_spec("https://example.test/repo.git", "v1.2.3", True) == (
        "video-timeline-copilot[transcribe] @ git+https://example.test/repo.git@v1.2.3"
    )


def test_skill_targets_include_claude_and_codex_locations(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(installer.Path, "home", lambda: tmp_path)

    assert installer.skill_targets("all") == [
        tmp_path / ".claude" / "skills" / "video-timeline-copilot",
        tmp_path / ".agents" / "skills" / "video-timeline-copilot",
        tmp_path / ".codex" / "skills" / "video-timeline-copilot",
    ]


def test_register_skills_copies_managed_skill_without_git_or_venv(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("---\nname: video-timeline-copilot\n---\n", encoding="utf-8")
    (source / ".git").mkdir()
    (source / ".venv").mkdir()
    (source / ".pytest_cache").mkdir()
    (source / "plans").mkdir()
    monkeypatch.setattr(installer.Path, "home", lambda: tmp_path / "home")

    installer.register_skills(source, "claude", copy=True, force=False)

    target = tmp_path / "home" / ".claude" / "skills" / "video-timeline-copilot"
    assert (target / "SKILL.md").exists()
    assert (target / installer.MANAGED_MARKER).exists()
    assert not (target / ".git").exists()
    assert not (target / ".venv").exists()
    assert not (target / ".pytest_cache").exists()
    assert not (target / "plans").exists()


def test_register_skills_leaves_unmanaged_existing_target_without_force(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("new", encoding="utf-8")
    target = tmp_path / "home" / ".claude" / "skills" / "video-timeline-copilot"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("existing", encoding="utf-8")
    monkeypatch.setattr(installer.Path, "home", lambda: tmp_path / "home")

    installer.register_skills(source, "claude", copy=True, force=False)

    assert (target / "SKILL.md").read_text(encoding="utf-8") == "existing"
