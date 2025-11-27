#!/usr/bin/env python3
"""
Initialize Django and verify that `sefaria.export` can be imported.

Uses GITHUB_WORKSPACE to locate Sefaria-Project if available.
"""
import os
import sys


def main() -> int:
    try:
        import django  # noqa: F401
    except Exception as e:  # pragma: no cover
        print(f"❌ Django not available: {e}")
        return 1

    workspace = os.environ.get("GITHUB_WORKSPACE", os.getcwd())
    proj_dir = os.path.join(workspace, "Sefaria-Project")
    sys.path.insert(0, os.path.abspath(proj_dir))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sefaria.settings")

    try:
        import django
        django.setup()
        from sefaria import export  # noqa: F401
    except Exception as e:
        print(f"❌ Failed to load export module: {e}")
        return 1

    # If we reach here, success
    from sefaria import export
    print("✅ Export module loaded")
    print("📋 Available functions:", dir(export))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
