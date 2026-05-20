from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from helpers.export_fcpxml import default_fcpxml_path, write_fcpxml
from helpers.common import read_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Update an existing FCPXML file in place from an EDL")
    parser.add_argument("edl", type=Path)
    parser.add_argument(
        "--xml",
        type=Path,
        default=None,
        help="Existing .fcpxml file to update. Defaults to the standard project_name-based path.",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Copy the previous XML to <name>.bak.fcpxml before updating it.",
    )
    args = parser.parse_args()

    edl_path = args.edl.resolve()
    edl = read_json(edl_path)
    xml_path = (args.xml or default_fcpxml_path(edl_path, edl)).resolve()

    if not xml_path.exists():
        raise SystemExit(f"ERROR: FCPXML does not exist yet: {xml_path}")

    backup_path = None
    if args.backup:
        backup_path = xml_path.with_name(f"{xml_path.stem}.bak{xml_path.suffix}")
        shutil.copy2(xml_path, backup_path)

    write_fcpxml(edl_path, xml_path)
    if backup_path:
        print(f"FCPXML backup -> {backup_path}")
    print(f"FCPXML updated -> {xml_path}")
