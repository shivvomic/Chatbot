"""One parser per format. Each returns a list of Section dicts: {section, page, text}.

`section` is the heading, `text` the body without the heading, `page` is the page the
section starts on (PDF only; None for other formats). Document text is data, never parsed
as instructions.
"""
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple, TypedDict

import pymupdf
from bs4 import BeautifulSoup

import config


class Section(TypedDict):
    section: str
    page: int | None
    text: str


class ParsedDocument(NamedTuple):
    meta: dict  # one entry of documents_metadata.json (or of the uploads manifest)
    sections: list[Section]


_NUMBERED_HEADING = re.compile(r"^\d+\.\s+\S")  # PDF headings look like "2. Signing In"
_PAGE_MARKER = re.compile(r"^Page \d+$")  # second line of every PDF page header
_UNDERLINE = re.compile(r"^(=+|-+)$")  # TXT headings are underlined with --- (title with ===)
_NOISE_TAGS = ["nav", "footer", "header", "aside", "script", "style"]
FALLBACK_SECTION = "Document"  # heading used when a file has no recognisable headings


def _join_lines(lines: list[str]) -> str:
    """Re-flow hard-wrapped lines: blank line = paragraph break, otherwise join with a space."""
    paragraphs, current = [], []
    for line in lines:
        if line.strip():
            current.append(line.strip())
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs)


def _section(heading: str, lines: list[str], page: int | None = None) -> Section:
    return {"section": heading, "page": page, "text": _join_lines(lines)}


def parse_pdf(path: Path) -> list[Section]:
    """Numbered headings ('1. Overview'); drops the running header + 'Page N' on each page.

    A PDF without numbered headings falls back to one section per page ("Page N").
    """
    sections: list[Section] = []
    current: tuple[str, int, list[str]] | None = None  # (heading, start page, body lines)
    pages: list[list[str]] = []
    with pymupdf.open(path) as pdf:
        for page in pdf:
            lines = page.get_text().splitlines()
            if len(lines) > 1 and _PAGE_MARKER.match(lines[1].strip()):
                lines = lines[2:]  # running header line + "Page N"
            pages.append(lines)
            # A numbered line closes the current section and opens a new one on this page;
            # any other line belongs to the open section (sections may span pages).
            for line in lines:
                if _NUMBERED_HEADING.match(line.strip()):
                    if current:
                        sections.append(_section(current[0], current[2], current[1]))
                    current = (line.strip(), page.number + 1, [])
                elif current:  # text before the first heading is the title block: skipped
                    current[2].append(line)
    if current:
        sections.append(_section(current[0], current[2], current[1]))
    if not sections:
        sections = [_section(f"Page {n}", lines, n) for n, lines in enumerate(pages, start=1)]
    return [s for s in sections if s["text"]]


def parse_html(path: Path) -> list[Section]:
    """One section per <h2>; nav/footer/header/aside/script/style are dropped first."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    sections: list[Section] = []
    for h2 in soup.find_all("h2"):
        body = []
        for sibling in h2.find_next_siblings():  # everything up to the next h1/h2
            if sibling.name in ("h1", "h2"):
                break
            body.append(sibling.get_text(" ", strip=True))
        sections.append({"section": h2.get_text(" ", strip=True), "page": None,
                         "text": "\n\n".join(t for t in body if t)})
    if not sections and soup.body:  # no <h2>: keep the whole visible body as one section
        sections = [{"section": FALLBACK_SECTION, "page": None,
                     "text": soup.body.get_text("\n", strip=True)}]
    return [s for s in sections if s["text"]]


def parse_markdown(path: Path) -> list[Section]:
    """Split on '## ' headings; YAML front matter and the '# ' title are removed."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL)
    sections: list[Section] = []
    heading: str | None = None
    lines: list[str] = []
    in_fence = False  # '## ' inside a ``` code block is not a heading
    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            if heading:
                sections.append({"section": heading, "page": None, "text": "\n".join(lines).strip()})
            heading, lines = line[3:].strip(), []
        elif heading:
            lines.append(line)
    if heading:
        sections.append({"section": heading, "page": None, "text": "\n".join(lines).strip()})
    if not sections:  # no '## ' headings: whole file minus a leading '# ' title
        body = re.sub(r"\A\s*# .*\n", "", text).strip()
        sections = [{"section": FALLBACK_SECTION, "page": None, "text": body}]
    return [s for s in sections if s["text"]]


def parse_txt(path: Path) -> list[Section]:
    """Headings are lines underlined with '---'; the '===' underlined title block is skipped."""
    lines = path.read_text(encoding="utf-8").splitlines()
    sections: list[Section] = []
    heading: str | None = None
    body: list[str] = []
    i = 0
    while i < len(lines):
        underline = lines[i + 1].strip() if i + 1 < len(lines) else ""
        is_heading = (
            lines[i].strip() and _UNDERLINE.match(underline) and len(underline) >= 3 and underline[0] == "-"
        )
        if is_heading:
            if heading:
                sections.append(_section(heading, body))
            heading, body = lines[i].strip(), []
            i += 2  # skip the heading and its underline
            continue
        if heading:
            body.append(lines[i])
        i += 1
    if heading:
        sections.append(_section(heading, body))
    if not sections:  # plain text without headings
        sections = [_section(FALLBACK_SECTION, lines)]
    return [s for s in sections if s["text"]]


# Keys are the `format` values used in documents_metadata.json.
PARSERS: dict[str, Callable[[Path], list[Section]]] = {
    "pdf": parse_pdf,
    "html": parse_html,
    "md": parse_markdown,
    "txt": parse_txt,
}


def load_documents(
    docs_dir: Path = config.DOCS_DIR, metadata_path: Path = config.METADATA_PATH
) -> list[ParsedDocument]:
    """Parse every document listed in a metadata manifest (joined by its `file` path)."""
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return [ParsedDocument(m, PARSERS[m["format"]](docs_dir / m["file"])) for m in metadata]


def load_all_documents() -> list[ParsedDocument]:
    """The dataset documents plus anything uploaded through the API (data/uploads/)."""
    docs = load_documents()
    if config.UPLOADS_METADATA_PATH.exists():
        docs += load_documents(config.UPLOADS_DIR, config.UPLOADS_METADATA_PATH)
    return docs
