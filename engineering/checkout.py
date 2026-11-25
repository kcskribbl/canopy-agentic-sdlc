"""Publish reviewed Maven source changes without replacing the application directory."""
from pathlib import Path
import os
import tempfile


def replace(path, contents):
    if contents is None:
        path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as out:
        temp = Path(out.name)
    try:
        temp.write_bytes(contents)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def publish(root, before, after, undo, extra_files=()):
    root = root.parent.resolve() / root.name
    if root.resolve() != root:
        raise ValueError(f"Refusing a redirected application directory: {root}")
    expected = before.keys() | after.keys()
    for path in (root / "src").rglob("*"):
        if path.is_file() and path.relative_to(root).as_posix() not in expected:
            raise ValueError(f"Unmanaged application source; leaving checkout unchanged: {path}")
    changes = []
    for key in sorted(expected):
        path = root / key
        if (key != "pom.xml" and key not in extra_files and not key.startswith("src/")) or not path.resolve().is_relative_to(root) or path.resolve() != path:
            raise ValueError(f"Invalid managed application path: {key}")
        old = path.read_bytes() if path.exists() else None
        current = None if old is None else old.decode("utf-8").replace("\r\n", "\n")
        # A retry after interruption may find an already-published subset.
        if current == after.get(key):
            continue
        if current != before.get(key):
            raise ValueError(f"Local changes to {path}; reconcile before publishing")
        changes.append((path, old, after.get(key)))
    for path, old, text in changes:
        replace(path, None if text is None else text.encode("utf-8"))
        undo.callback(replace, path, old)
