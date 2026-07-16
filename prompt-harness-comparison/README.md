# Agent harness prompt construction: comparative field guide

Research date: 2026-07-16 (Europe/Berlin)

## Scope and interpretation

This package compares the generic, built-in prompt-construction paths of six agent harnesses. It covers primary agents, built-in subagents, hidden/system agents, and prompt-changing workflows. Product-specific example applications built on top of a framework are outside scope unless they define the framework's generic delegation mechanism.

"MS Agent" is interpreted as ModelScope's `modelscope/ms-agent`, because that is the project whose public name is `ms-agent`. It is not Microsoft's Agent Framework.

Each `.txt` file is a source-faithful rendered example request. It separates:

- `SYSTEM`: text placed in one or more system/developer instructions;
- `MESSAGES`: chat history after harness-specific rewriting;
- `TOOLS`: function/tool schemas sent through the provider API, when not embedded in text;
- `RUNTIME`: non-prompt controls such as permissions, model selection, stop strings, and iteration limits.

Fixed prompt prose found in the examined source/package is reproduced in the example instead of being represented by a named block. Braced placeholders are reserved for data that varies with the user's request, repository, configured agent, memory, or resulting session—for example `{user_request}`, `{project_instructions}`, and `{conversation_history}`. JSON objects, shell substitutions such as `${MEMORY_DIR}`, and braces inside upstream code examples are literal source text, not omissions. Provider chat-template tokens are omitted because the provider SDK/model tokenizer, rather than the harness, normally renders those.

For selectors whose output depends on the request, the examples choose one concrete built-in branch. For example, little-coder renders its packaged `two_pointers.md` knowledge card and `read.md` tool card rather than leaving `{selected_card}` markers. Alternative fixed branches receive separate workflow files where they materially change the prompt, such as Letta Code's Claude, Codex, and Gemini source presets.

## Versions examined

| Harness | Reference examined | Nature of system |
|---|---|---|
| Qwen Code | npm `@qwen-code/qwen-code` 0.19.10 plus upstream docs | Opinionated CLI with multiple built-in worker prompts |
| Qwen Agent | upstream `main` | Python framework; prompt shape depends on agent class and LLM adapter |
| opencode | upstream `dev` and docs updated 2026-07-14; npm 1.18.2 cross-check | CLI with model-specific base prompts and configurable agents |
| MS Agent | ModelScope `ms-agent` upstream `main` | Python framework driven by merged YAML/OmegaConf configuration |
| Letta Code | npm `@letta-ai/letta-code` 0.28.8 plus upstream source | Persistent-agent CLI with memory-aware prompt presets |
| little-coder | npm `little-coder` 1.10.0; bundled pi 0.79.4 | pi launcher that replaces pi's default prompt and adds extension blocks |

## Executive comparison

| Axis | Qwen Code | Qwen Agent | opencode | MS Agent | Letta Code | little-coder |
|---|---|---|---|---|---|---|
| Base prompt selection | Qwen Code core, or `QWEN_SYSTEM_MD` replacement | Caller-supplied system; default helpful-assistant text | Agent prompt, else model-family prompt | Merged YAML `prompt.system`; fallback constant | Persisted preset selected by memory mode | Packaged `AGENTS.md` passed as pi custom system prompt |
| Project/user instructions | User memory and append instruction suffix | Caller messages/files; class-specific transforms | Environment, skills, MCP, global/project rules, configured instructions | Personalization then skill injection | Memory blocks/filesystem and client skills | Extension-selected cards, algorithm references, then date/cwd |
| Tool description transport | API-native schemas | Nous XML text by default; optionally API-native | API-native schemas | API-native schemas | API-native schemas | API-native schemas, while `AGENTS.md` also explains tools |
| Main history | Normal conversation history | Normal history, sometimes rewritten | Session history with synthetic read/subtask parts | `Message` history plus memory/session assembly | Server-persisted conversation plus memory context | pi session history |
| Subagent context | Type-dependent: fresh, forked, workflow, or teammate | Framework has no single universal subagent protocol; GroupChat rewrites roles | Child session receives task prompt; agent/environment/rules rebuilt | Fresh configured LLMAgent; dynamic splitter supplies system and query | Some fresh specialized agents; fork/recall inherit full trajectory | Fresh child process with same base system; no parent transcript by default |
| Read-only enforcement | Prompt plus tool/permission restriction | Tool list chosen by caller/agent | Permission rules are authoritative; prompt may only describe intent | Tool config/disallowed tools | Subagent tool profile and sandbox | Child allowed-tool environment and permission gate |
| Persistent identity/memory | User memory suffix | Optional memory components/classes | Rules and session state, not identity-first | Optional memory and personalization | Central design: system memory is part of agent identity | None beyond files/session unless an extension adds it |
| Prompt changes per turn | Mode, sandbox, git state, memory, available tools | Agent preprocessor may rewrite final user message | Environment, references, skills, MCP, rules, structured-output modifier | Personalization and skills rebuilt; messages assembled | Memory/skills can be recompiled; reminders may be injected inline | Knowledge cards, skill cards, plan/research blocks, date/cwd |

