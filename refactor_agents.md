# Instructions for specific agent implementations

This document is the authoritative starting specification for concrete agents
in this repository.

All agents must:

- subclass the abstract `AgentBuilder`;
- expose a synchronous public API;
- be usable as preconfigured objects injected into a Python
  `SnippetEnvironment` through its existing `provided_types` mapping;
- construct their instructions through the shared Jinja template environment;
- expose public stubs in the same style as the helpers described in
  `refactor_helpers.md`; and
- return JSON-serializable `AgentResult` subclasses rather than SDK run-result
  objects.

Agent instances are request-bound. Construct an agent for one request, call
`run()` once, and construct a new instance for the next request. A later
instance may be initialized with the same or different context inputs.

## Public lifecycle

`AgentBuilder` does not impose a universal public constructor signature. Each
concrete `AgentBuilder` subclass defines a constructor appropriate to its
purpose. All concrete agents expose an argument-free synchronous `run()` method
and remain request-bound as described above.

Agents whose purpose does not fully determine the instruction for a particular
invocation accept both a focused `task` and the original `user_message`. This
applies to configurable-purpose agents such as `TextGenerationAgent` and
`REPLAnswerAgent`:

```python
agent = TextGenerationAgent(
    task="Write a concise comparison of the supplied reports.",
    user_message="Compare our quarterly reports and explain anything unusual.",
    context=ContextInput(...),
)
agent_result = agent.run()
```

For these configurable-purpose agents, the textual inputs have different roles:

- `task` is the focused instruction for this particular agent invocation. It is
  sent to the OpenAI Agents SDK as the user chat message when the agent runs.
- `user_message` is the original, broader user request that motivated the
  focused task. It is rendered into the `<environment>` section of the system
  instructions so an agent or subagent retains the context of the larger task.

Do not duplicate `task` in the system instructions.

An agent whose class defines one unambiguous operation does not accept a
separate `task`. Its fixed task belongs in that subclass's instructions, and its
constructor accepts only the request inputs needed for that operation. For
example, `SearchQueryRewriteAgent` accepts `user_message` because rewriting the
message into search queries is already its complete task.

`run()` returns the first ordinary model answer produced after zero or more tool
calls. In other words, an agent may call tools repeatedly, but it stops on its
first model response that contains no tool call.

## Public and background configuration

Public constructors should contain only the user-facing inputs appropriate to
the concrete agent, such as `task`, `user_message`, or context parameters. They
must not expose SDK agents, models, clients, tool closures, `SnippetEnvironment`,
the mutable runtime `Context`, or other host internals.

Use a user-facing immutable `ContextInput` wrapper to describe values available
to an invocation. It may contain files, collections, websites, images,
knowledge bases, prior results, and initial state, keyed by their model-facing
context IDs. Concrete agents privately transform this input into the internal
runtime `Context` needed for rendering and execution.

`AgentBuilder` owns a protected `_global_configs` dictionary containing trusted
background configuration shared by constructed agents. Rename the previous
public `global_configs` attribute to `_global_configs`. Model configuration,
trusted `provided_types`, factories, and similar application capabilities
belong in protected configuration and must not appear in public stubs or
model-facing result representations.

For `REPLAnswerAgent`, background construction follows this boundary:

```text
ContextInput
    -> private Context construction
    -> protected provided bindings from _global_configs
    -> private SnippetEnvironment construction
    -> private SDK tool closure
```

Agents themselves may be injected as capabilities into another
`SnippetEnvironment` through `provided_types`. Agent objects and other host
capabilities must not be stored in model-controlled `context.state`.

## Result types

Each concrete agent returns its own `AgentResult` subclass containing the full
answer string in a public `result` field:

```python
class TextGenerationResult(AgentResult):
    result: str


class REPLAnswerResult(AgentResult):
    result: str
```

The complete representation returned by `_todict()` includes the entire result:

```json
{
  "type": "TextGenerationResult",
  "result": "Complete generated response..."
}
```

The compact `_to_agent_state_repr(operation)` representation includes the
operation, a bounded preview, and the length of the full result, rather than
repeating a potentially large response:

```json
{
  "_type": "TextGenerationResult",
  "_operation": "add",
  "_fields": {
    "result_preview": "Beginning of response...",
    "length": 1842
  },
  "_metadata": {}
}
```

Both representations must be JSON-serializable. The result objects and their
`result` fields must be included in generated stubs.

## Templating

