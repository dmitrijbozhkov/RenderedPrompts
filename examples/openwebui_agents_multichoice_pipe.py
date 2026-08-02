"""
title: OpenAI Agents Multiple-choice Pipe
author: example
version: 0.1.0
requirements: openai-agents>=0.2, pydantic>=2

Open WebUI Pipe example using the OpenAI Agents SDK and an interactive browser
modal. Configure ``OPENAI_API_KEY`` in the Pipe valves (or in the Open WebUI
process environment), then select this Pipe as the chat model.

The ``execute`` event deliberately runs trusted JavaScript in the Open WebUI
page. Review it before installing this Function.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from agents import (
    Agent,
    OpenAIProvider,
    RunConfig,
    RunContextWrapper,
    Runner,
    function_tool,
)
from pydantic import BaseModel, Field


EventCall = Callable[[dict[str, Any]], Awaitable[Any]]


class ChoiceQuestion(BaseModel):
    """One question shown in the modal."""

    question: str = Field(min_length=1, description="The question shown to the user")
    options: list[str] = Field(
        min_length=2,
        description="Two or more short, mutually exclusive suggested answers",
    )


@dataclass
class OpenWebUIContext:
    event_call: EventCall


def _question_dialog_javascript(questions: list[dict[str, Any]]) -> str:
    """Return JS that blocks the chat and resolves with all submitted answers."""
    payload = json.dumps(questions, ensure_ascii=True).replace("<", "\\u003c")
    return f"""
const questions = {payload};
const oldOverlay = document.getElementById('agents-multichoice-overlay');
if (oldOverlay) oldOverlay.remove();

const overlay = document.createElement('div');
overlay.id = 'agents-multichoice-overlay';
overlay.setAttribute('role', 'dialog');
overlay.setAttribute('aria-modal', 'true');
overlay.setAttribute('aria-labelledby', 'agents-multichoice-title');
overlay.style.cssText = `position:fixed;inset:0;z-index:2147483647;
  background:rgba(0,0,0,.64);display:flex;align-items:center;
  justify-content:center;padding:20px;box-sizing:border-box`;

const panel = document.createElement('form');
panel.style.cssText = `width:min(680px,100%);max-height:90vh;overflow:auto;
  background:var(--color-gray-900,#18181b);color:var(--color-gray-100,#fafafa);
  border:1px solid var(--color-gray-700,#3f3f46);border-radius:14px;
  padding:22px;box-shadow:0 20px 50px rgba(0,0,0,.45);font:inherit`;

const title = document.createElement('h2');
title.id = 'agents-multichoice-title';
title.textContent = 'A few questions before I continue';
title.style.cssText = 'font-size:1.2rem;font-weight:650;margin:0 0 6px';
panel.appendChild(title);
const hint = document.createElement('p');
hint.textContent = 'Choose one answer per question, or select Custom answer.';
hint.style.cssText = 'opacity:.75;margin:0 0 18px';
panel.appendChild(hint);

const groups = [];
questions.forEach((item, questionIndex) => {{
  const fieldset = document.createElement('fieldset');
  fieldset.style.cssText = 'border:0;padding:0;margin:0 0 20px';
  const legend = document.createElement('legend');
  legend.textContent = `${{questionIndex + 1}}. ${{item.question}}`;
  legend.style.cssText = 'font-weight:600;margin-bottom:9px';
  fieldset.appendChild(legend);

  const customInput = document.createElement('input');
  customInput.type = 'text';
  customInput.placeholder = 'Type your own answer';
  customInput.style.cssText = `display:none;width:100%;box-sizing:border-box;
    margin:7px 0 0 27px;padding:9px 11px;border-radius:8px;border:1px solid #71717a;
    background:#27272a;color:#fafafa`;

  [...item.options, 'Custom answer'].forEach((option, optionIndex) => {{
    const label = document.createElement('label');
    label.style.cssText = 'display:flex;gap:9px;align-items:flex-start;padding:5px 0;cursor:pointer';
    const radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = `agents-question-${{questionIndex}}`;
    radio.value = optionIndex === item.options.length ? '__custom__' : option;
    radio.required = true;
    radio.addEventListener('change', () => {{
      customInput.style.display = radio.value === '__custom__' ? 'block' : 'none';
      customInput.required = radio.value === '__custom__';
      if (customInput.required) customInput.focus();
    }});
    const text = document.createElement('span');
    text.textContent = option;
    label.append(radio, text);
    fieldset.appendChild(label);
  }});
  fieldset.appendChild(customInput);
  panel.appendChild(fieldset);
  groups.push({{ item, fieldset, customInput }});
}});