## Construction pipelines

### 1. Qwen Code

Normal main-agent order:

1. Select the packaged Qwen Code core prompt, unless `QWEN_SYSTEM_MD` replaces it with a file.
2. Add fixed sections for mandates, software-engineering workflow, operational guidance, tone, security, tool use, delegation, code search, sandbox/git behavior, and action guidance.
3. Append user-memory/custom-instruction material and optional caller append instructions.
4. Add mode-specific text, notably plan-mode restrictions/reminders.
5. Send tool schemas separately through the model adapter and send the accumulated chat history.

Subagents do not share one universal template. `general-purpose` and `Explore` use dedicated system prompts; workflow workers use a workflow-specific system; fork workers receive a fork boilerplate and directive; teammates get team identity/context. The fork path explicitly tells workers not to spawn further agents. The examples in `qwen-code/agent/subagent/` preserve these differences.

### 2. Qwen Agent

Qwen Agent is a framework rather than a single CLI prompt. Three materially different paths exist:

1. `FnCallAgent`/`Assistant` with the default Nous function-calling prompt serializes function definitions into a tools block appended to the first system message. Tool calls and tool results are converted to tagged text messages.
2. With raw/native API tool calling enabled, the system remains caller-controlled and the schemas travel in the API `tools` field.
3. `ReActChat` embeds tool descriptions and its Thought/Action protocol in the final user message, not the system message, and sets Observation stop strings.

`BasicDocQA` adds retrieved reference material to the system message. `GroupChat` is the closest built-in multi-agent harness: it constructs participant personas and rewrites other speakers' turns into `name: content` user text while the selected participant's own turns appear as assistant messages. This is role remapping, not a generic parent/child transcript fork.

### 3. opencode

Normal request order:

1. Use `agent.prompt` when configured; otherwise select a model-family base (`anthropic`, `codex`, `gpt`, `gemini`, `kimi`, `trinity`, `meta`, `beast`, or default).
2. Append an environment block with model identity, working directory/worktree, git/platform/date, and project references.
3. Append the available-skills catalogue and MCP server instructions when enabled.
4. Append instruction sources: global rules, project `AGENTS.md`/`CLAUDE.md`/`CONTEXT.md`, and configured local/URL instructions. Nested rules may instead be attached on demand when a file is read.
5. Append workflow modifiers such as structured-output or max-step instructions.
6. Send provider-native tool schemas and converted session messages.

Built-in primary agents are `build` and `plan`. Current built-in subagents are `general`, `explore`, and `scout`. Internal model workflows include `compaction` and `title`; the current file-change `summary` path is also included to make its lack of a separate LLM prompt explicit. A subagent runs in a child session with its own agent configuration and a synthesized task user message; the parent transcript is not blindly copied as a flat prompt. An explicit `@agent` mention becomes synthetic text directing the main agent to call the task tool.

### 4. MS Agent (ModelScope)

The generic `LLMAgent` order is unusually clear:

1. Start with merged config `prompt.system`; if absent, use the fallback helpful-assistant string. The repository default YAML normally supplies a longer task-execution system prompt.
2. Append the personalization section, if configured.
3. Append skill injection: full bodies for always-loaded skills plus an index/metadata for enabled skills.
4. Assemble memory/session messages.
5. Send tool schemas separately.

Configured `agent_tools` instantiate a fresh agent from a referenced or inline config and forward a request payload. The dynamic `split_to_sub_task` path is especially important: the parent's tool arguments contain `{system, query}` for every child; that `system` becomes the child's `prompt.system`, and `query` becomes its user request. All subagents receive `ms_agent_subagent: true`, which changes runtime defaults such as snapshots, but there is no mandatory hidden "you are a subagent" sentence. Plugin `Task` delegation likewise resolves a plugin agent config and forwards the generated prompt.

### 5. Letta Code

Letta Code's base is persisted as part of the server-side agent rather than rebuilt only as an ephemeral CLI string.

1. Select a managed preset. The default/`letta` preset chooses a memory-filesystem-aware body in MemFS mode and a no-MemFS body otherwise. The Claude Code, Codex, and Gemini CLI source presets are rendered separately because each has a distinct fixed body.
2. Embed or expose memory according to mode: core memory blocks and/or the memory filesystem tree and system files.
3. Append the available-skills block used by the client.
4. Send persisted conversation messages and native tool schemas.
5. Add inline system-reminder wrappers for special events and delegation paths.

Subagent semantics vary. `general-purpose`, `init`, `memory`, `history-analyzer`, and `reflection` have dedicated system prompts and scoped tools. `fork` and `recall` explicitly do not use their markdown body as the runtime system prompt: they retain the parent's system/history via conversation forking and prepend an inline reminder that narrows the new task. This makes Letta Code the strongest contrast between fresh-agent specialization and true trajectory inheritance.

### 6. little-coder

The launcher invokes pi with `--system-prompt AGENTS.md`, `--no-context-files`, and its packaged extension set. In pi, a custom prompt replaces the normal pi base. The effective order is:

1. Packaged little-coder `AGENTS.md`.
2. Any append-system material.
3. Project context files (normally absent because the launcher disables them).
4. Per-turn algorithm reference selected by the knowledge extension.
5. Workflow block, such as Plan Mode or Deep Research, when active.
6. Per-turn tool-usage cards selected by error recovery, recency, and intent.
7. Active pi skill catalogue, if enabled.
8. Current date and current working directory.

Sub-coders are fresh little-coder processes. They receive the same base prompt and extensions but a restricted read/browse tool environment, automatic permission mode, and a concise-report suffix on the user task. There is no separate child system identity and no parent chat transcript. Plan Mode and Deep Research orchestrate multiple such children using specialized user prompts, then inject research findings into a one-shot main-agent system block for synthesis.

## Most consequential differences

### Tool schemas are not always prompt text

Qwen Agent's default Nous adapter textualizes schemas and tool traffic. Its raw mode and all five other harnesses generally send schemas in a separate provider API field. A text-only prompt capture will therefore understate the model input for most harnesses and overstate how universal Qwen Agent's XML is.

### Replacement versus append semantics

- Qwen Code's `QWEN_SYSTEM_MD` can replace the packaged core.
- opencode's custom agent prompt replaces the model-family base but still receives environment/rules segments.
- little-coder's `AGENTS.md` replaces pi's default system prompt, while pi still appends date/cwd and extension content.
- MS Agent and Qwen Agent usually treat caller/config system text as the base and class-specific logic appends or rewrites around it.
- Letta Code persists an entire preset on the agent, then recompiles memory/skills around that persisted identity.

### Parent context inheritance

| Mechanism | Parent conversation visible? | How task is focused |
|---|---:|---|
| Qwen Code fresh built-ins/workflow | Usually no full transcript | Dedicated system plus explicit task |
| Qwen Code fork | Yes | Fork boilerplate and directive |
| Qwen Agent GroupChat | Rewritten shared transcript | Speaker-name role remapping |
| opencode Task child | Task/context selected by caller; separate child session | Task prompt and child agent config |
| MS Agent AgentTool | No automatic parent transcript | Request payload or caller-supplied message list |
| Letta Code fork/recall | Yes | Inline fork reminder overrides inherited trajectory |
| Letta Code fresh specialized agents | Prompt/transcript payload varies | Dedicated system and scoped tools |
| little-coder sub-coder | No | User task plus concise-report suffix |

### Enforcement is not the prose prompt

Read-only and planning behavior is often enforced outside the system text. opencode uses permissions; little-coder uses allowed-tool environment variables and tool-call blocking; Letta Code and Qwen Code provide scoped tools/sandboxes; MS Agent can strip disallowed tools. The `.txt` files therefore list runtime controls next to the rendered prompt.

## Directory map

See `MANIFEST.tsv` for every included workflow. The directory layout follows the requested convention:

```text
{harness}/agent/{workflow}.txt
{harness}/agent/subagent/{workflow}.txt
```

## Primary sources

### Qwen Code

- https://github.com/QwenLM/qwen-code
- https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/sub-agents.md

### Qwen Agent

- https://github.com/QwenLM/Qwen-Agent
- https://github.com/QwenLM/Qwen-Agent/blob/main/qwen_agent/llm/fncall_prompts/nous_fncall_prompt.py
- https://github.com/QwenLM/Qwen-Agent/blob/main/qwen_agent/agents/react_chat.py
- https://github.com/QwenLM/Qwen-Agent/blob/main/qwen_agent/agents/group_chat.py
- https://github.com/QwenLM/Qwen-Agent/blob/main/qwen_agent/agents/doc_qa/basic_doc_qa.py

### opencode

- https://github.com/anomalyco/opencode
- https://opencode.ai/docs/agents/
- https://opencode.ai/docs/rules/
- https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/system.ts
- https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/instruction.ts
- https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/prompt.ts
- https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/llm.ts

### MS Agent

- https://github.com/modelscope/ms-agent
- https://github.com/modelscope/ms-agent/blob/main/ms_agent/agent/agent.yaml
- https://github.com/modelscope/ms-agent/blob/main/ms_agent/agent/llm_agent.py
- https://github.com/modelscope/ms-agent/blob/main/ms_agent/tools/agent_tool.py
- https://github.com/modelscope/ms-agent/blob/main/ms_agent/skill/README.md

### Letta Code

- https://github.com/letta-ai/letta-code
- https://github.com/letta-ai/letta-code/blob/main/src/agent/subagents/builtin/reflection.md

### little-coder

- https://github.com/itayinbarr/little-coder
- https://github.com/itayinbarr/little-coder/blob/main/AGENTS.md
- https://github.com/itayinbarr/little-coder/blob/main/docs/architecture.md

## Caveats

- Upstream prompts change frequently. Version pins above matter.
- Custom agents, plugins, hooks, remote MCP instructions, and user rule files can arbitrarily change final text.
- Some model providers merge multiple system segments; others retain separate system/developer messages. The files show harness-level segments before provider-specific serialization.
- "Exhaustive" here means all generic built-in prompt-construction branches and agent types identified in the examined versions, not every domain-specific demo/project bundled in a framework repository.