Use Jinja templates rooted at `agent-runtime/templates`. The canonical global
template is `templates/agent_instructions.md.j2`. Build instructions
iteratively from the most concrete representation to the global template:

```text
individual item template
    -> source or section template
    -> environment, Python API, skills, or knowledge-base section
    -> agent_instructions.md.j2
```

Component templates belong in:

- `templates/agent_templates/` for an agent's role, responsibilities, and
  restrictions;
- `templates/python_apis/` for stubs of APIs available to the agent;
- `templates/skills/` for model-facing skills;
- `templates/environment/` for the original user message and available runtime
  context; and
- `templates/knowledge_base/` for RAG results, web-search results, and OKF
  knowledge sources.

Section templates own their semantic wrappers. The global template receives
completed sections and arranges them without wrapping them a second time.
Templates may render Markdown inside XML-like semantic tags. Each collection is
enclosed by its section tag, and individual items receive short context-local
IDs and any relevant metadata.

### Python APIs

All Python APIs available to the agent are enclosed in one section:

```markdown
<python_api>
API stubs available in the snippet environment
</python_api>
```

### Skills

Each rendered skill has its own semantic enclosure inside the rendered skills
section:

```markdown
<skill id="skill_id">
Skill Markdown contents
</skill>
```

### Retrieval results

Knowledge items produced by the same retrieval query are pooled together.
`<metadata>` contains YAML metadata describing the retrieval and item:

```markdown
<retrieval id="query_id">
<metadata>
query: "query here"
source: RAG
</metadata>
<retrieval_item id="1">
<metadata>
inclusion_criteria:
    - one
    - two
</metadata>
Markdown contents here...
</retrieval_item>
</retrieval>
```

Web-search results use the same nested structure, with `<web_search>` identifying
one search:

```markdown
<web_search id="search_id">
<metadata>
query: "query here"
source: brave search
</metadata>
<retrieval_item id="1">
<metadata>
inclusion_criteria:
    - one
    - two
</metadata>
Markdown contents here...
</retrieval_item>
</web_search>
```

### OKF knowledge bases

Render an OKF knowledge base with its index and any concepts selected for the
current context:

```markdown
<knowledge_base id="knowledge_base_id">
<metadata>
name: "knowledge base name"
other: metadata
</metadata>
<index>
OKF repository index file
</index>
<concept id="1">
Relevant OKF concept Markdown
</concept>
</knowledge_base>
```

### Context IDs and lookup

Top-level IDs correspond directly to keys in the appropriate internal
`Context` registry. For example:

```python
context.knowledge_bases["knowledge_base_id"]
context.collections["query_id"]
context.websites["search_id"]
context.files["file_id"]
```

Nested IDs such as `<retrieval_item id="1">` and `<concept id="1">` are local
to their enclosing source. They are accessed through the object selected by
the outer registry key. Skills and public stubs must show this two-level lookup
explicitly so the model can resolve rendered IDs back to Python objects.

IDs should be short enough for a model to copy and manipulate and must be
unique within their enclosing context or source.

### Environment

All environment items are contained in one `<environment>` section. It includes
the original broader user message and rendered entries for available files,
collections, websites, images, knowledge bases, prior results, and initial
state where applicable:

```markdown
<environment>
<user_message>
Original broader user request
</user_message>

Rendered context items...
</environment>
```

The environment may later include a compaction summary and reintroduce state
whose earlier tool representation was compacted. Compaction behavior is only a
planning stub for now and must not be implemented as part of the initial agent
work.

## Agents

### AgentBuilder

`AgentBuilder` is an abstract base class with no concrete agent behavior. It
contains protected global configuration and shared helpers for building every
agent's instructions from the Jinja template hierarchy. Its public `run()`
contract is synchronous.

### TextGenerationAgent

`TextGenerationAgent` is a request-bound text-generation agent. It receives a
focused `task`, the original `user_message`, and optional `ContextInput`, builds
its system instructions from the configured templates, and synchronously runs
until the first non-tool-call model answer.

It returns `TextGenerationResult`, whose `result` field contains the complete
answer string.

### REPLAnswerAgent

`REPLAnswerAgent` is a request-bound CodeAct-style answering agent. It receives
a focused `task`, the original `user_message`, and optional `ContextInput`.
Internally it constructs a runtime `Context`, injects protected bindings into a
`SnippetEnvironment`, and exposes snippet execution to the SDK agent as a tool.