const submit = document.createElement('button');
submit.type = 'submit';
submit.textContent = 'Submit answers';
submit.style.cssText = `border:0;border-radius:9px;padding:10px 16px;font-weight:650;
  background:#2563eb;color:white;cursor:pointer`;
panel.appendChild(submit);
overlay.appendChild(panel);
document.body.appendChild(overlay);

// The overlay intercepts pointers; this capture handler also prevents global
// composer shortcuts from sending another request while the tool is waiting.
const blockOutsideKeys = (event) => {{
  if (!overlay.contains(event.target)) {{ event.preventDefault(); event.stopImmediatePropagation(); }}
  if (event.key === 'Escape') {{ event.preventDefault(); event.stopImmediatePropagation(); }}
}};
document.addEventListener('keydown', blockOutsideKeys, true);
overlay.addEventListener('click', (event) => {{ if (event.target === overlay) event.preventDefault(); }});

try {{
  return await new Promise((resolve) => {{
    panel.addEventListener('submit', (event) => {{
      event.preventDefault();
      if (!panel.reportValidity()) return;
      const answers = groups.map((group, index) => {{
        const selected = group.fieldset.querySelector(`input[name="agents-question-${{index}}"]:checked`);
        return {{
          question: group.item.question,
          answer: selected.value === '__custom__' ? group.customInput.value.trim() : selected.value
        }};
      }});
      resolve({{ answers }});
    }});
    panel.querySelector('input[type="radio"]')?.focus();
  }});
}} finally {{
  document.removeEventListener('keydown', blockOutsideKeys, true);
  overlay.remove();
}}
""".strip()


class OpenWebUIQuestionAgent:
    """Build and run the SDK agent with the browser question tool."""

    def __init__(
        self, *, model: str, api_key: str, context: OpenWebUIContext
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.context = context

    def build(self) -> Agent[OpenWebUIContext]:
        @function_tool
        async def multichoise_user_question(
            wrapper: RunContextWrapper[OpenWebUIContext],
            questions: list[ChoiceQuestion],
        ) -> str:
            """Ask the user multiple choice questions and wait for all answers.

            Use this when missing preferences or requirements would materially
            affect the answer. Supply all questions in one call. Every question
            automatically includes a custom free-text answer in the UI.
            """
            if not questions:
                return "No questions were supplied."
            event = {
                "type": "execute",
                "data": {
                    "code": _question_dialog_javascript(
                        [question.model_dump() for question in questions]
                    )
                },
            }
            result = await wrapper.context.event_call(event)
            return json.dumps(result, ensure_ascii=False)

        instructions = (
            "You are a helpful assistant in Open WebUI. Answer the user's request. "
            "When important requirements are ambiguous, call "
            "multichoise_user_question once with all necessary questions, then use "
            "the returned answers to complete the original request. Do not ask those "
            "questions again in ordinary chat text.\n\n"
            "Environment:\n"
            "The question tool opens a blocking browser modal. Each question has "
            "suggested choices and an automatic custom-answer field."
        )
        return Agent(
            name="OpenWebUI interactive assistant",
            instructions=instructions,
            model=self.model,
            tools=[multichoise_user_question],
        )

    async def run(self, prompt: str) -> Any:
        return await Runner.run(
            self.build(),
            prompt,
            context=self.context,
            run_config=RunConfig(
                model_provider=OpenAIProvider(api_key=self.api_key),
                workflow_name="OpenWebUI interactive question pipe",
            ),
        )


def _latest_user_text(body: dict[str, Any]) -> str:
    messages = body.get("messages")
    if not isinstance(messages, list):
        raise ValueError("body.messages must be a list")
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
    raise ValueError("No non-empty user message was found")


class Pipe:
    class Valves(BaseModel):
        OPENAI_API_KEY: str = Field(
            default="", description="OpenAI API key; environment fallback is supported"
        )
        MODEL: str = Field(default="gpt-5-mini", description="OpenAI model name")

    def __init__(self) -> None:
        self.valves = self.Valves()

    def pipes(self) -> list[dict[str, str]]:
        return [{"id": "interactive-agent", "name": "Interactive OpenAI Agent"}]

    async def pipe(
        self,
        body: dict[str, Any],
        __event_call__: EventCall | None = None,
    ) -> str:
        if __event_call__ is None:
            raise RuntimeError("This Pipe requires Open WebUI's __event_call__ callback")

        api_key = self.valves.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("Configure OPENAI_API_KEY in the Pipe valves")

        builder = OpenWebUIQuestionAgent(
            model=self.valves.MODEL,
            api_key=api_key,
            context=OpenWebUIContext(event_call=__event_call__),
        )
        result = await builder.run(_latest_user_text(body))
        return str(result.final_output)
