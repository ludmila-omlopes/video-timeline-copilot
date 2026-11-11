from __future__ import annotations

import argparse
from pathlib import Path


GUIDES_DIR = Path(__file__).resolve().parent / "guides"


def guide_topics() -> dict[str, Path]:
    return {path.stem: path for path in sorted(GUIDES_DIR.glob("*.md"))}


def guide_summary(path: Path) -> str:
    """The first paragraph line under the title, used as the one-line description."""
    collected: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if not stripped:
            if collected:
                break
            continue
        collected.append(stripped)
    summary = " ".join(collected)
    return summary if len(summary) <= 200 else summary[:197].rstrip() + "..."


def read_guide(topic: str) -> str:
    topics = guide_topics()
    key = topic.strip().lower().removesuffix(".md")
    if key not in topics:
        raise KeyError(f"unknown guide {topic!r}; available: {', '.join(topics)}")
    return topics[key].read_text(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print the agent guide for one part of the workflow. The guides ship with the CLI, so they always match it."
    )
    parser.add_argument("topic", nargs="?", default=None, help="Guide name; omit to list the guides")
    args = parser.parse_args()

    if args.topic is None:
        topics = guide_topics()
        width = max((len(name) for name in topics), default=0)
        for name, path in topics.items():
            print(f"{name:<{width}}  {guide_summary(path)}")
        return
    try:
        print(read_guide(args.topic))
    except KeyError as exc:
        raise SystemExit(str(exc.args[0])) from exc


if __name__ == "__main__":
    main()
