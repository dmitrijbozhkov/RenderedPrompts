# Persistent Python Agent

An intentionally small example using the OpenAI Agents SDK. The agent includes
persistent Python execution, web fetching, ParadeDB RAG search, and a typed
haiku sub-agent exposed as a tool.

The `execute_code` tool:

- runs model-supplied Python in a fresh subprocess;
- captures standard output, standard error, exceptions, and tracebacks;
- exposes a persistent dictionary named `state`;
- restores and reserializes Python's complete `__main__` module with `dill`
  for every snippet;
- renders run-specific instructions from a Jinja template using the context
  passed to `Runner.run`.

The persisted module includes `state` plus globals such as imports, functions,
and classes. If a snippet raises an exception, its error is returned to the
model and the modified state is still serialized.

> [!WARNING]
> This is a local, trusted-development example—not a security sandbox. Model
> generated Python can read files, start processes, access credentials, or do
> anything else allowed to the current OS user. Use a real isolated runtime
> (container/VM, resource limits, restricted network and filesystem, and
> approval controls) before exposing it to untrusted users.

## Setup

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
export OPENAI_API_KEY="..."
```

Optionally choose a model or state directory:

```bash
export OPENAI_MODEL="gpt-5.6-sol"
export PYTHON_AGENT_STATE_DIR=".agent_state"
export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5443/postgres"
export EMBEDDING_BASE_URL="http://localhost:8000/v1"
export EMBEDDING_API_KEY="not-needed"
export EMBEDDING_MODEL="text-embedding-3-small"
```

`search_rag` expects a ParadeDB table named `documents` with integer `id`
and text `content` columns, a pgvector `embedding` column, a BM25 index whose
key field is `id`, and a cosine-distance vector index. Its query follows
sqlalchemy-paradedb's official hybrid RRF example: BM25 and semantic results
are fused using reciprocal rank fusion with `k=60`. Stored document embeddings
must use the same model and dimensions as `EMBEDDING_MODEL`.

## Run

```bash
persistent-python-agent \
  --context-json '{"user_name":"Ada","preferred_units":"metric"}' \
  "Store the first 20 Fibonacci numbers in state, then report their sum."
```

Run another request with the same state directory:

```bash
persistent-python-agent \
  --context-json '{"user_name":"Ada","preferred_units":"metric"}' \
  "Use the Fibonacci numbers you saved previously and print the last five."
```

The template lives at
`src/persistent_python_agent/templates/instructions.jinja2`. The application
passes an `AgentContext` to the runner:

```python
from agents import Runner
from persistent_python_agent import AgentContext, build_agent

context = AgentContext(
    instruction_data={
        "user_name": "Ada",
        "preferred_units": "metric",
    }
)

result = await Runner.run(
    build_agent(),
    "Calculate the first 20 Fibonacci numbers.",
    context=context,
)
```

The Agents SDK calls `build_instructions(context, agent)` when the agent is
invoked. That function renders the Jinja template using
`context.context.instruction_data`, making the selected local context data
visible to the model as instructions.

The tool returns JSON in this shape:

```json
{
  "ok": false,
  "stdout": "",
  "stderr": "",
  "error": "ValueError: boom",
  "traceback": "Traceback (most recent call last): ..."
}
```

## Test

```bash
pytest
```

Tests exercise the executor without making API calls.
