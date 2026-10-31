"""Grounded answer generation (step 9): call the LLM, validate its JSON with pydantic."""
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

import config
from app import llm
from app.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from app.retrieval.context_builder import ContextChunk

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


class InvalidAnswerError(RuntimeError):
    """The LLM did not return schema-valid JSON, even after the retry."""


class LLMConflict(BaseModel):
    claim: str
    chunk_id: str


class LLMAnswer(BaseModel):
    """What the LLM must return (see SYSTEM_PROMPT)."""

    status: Literal["answered", "conflict", "needs_clarification", "not_found"]
    answer: str = ""
    conflicts: list[LLMConflict] = Field(default_factory=list)
    clarifying_question: str | None = None


def parse_answer(raw: str) -> LLMAnswer:
    """Validate a raw reply; tolerates ```json fences around the object."""
    return LLMAnswer.model_validate_json(_FENCE.sub("", raw.strip()))


def generate_answer(
    question: str,
    context: list[ContextChunk],
    conflict_hints: list[str],
    feedback: str | None = None,
) -> LLMAnswer:
    """Ask the LLM; on invalid JSON retry LLM_JSON_RETRIES times with the validation error."""
    prompt = build_user_prompt(question, context, conflict_hints, feedback)
    for _ in range(1 + config.LLM_JSON_RETRIES):
        raw = llm.generate(prompt, system=SYSTEM_PROMPT, json_mode=True)
        try:
            return parse_answer(raw)
        except ValidationError as exc:
            first = exc.errors()[0]
            prompt += (
                f"\nYour previous reply was not valid JSON for the schema "
                f"({first['type']} at {'.'.join(map(str, first['loc'])) or 'root'}). "
                "Reply again with the JSON object only."
            )
    raise InvalidAnswerError("LLM reply was not valid JSON after retry")
