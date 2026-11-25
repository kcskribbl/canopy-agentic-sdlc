"""Import one operator-registered, hash-pinned change; never import a caller-selected directory."""
from pathlib import Path
import re

from sdlc_store import sha


def load(root, registration, base, size_limit):
    if registration.get("baseline") != sha(base):
        raise ValueError("Reviewed patch baseline mismatch; request a new plan")
    rel = registration["directory"]
    directory = (root / rel).resolve()
    if not directory.is_relative_to(root / "scenarios") or not directory.is_dir():
        raise ValueError("Patch must be registered under scenarios")
    expected = registration["files"]
    changes = {}
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        key = path.relative_to(directory).as_posix()
        if (key not in expected or not re.fullmatch(r"(?:pom\.xml|src/(?:main|test)/[A-Za-z0-9._/-]+)",key)
                or path != path.resolve() or path.stat().st_size > size_limit):
            raise ValueError("Unreviewed patch file: " + key)
        if key.startswith("src/test/") and key in base:
            raise ValueError("Reviewed experiment cannot replace accepted regression tests")
        text = path.read_text(encoding="utf-8")
        if expected[key] != sha(text):
            raise ValueError("Reviewed patch file changed: " + key)
        changes[key] = text
    if not changes or changes.keys() != expected.keys():
        raise ValueError("Reviewed patch missing files")
    return changes
