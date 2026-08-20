# Major refactor plan

The public API described here is intended to be exposed to CodeAct-style agents
that perform actions by executing Python snippets. The API consists of bounded
helpers for exploring and manipulating explicitly configured resources such as
files, directories, OKF repositories, and S3 object buckets.

Unless an agent explicitly produces prose or JSON constrained by a JSON schema,
it should perform work through a snippet action and either return an object or
perform the requested side effect. Helpers and APIs will normally be injected
into a dedicated `SnippetEnvironment` through the existing `provided_types`
mapping. Preserve the current API and build upon the project-owned runtime
types.

All agent operations and helper methods are synchronous for now.

## Results and serialization

Agents should return JSON-serializable data or instances of the abstract
`AgentResult` class. Both representations produced by an `AgentResult` must be
JSON-serializable:

- `_to_agent_state_repr()` returns a short, model-facing view of an
  `AgentResult` whose key in `context.state` was added, updated, or deleted. The
  runtime currently tracks only operations that directly touch
  `context.state` keys; it does not track mutations nested inside stored
  objects.
- `_todict()` returns the full model-relevant data represented by the object.
  It is used for a complete view, including through `context.display`.

Full model-relevant data does not include internal clients, connections,
credentials, configured filesystem roots, factories, or other host
capabilities. Helpers should materialize unserializable clients and connections
only when an operation needs them, and should never expose them through either
result representation.

Use the existing result-view helpers so a consuming agent can first inspect a
collapsed result and explicitly request or display its complete representation.

## Filesystem rules

The initial implementation is intentionally limited to simple filesystem
objects and regular synchronous filesystem operations.

- Operate only on regular files and real directories.
- Reject symlinks, including symlinks in intermediate path components.
- Reject sockets, FIFOs, devices, and every other non-regular filesystem
  object.
- A lock represented by an ordinary regular file, including a file with a
  `.lock` suffix, is treated as a regular file. No filename-based lock detection
  is required.
- Preserve the root-confinement behavior of `ReadOnlyDir` for every source and
  destination path.
- Writing and editing methods replace the original file or its contents using
  ordinary filesystem behavior.
- Copy operations must reject special source or destination objects. Recursive
  copies must reject a special object anywhere in the copied tree.

The agents normally receive one writable workspace directory. Access to files
outside that workspace is deliberately limited and exposed through narrower
helpers such as `ReadCopyDir`.

Changes involving path resolution, traversal, symlinks, or special files must
include regression tests for accepted regular objects and rejected objects.

## Helper classes

Helper classes give agents bounded ways to navigate and manipulate external
resources. Document their public APIs in the same detailed style as
`ReadOnlyDir` so generated stubs can be included in the instructions of agents
and subagents that use them.

### ReadOnlyDir

Use the existing `ReadOnlyDir` as the starting point for browsing a configured
directory. Retain its root-confined listing, globbing, searching, and text-file
reading APIs. Update its validation where necessary to enforce the shared
filesystem rules, including rejection of symlinked path components and special
filesystem objects.

### ReadCopyDir

Implement `ReadCopyDir` as a child of `ReadOnlyDir`. It represents limited
access to a directory outside the agent's workspace and has a separately
configured workspace destination root set during initialization.

- `copy()` copies one regular file from the readable root into the configured
  workspace root. It does not accept directories.
- `copy_dir()` recursively copies a real directory into the configured
  workspace root. It accepts only trees made from regular files and real
  directories and fails if it encounters a symlink or another special object.

Source paths are confined to the readable root and destination paths are
confined to the configured workspace root. Existing regular destination files
may be replaced using normal filesystem copy behavior.

### WritableDir

Implement `WritableDir` as a child of `ReadOnlyDir`, adding the ability to:

- write a regular file, creating it or replacing its complete contents;
- replace string content in a regular file;
- delete a regular file;
- rename a regular file; and
- copy a regular file within the configured writable root.

All source and destination paths remain confined to the same configured root.
Operations use ordinary filesystem semantics and replace original files or
contents when editing. They must enforce the shared filesystem rules before
operating.

### ReadOnlyFile

Implement a file object that subclasses `AgentResult` and represents an
explicitly available read-only regular file. It is used primarily while
building context and instructions to tell an agent that the file is available.
Its result representations expose all model-relevant file data needed for
reference and manipulation, but never expose internal roots or host
capabilities. File contents must remain JSON-serializable when included.

