
from __future__ import annotations

from pathlib import Path


class FileStateCache:
    """Tracks which files have been read, enforcing read-before-edit.

    Stores { absolute_path: (content, mtime_ns) } after each ReadFile call.
    EditFile and WriteFile check the cache before proceeding:
      - Gate 1: file must have been read (present in cache).
      - Gate 2: both mtime and content must match the last read; timestamp
        granularity or preserved mtimes must not authorize unseen changes.
    """

    def __init__(self, *, read_text=None) -> None:
        self._cache: dict[str, tuple[str, int]] = {}
        self._read_text = read_text or (lambda path: path.read_text(encoding="utf-8"))

    def content(self, path: str) -> str | None:
        entry = self._cache.get(path)
        return entry[0] if entry else None

    def forget(self, path: str) -> None:
        self._cache.pop(path, None)

    def record(self, path: str, content: str, mtime_ns: int) -> None:
        """Record a file's content and mtime after a successful read."""
        self._cache[path] = (content, mtime_ns)

    def check(self, path: str) -> tuple[bool, str]:
        """Check whether the file is safe to edit/write.

        Returns (ok, error_message). If ok is True, error_message is empty.
        """
        entry = self._cache.get(path)
        if entry is None:
            return False, "Error: file has not been read yet. Read it first before editing."

        cached_content, cached_mtime_ns = entry
        try:
            current_path = Path(path)
            current_mtime_ns = current_path.stat().st_mtime_ns
        except OSError:
            # File may have been deleted; allow the write to proceed
            # (WriteFile will create it, EditFile will fail on its own).
            return True, ""

        if current_mtime_ns != cached_mtime_ns:
            return False, "Error: file has been modified since last read. Read it again before editing."

        try:
            if self._read_text(current_path) != cached_content:
                return False, "Error: file has been modified since last read. Read it again before editing."
        except (OSError, ValueError):
            return False, "Error: cannot verify file contents. Read it again before editing."

        return True, ""

    def update(self, path: str) -> None:
        """Update the cache entry after a successful edit/write."""
        try:
            p = Path(path)
            content = self._read_text(p)
            mtime_ns = p.stat().st_mtime_ns
            self._cache[path] = (content, mtime_ns)
        except (OSError, ValueError):
            # If we can't read it back, just remove the stale entry.
            self._cache.pop(path, None)

    def clear(self) -> None:
        """Discard read-before-edit state after the working directory changes."""
        self._cache.clear()
