"""Answer verification (step 11).

* Every cited chunk_id must be in the context; unknown ids are stripped.
* Sentences without a valid citation are removed.
* The answer, conflict claims and clarifying question are scanned for PII / secret patterns
  and planted sensitive values.
The pipeline regenerates once on failure, then falls back to not_found.
"""
import re
from dataclasses import dataclass, field

from app.generation.answer_generator import LLMAnswer
from app.guardrails.output_filter import find_leaks

_CITATION = re.compile(r"\[([^\[\]]+)\]")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_LEADING_CITES = re.compile(r"^((?:\s*\[[^\[\]]+\])+)\s*")
_CITED_STATUSES = ("answered", "conflict")  # statuses whose answer must be grounded


@dataclass
class Verification:
    answer: str  # cleaned answer text
    cited_ids: list[str]  # valid citations, in order of first use
    kept: int  # sentences kept
    total: int  # sentences before cleaning
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def split_sentences(text: str) -> list[str]:
    """Sentences, with a citation that follows a full stop ("x. [id]") kept on its sentence."""
    pieces = [p for p in _SENTENCE_END.split(text.strip()) if p]
    sentences: list[str] = []
    for piece in pieces:
        lead = _LEADING_CITES.match(piece)
        if lead and sentences:
            sentences[-1] += " " + lead.group(1).strip()
            piece = piece[lead.end():]
        if piece.strip():
            sentences.append(piece.strip())
    return sentences


def _ids_in(group: str) -> list[str]:
    """'D01-s2-c1, D02-s2-c1' -> both ids."""
    return [i.strip() for i in re.split(r"[,;]", group) if i.strip()]


def _clean_sentence(sentence: str, valid: set[str]) -> tuple[str, list[str]]:
    """Drop unknown ids from a sentence; returns (sentence, valid ids it cites)."""
    cited: list[str] = []

    def keep_valid(match: re.Match) -> str:
        ids = [i for i in _ids_in(match.group(1)) if i in valid]
        cited.extend(ids)
        return f"[{', '.join(ids)}]" if ids else ""

    return re.sub(r"\s+", " ", _CITATION.sub(keep_valid, sentence)).strip(), cited


def verify(result: LLMAnswer, context_ids: set[str]) -> Verification:
    """Clean the answer and list everything that is still wrong with it."""
    sentences = split_sentences(result.answer)
    kept_sentences: list[str] = []
    cited: list[str] = []
    # Keep a sentence only if it cites at least one chunk the model was actually shown.
    for sentence in sentences:
        cleaned, ids = _clean_sentence(sentence, context_ids)
        if ids or result.status not in _CITED_STATUSES:
            kept_sentences.append(cleaned)
            cited += ids
    report = Verification(
        answer=" ".join(kept_sentences), cited_ids=list(dict.fromkeys(cited)),
        kept=len(kept_sentences), total=len(sentences),
    )
    if result.status in _CITED_STATUSES and not report.cited_ids:
        report.problems.append("the answer had no sentence with a valid [chunk_id] citation")
    # Scan the raw reply (before uncited sentences were dropped) so nothing sensitive slips through.
    scanned = " ".join([result.answer, result.clarifying_question or "", *(c.claim for c in result.conflicts)])
    leaks = find_leaks(scanned)
    if leaks:
        report.problems.append(f"the reply contained sensitive content ({', '.join(leaks)})")
    return report
