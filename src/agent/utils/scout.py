"""Root-confined, read-only filesystem helpers for scouting agents."""

from __future__ import annotations

import builtins
import json
import os
import re
import tomllib
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Iterator


class ScoutFSError(ValueError):
    """Raised when a scouting operation is invalid or unsafe."""


@dataclass(frozen=True)
class Entry:
    """A directory entry relative to the scout root."""

    path: str
    kind: str
    size: int | None
    is_symlink: bool


@dataclass(frozen=True)
class Match:
    """One text-search match."""

    path: str
    line: int
    text: str


@dataclass(frozen=True)
class OutlineItem:
    """One addressable item in a structured document."""

    path: str
    kind: str
    line: int | None = None


@dataclass(frozen=True)
class DocumentOutline:
    """A lightweight structural view of a document."""

    format: str
    items: tuple[OutlineItem, ...]


class ScoutFS:
    """Provide bounded, read-only access beneath one directory."""

    _MARKDOWN_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")

    def __init__(
        self,
        root: str | Path,
        *,
        max_file_bytes: int = 1_000_000,
        max_results: int = 500,
    ) -> None:
        resolved = Path(root).expanduser().resolve(strict=True)
        if not resolved.is_dir():
            raise NotADirectoryError(resolved)
        if max_file_bytes <= 0 or max_results <= 0:
            raise ValueError("limits must be positive")
        self._root: Path = resolved
        self._max_file_bytes: int = max_file_bytes
        self._max_results: int = max_results

    def list(self, path: str = ".") -> builtins.list[Entry]:
        """List one directory without following symlinks."""
        directory = self._resolve(path)
        if not directory.is_dir():
            raise NotADirectoryError(directory)

        entries: builtins.list[Entry] = []
        for child in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
            stat = child.lstat()
            relative = child.relative_to(self._root).as_posix()
            if child.is_symlink():
                kind = "symlink"
                size = stat.st_size
            elif child.is_dir():
                kind = "directory"
                size = None
            elif child.is_file():
                kind = "file"
                size = stat.st_size
            else:
                kind = "other"
                size = stat.st_size
            entries.append(Entry(relative, kind, size, child.is_symlink()))
            if len(entries) >= self._max_results:
                break
        return entries

    def glob(self, pattern: str) -> builtins.list[str]:
        """Return files matching a root-relative glob."""
        if not pattern or Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise ScoutFSError("glob must be a non-empty root-relative pattern")

        matches: builtins.list[str] = []
        for path in self._walk_files():
            relative = path.relative_to(self._root).as_posix()
            if fnmatch(relative, pattern) or (
                pattern.startswith("**/") and fnmatch(relative, pattern[3:])
            ):
                matches.append(relative)
                if len(matches) >= self._max_results:
                    break
        return matches

    def grep(
        self,
        query: str,
        glob: str | None = None,
        *,
        fixed_string: bool = False,
        case_sensitive: bool = True,
    ) -> builtins.list[Match]:
        """Search text files and return bounded, line-oriented matches."""
        if not query:
            raise ScoutFSError("query cannot be empty")
        flags = 0 if case_sensitive else re.IGNORECASE
        expression = re.compile(re.escape(query) if fixed_string else query, flags)

        matches: builtins.list[Match] = []
        paths = self.glob(glob) if glob else [
            path.relative_to(self._root).as_posix() for path in self._walk_files()
        ]
        for relative in paths:
            try:
                text = self._read_text(self._resolve(relative))
            except (ScoutFSError, UnicodeDecodeError):
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if expression.search(line):
                    matches.append(Match(relative, line_number, line))
                    if len(matches) >= self._max_results:
                        return matches
        return matches

    def read(self, path: str, offset: int = 0, limit: int = 200) -> str:
        """Read a bounded range of lines from a UTF-8 text file."""
        if offset < 0 or limit <= 0:
            raise ScoutFSError("offset must be non-negative and limit must be positive")
        lines = self._read_text(self._resolve(path)).splitlines()
        return "\n".join(lines[offset : offset + limit])

    def outline(self, path: str) -> DocumentOutline:
        """Return headings or key paths for Markdown, JSON, or TOML."""
        resolved = self._resolve(path)
        suffix = resolved.suffix.casefold()
        text = self._read_text(resolved)

        if suffix in {".md", ".markdown"}:
            items = self._markdown_outline(text)
            return DocumentOutline("markdown", tuple(items))
        if suffix == ".json":
            value = json.loads(text)
            return DocumentOutline("json", tuple(self._key_outline(value)))
        if suffix == ".toml":
            value = tomllib.loads(text)
            return DocumentOutline("toml", tuple(self._key_outline(value)))
        raise ScoutFSError(f"unsupported document format: {suffix or '<none>'}")

    def query(self, path: str, selector: str) -> Any:
        """Read a Markdown section or select a JSON/TOML value."""
        if not selector:
            raise ScoutFSError("selector cannot be empty")
        resolved = self._resolve(path)
        suffix = resolved.suffix.casefold()
        text = self._read_text(resolved)

        if suffix in {".md", ".markdown"}:
            return self._markdown_section(text, selector)
        if suffix == ".json":
            value = json.loads(text)
        elif suffix == ".toml":
            value = tomllib.loads(text)
        else:
            raise ScoutFSError(f"unsupported document format: {suffix or '<none>'}")

        parts = self._selector_parts(selector)
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            elif isinstance(value, list) and part.isdecimal():
                value = value[int(part)]
            else:
                raise KeyError(selector)
        return value

    def _resolve(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        candidate = candidate if candidate.is_absolute() else self._root / candidate
        resolved = candidate.resolve(strict=True)
        try:
            resolved.relative_to(self._root)
        except ValueError as error:
            raise ScoutFSError(f"path escapes scout root: {path}") from error
        return resolved

    def _walk_files(self) -> Iterator[Path]:
        for directory, names, files in os.walk(self._root, followlinks=False):
            names[:] = sorted(
                name for name in names if not (Path(directory) / name).is_symlink()
            )
            for name in sorted(files):
                path = Path(directory) / name
                try:
                    resolved = self._resolve(path)
                except (FileNotFoundError, ScoutFSError):
                    continue
                if resolved.is_file():
                    yield resolved

    def _read_text(self, path: Path) -> str:
        if not path.is_file():
            raise ScoutFSError(f"not a file: {path}")
        size = path.stat().st_size
        if size > self._max_file_bytes:
            raise ScoutFSError(
                f"file exceeds {self._max_file_bytes} byte limit: "
                f"{path.relative_to(self._root)}"
            )
        data = path.read_bytes()
        if b"\x00" in data:
            raise ScoutFSError(f"binary file is not readable: {path.relative_to(self._root)}")
        return data.decode("utf-8")

    def _markdown_outline(self, text: str) -> builtins.list[OutlineItem]:
        items: builtins.list[OutlineItem] = []
        stack: builtins.list[str] = []
        fenced = False
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith(("```", "~~~")):
                fenced = not fenced
                continue
            match = None if fenced else self._MARKDOWN_HEADING.match(line)
            if match:
                level = len(match.group(1))
                stack[level - 1 :] = [match.group(2).strip()]
                items.append(OutlineItem("/".join(stack), "heading", line_number))
        return items

    def _key_outline(self, value: Any, prefix: str = "") -> builtins.list[OutlineItem]:
        items: builtins.list[OutlineItem] = []
        if isinstance(value, dict):
            for key, child in value.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                items.append(OutlineItem(path, type(child).__name__))
                items.extend(self._key_outline(child, path))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                path = f"{prefix}.{index}" if prefix else str(index)
                items.extend(self._key_outline(child, path))
        return items

    def _markdown_section(self, text: str, selector: str) -> str:
        lines = text.splitlines()
        headings = self._markdown_outline(text)
        selected = next((item for item in headings if item.path == selector), None)
        if selected is None or selected.line is None:
            raise KeyError(selector)

        level = len(lines[selected.line - 1]) - len(lines[selected.line - 1].lstrip("#"))
        end = len(lines)
        for item in headings:
            if item.line is not None and item.line > selected.line:
                next_line = lines[item.line - 1]
                next_level = len(next_line) - len(next_line.lstrip("#"))
                if next_level <= level:
                    end = item.line - 1
                    break
        return "\n".join(lines[selected.line - 1 : end])

    @staticmethod
    def _selector_parts(selector: str) -> builtins.list[str]:
        if selector.startswith("/"):
            return [
                part.replace("~1", "/").replace("~0", "~")
                for part in selector.split("/")[1:]
            ]
        return selector.split(".")
