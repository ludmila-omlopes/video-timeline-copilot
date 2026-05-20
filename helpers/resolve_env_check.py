from __future__ import annotations

import importlib
import os
import sys


def main() -> None:
    print("DaVinci Resolve scripting environment")
    print(f"RESOLVE_SCRIPT_API={os.environ.get('RESOLVE_SCRIPT_API', '')}")
    print(f"RESOLVE_SCRIPT_LIB={os.environ.get('RESOLVE_SCRIPT_LIB', '')}")

    try:
        dvr = importlib.import_module("DaVinciResolveScript")
    except ImportError:
        print("status=offline")
        print("reason=DaVinciResolveScript could not be imported")
        raise SystemExit(1)

    resolve = dvr.scriptapp("Resolve")
    if not resolve:
        print("status=api_import_ok_resolve_not_connected")
        print("reason=Open DaVinci Resolve and run this check again")
        raise SystemExit(1)

    version = resolve.GetVersionString() if hasattr(resolve, "GetVersionString") else "unknown"
    print("status=ready")
    print(f"resolve_version={version}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error={exc}", file=sys.stderr)
        raise SystemExit(1)

