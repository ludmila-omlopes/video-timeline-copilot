from __future__ import annotations

import sys


COMMANDS = {
    "inventory": ("helpers.inventory", "Index local video media"),
    "analyze-video": ("helpers.video_analysis", "Analyze visual video signals"),
    "transcribe": ("helpers.transcribe", "Transcribe one video with faster-whisper"),
    "pack-transcripts": ("helpers.pack_transcripts", "Pack transcript JSON files"),
    "draft-silence-cut": ("helpers.draft_silence_cut", "Create a draft EDL by removing detected silence"),
    "refine-audio-cuts": ("helpers.audio_refine", "Refine EDL cut boundaries using source audio"),
    "separate-audio": ("helpers.separate_audio", "Separate source audio into Demucs stems"),
    "validate-edl": ("helpers.validate_edl", "Validate an EDL JSON file"),
    "export-srt": ("helpers.export_srt", "Generate SRT subtitles from an EDL"),
    "export-fcpxml": ("helpers.export_fcpxml", "Export FCPXML from an EDL"),
    "update-fcpxml": ("helpers.update_fcpxml", "Update an existing FCPXML file in place"),
    "import-fcpxml": ("helpers.import_fcpxml", "Import an edited FCPXML back into an EDL"),
    "render-preview": ("helpers.render_preview", "Render an MP4 preview from an EDL"),
    "render-fcpxml-preview": ("helpers.render_fcpxml_preview", "Render an MP4 preview from an FCPXML file"),
    "qa-preview": ("helpers.qa_preview", "Run automated QA checks for a preview render"),
    "evaluate-edl": ("helpers.evaluate_edl", "Evaluate an EDL before final handoff"),
    "resolve-env-check": ("helpers.resolve_env_check", "Check DaVinci Resolve scripting access"),
    "build-resolve-project": ("helpers.build_resolve_project", "Build a DaVinci Resolve project"),
    "update-resolve-timeline": ("helpers.update_resolve_timeline", "Create or replace timelines in an existing Resolve project"),
}


def print_help() -> None:
    print("Usage: vtc <command> [args]\n")
    print("Commands:")
    width = max(len(name) for name in COMMANDS)
    for name, (_, description) in COMMANDS.items():
        print(f"  {name:<{width}}  {description}")
    print("\nRun 'vtc <command> --help' for command-specific options.")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        print_help()
        return

    command = sys.argv[1]
    target = COMMANDS.get(command)
    if target is None:
        print(f"unknown command: {command}", file=sys.stderr)
        print("run 'vtc --help' to see available commands", file=sys.stderr)
        raise SystemExit(2)

    module_name, _ = target
    module = __import__(module_name, fromlist=["main"])
    sys.argv = [f"vtc {command}", *sys.argv[2:]]
    module.main()


if __name__ == "__main__":
    main()
