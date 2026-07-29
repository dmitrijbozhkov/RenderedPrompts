
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
    line: int | None = ...

@dataclass(frozen=True)
class DocumentOutline:
    """A lightweight structural view of a document."""
    format: str
    items: tuple[OutlineItem, ...]

class ScoutFS:
    """Provide bounded, read-only access beneath one directory."""
    def __init__(self, root: str | Path, *, max_file_bytes: int = 1000000, max_results: int = 500) -> None: ...
    def list(self, path: str = '.') -> builtins.list[Entry]:
        """List one directory without following symlinks."""
    def glob(self, pattern: str) -> builtins.list[str]:
        """Return files matching a root-relative glob."""
    def grep(self, query: str, glob: str | None = None, *, fixed_string: bool = False, case_sensitive: bool = True) -> builtins.list[Match]:
        """Search text files and return bounded, line-oriented matches."""
    def read(self, path: str, offset: int = 0, limit: int = 200) -> str:
        """Read a bounded range of lines from a UTF-8 text file."""
    def outline(self, path: str) -> DocumentOutline:
        """Return headings or key paths for Markdown, JSON, or TOML."""
    def query(self, path: str, selector: str) -> Any:
        """Read a Markdown section or select a JSON/TOML value."""