### WriteFile

Implement `WriteFile` using the existing proposed name and as the writable
counterpart of `ReadOnlyFile`. It indicates during instruction formatting that
an explicit regular file exists and may be written or overwritten. Its read and
write operations follow the shared filesystem rules, and its result
representations follow the same serialization rules as `ReadOnlyFile`.

### OfficeCLI file wrappers (future)

Implement a future synchronous Python wrapper around a pinned OfficeCLI
version for manipulating `.docx`, `.xlsx`, and `.pptx` files through the
OfficeCLI batch API. The wrapper is an explicitly granted file capability, not
a general subprocess or filesystem capability.

Use an abstract `OfficeFile` derived from `WriteFile`, with format-specific
`WordFile`, `WorkbookFile`, and `PresentationFile` subclasses. Trusted
application code selects the subclass after validating the file format. The
public object is attached under `context.files[id]`; it must not expose the
OfficeCLI executable, subprocess environment, absolute host path, credentials,
or runner implementation through its public API or result representations.

Each format-specific file exposes `batch()` and returns a fresh fluent builder:

```python
result = (
    presentation.batch()
    .set("/slide[1]/shape[1]", props={"text": "Quarterly Results"})
    .add(
        "/",
        type="slide",
        props={"title": "Risks and next steps"},
    )
    .validate()
    .apply()
)
```

Builder methods enqueue commands and return the same builder so calls can be
chained. They do not modify the file until `apply()` is called. A builder is a
temporary host-bound capability: do not serialize it, persist it, put it in
`context.state`, or reuse it after `apply()`.

#### Batch operations

The builder API follows the pinned OfficeCLI `BatchItem` operations and field
names rather than inventing higher-level document-editing operations. Implement
these public methods:

```python
class OfficeBatch:
    def get(self, path: str, *, depth: int | None = None) -> Self: ...
    def query(self, selector: str) -> Self: ...
    def set(self, path: str, *, props: Mapping[str, JSONValue]) -> Self: ...
    def add(
        self,
        parent: str,
        *,
        type: str,
        props: Mapping[str, JSONValue] | None = None,
        source: str | None = None,
        index: int | None = None,
        after: str | None = None,
        before: str | None = None,
    ) -> Self: ...
    def remove(self, path: str) -> Self: ...
    def move(
        self,
        path: str,
        *,
        to: str | None = None,
        index: int | None = None,
        after: str | None = None,
        before: str | None = None,
    ) -> Self: ...
    def swap(self, path: str, path2: str) -> Self: ...
    def view(self, mode: str) -> Self: ...
    def validate(self) -> Self: ...
    def apply(self) -> dict[str, JSONValue]: ...
```

`source` maps internally to the OfficeCLI batch field `from`; the Python name
avoids using the reserved keyword. Emit the canonical `command` discriminator,
not the `op` alias. Compile all queued operations into one JSON array and invoke
OfficeCLI batch once. Return the literal structured OfficeCLI JSON response
decoded into a usable Python dictionary.

OfficeCLI batch also supports `raw` and `raw-set`, but do not expose them in the
initial agent-facing API. Direct XML manipulation materially expands the
corruption and security surface and can be added later as a separately reviewed
capability.

#### Format-specific permissions

Use `WordBatch`, `WorkbookBatch`, and `PresentationBatch` subclasses. Their
method names and serialized fields remain identical to `OfficeBatch`, but each
subclass validates the paths, element `type` values, view modes, and operations
permitted for its document format. Generated stubs must show only the methods
and literal values available for that format where practical.

Wrapper validation is intentionally shallow. It checks the command shape,
format-level allowlists, path syntax, JSON serializability, command count, and
encoded payload size. OfficeCLI remains responsible for document-dependent
validation such as whether a path exists, a parent accepts an element type, or
a property applies to a selected element. Do not reproduce OfficeCLI's full DOM
and OpenXML rules in Python.

#### Execution and replacement semantics

The internal OfficeCLI runner is trusted application configuration and must not
be supplied by the model. Invoke an explicitly configured executable using an
argument list with `shell=False`, a restricted environment, a timeout, and
bounded stdout and stderr handling. Pin and test the supported OfficeCLI
version because its batch schema and behavior may change.