The snippet namespace contains `context` and the trusted values supplied through
`provided_types`. The agent explores model-visible values through `context`,
including two-level lookups described by rendered IDs. `print()` is not exposed
as a safe builtin and stdout is not part of the execution protocol. Snippet
results communicate through structured context updates, display data, and error
reports.

The agent may perform zero or more snippet tool calls and stops on its first
ordinary model answer. It returns `REPLAnswerResult`, whose `result` field
contains that complete answer string.

### ImageDescriptionAgent

`ImageDescriptionAgent` is a request-bound multimodal agent with the public
lifecycle:

```python
result = ImageDescriptionAgent(file=image_file, task=focus).run()
```

`file` must be a `ReadOnlyFile` naming a supported PNG, JPEG, WebP, or
non-animated GIF image. `task` is the focused instruction describing which
visible details the model should prioritize. The agent sends the task and image
together as one SDK user message; image bytes must not be rendered into system
instructions or stored in model-controlled context.

The agent distinguishes visible observations from uncertain interpretation and
does not invent unseen content. It returns `ImageDescriptionResult`, whose
`result` field contains the complete description string.

### SearchQueryRewriteAgent

`SearchQueryRewriteAgent` is a simple agent used to rewrite original user query into a small set of targeted queries that answer the users information need.
This agent takes in original user request and immediately in one turn generates queries for Brave LLM Context Search using constrained jsonschema.
It is intended to be the first step toward either giving the user an answer or
performing further search when the initial search results are insufficient.
It is a fixed-purpose `AgentBuilder` subclass, so its public lifecycle is:

```python
result = SearchQueryRewriteAgent(user_message=user_message).run()
```

It does not accept `task`: the query-rewriting task is defined by the agent's
class and instruction template, while `user_message` is the request supplied as
the SDK user chat message.

The result schema should be compatible with follwing example:

```json
{
  "description": "2-3 short sentences of the task that should be performed on user query",
  "entities": ["entities to resolve"],
  "information_needs": ["short descritpiton of information need based on user query"],
  "queries": [
    {
      "query": "query_1",
      "complexity": "simple"
    },
    {
      "query": "query_2",
      "complexity": "complex"
    }
  ]
}
```

Each query carries a semantic `complexity` preset rather than provider-specific
context-size parameters:

- `simple` is a narrow lookup for one directly verifiable fact;
- `standard` is an ordinary explanatory or multi-source lookup and is the
  default choice when complexity is uncertain; and
- `complex` requires broad research, comparison, synthesis, or resolution of a
  disputed topic.

The search executor translates these presets into Brave LLM Context parameters:

| Complexity | `count` | `maximum_number_of_tokens` |
| --- | ---: | ---: |
| `simple` | 5 | 2048 |
| `standard` | 20 | 8192 |
| `complex` | 50 | 16384 |

This mapping is execution policy and does not belong in the agent output. The
executor may downgrade individual presets to enforce an aggregate search-token
budget when several queries are returned.

Use the following strict JSON Schema for the structured output. The requirement
that `description` contain two or three sentences is a prompting constraint;
JSON Schema cannot reliably count natural-language sentences.

```json
{
  "title": "SearchQueryRewriteResult",
  "description": "A focused search plan derived from the original user request.",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "description": {
      "type": "string",
      "description": "Two or three short sentences describing the task to perform for the user.",
      "pattern": ".*\\S.*"
    },
    "entities": {
      "type": "array",
      "description": "Named entities or ambiguous references that the search should resolve.",
      "items": {
        "type": "string",
        "pattern": ".*\\S.*"
      },
      "maxItems": 20
    },
    "information_needs": {
      "type": "array",
      "description": "Short descriptions of the distinct information needed to answer the request.",
      "items": {
        "type": "string",
        "pattern": ".*\\S.*"
      },
      "minItems": 1,
      "maxItems": 10
    },
    "queries": {
      "type": "array",
      "description": "Targeted queries to submit to Brave LLM Context Search.",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "query": {
            "type": "string",
            "description": "A targeted query to submit to Brave LLM Context Search.",
            "pattern": ".*\\S.*"
          },
          "complexity": {
            "type": "string",
            "description": "Semantic complexity used by the executor to select a search budget.",
            "enum": ["simple", "standard", "complex"]
          }
        },
        "required": ["query", "complexity"]
      },
      "minItems": 1,
      "maxItems": 5
    }
  },
  "required": [
    "description",
    "entities",
    "information_needs",
    "queries"
  ]
}
```