Disable automatic resident mode for wrapper calls. `apply()` must provide the
same replace-original semantics as `WriteFile`:

1. reject an empty batch and an already-applied builder;
2. revalidate that the target and every path component are regular and not
   symlinks;
3. operate on a trusted temporary copy created beside the target file;
4. run one atomic OfficeCLI batch without `--best-effort` or `--force`;
5. require a successful response and run document validation;
6. replace the original with the validated temporary result using
   `os.replace()`; and
7. preserve the original byte-for-byte if execution, decoding, or validation
   fails.

Serialize concurrent writes to the same target within the wrapper. OfficeCLI's
own concurrent batch promotion can otherwise be last-writer-wins even when each
individual batch reports success.

#### Commands outside the batch API

Do not force terminal-only OfficeCLI commands into `OfficeBatch`. The initial
wrapper does not expose process and installation operations such as `open`,
`save`, `close`, `plugins`, `watch`, `mcp`, `skills`, `install`, or `config`.

Potentially useful non-batch operations require separate APIs and security
review:

- `dump()` may be an immediate read method on an existing `OfficeFile`;
- Word `refresh()` may be an immediate transactional mutation;
- `create`, `merge`, and export operations create or select additional paths
  and therefore belong on a separately authorized, root-confined workspace
  factory or directory capability rather than on `OfficeFile`.

Tests must cover every batch operation, format-level rejection, malformed and
oversized commands, non-JSON values, special files, symlink replacement races,
timeouts, invalid CLI JSON, failed document validation, builder reuse,
concurrent writes, and preservation of the original file on every failure.

### ReadOnlyOKF

Implement `ReadOnlyOKF` as a child of `ReadOnlyDir` representing a read-only OKF
repository. In addition to the inherited directory APIs, it provides methods
to:

- get the OKF index;
- get the OKF directory tree;
- read the metadata header of a concept Markdown file; and
- read the Markdown contents separately from its metadata header.

### WritableOKF

Implement `WritableOKF` using the regular writable-directory behavior together
with `ReadOnlyOKF`. It intentionally retains the ordinary directory APIs, so an
agent may manipulate regular files in the repository directly. It additionally
provides convenience methods for editing only the metadata header or only the
Markdown contents of an OKF concept file.

These OKF-specific methods add direct manipulation APIs; they are conveniences,
not restrictions on the inherited writable-directory capability.

### Processing

Implement a synchronous `Processing` helper around the Docling Serve remote
API. It is initialized by trusted application code with the API URL and common
processing parameters. When supported, it may also be configured with a custom
OpenAI-compatible VLM endpoint for image descriptions.

Processing methods accept only regular source files. Docling Serve is
responsible for converting documents into Markdown and representing page or
document structure. Return the literal JSON response from Docling Serve decoded
into a usable Python dictionary; do not normalize it into a project-specific
result schema. Model-facing skills will describe how agents should interpret
these dictionaries.

#### S3 processing cache

S3 caching is optional and is enabled only when trusted cache-bucket
configuration and credentials are supplied.

1. Compute a SHA-256 hash from the raw bytes of the original input file.
2. Use the hash to look up a cached JSON response under a convenient key such
   as `docling/<sha256>.json`.
3. On a valid cache hit, decode the cached JSON object and return it as a Python
   dictionary without calling Docling Serve.
4. Treat a missing, unreadable, malformed, or non-dictionary cached object as a
   cache miss.
5. On a cache miss, process the original file with Docling Serve, decode its
   response into a Python dictionary, store that response as JSON under the
   hash-derived key, and return the dictionary.
6. If caching is not configured, process the file normally and return the
   decoded response dictionary.

Assume for now that processing configuration is identical for every invocation,
so the original file hash alone is sufficient as the cache key. S3 clients and
credentials are internal implementation details and must not be serialized or
exposed to the agent.

#### process_word

Process a regular Word document through Docling Serve and return its decoded
JSON response dictionary.

#### process_pdf

Process a regular PDF document through Docling Serve and return its decoded
JSON response dictionary.

#### process_excel

Process a regular Excel document through Docling Serve and return its decoded
JSON response dictionary.

#### process_pptx

Process a regular PowerPoint document through Docling Serve and return its
decoded JSON response dictionary.
