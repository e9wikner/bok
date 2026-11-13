"""Edit the company's accounting instructions one section at a time.

The agent in a thread learns something general ("search the 2440 credit, not
the counterparty name") and must be able to keep it for next time. Handing it
the whole document to rewrite invites it to drop what it did not mean to, so
the tool takes one section: a heading and its text. The section with that
heading is replaced; a new heading is appended. Every call is a new immutable
version (`AgentInstructionRepository`), so a human can read and restore any
earlier one.
"""

import re
from typing import Optional

from domain.validation import ValidationError
from repositories.agent_instruction_repo import AgentInstructionRepository

SCOPE = "accounting_company"
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def _heading(line: str) -> Optional[tuple[int, str]]:
    match = _HEADING.match(line)
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip().casefold()


def merge_section(document: str, rubrik: str, text: str) -> str:
    """Return ``document`` with the section headed ``rubrik`` set to ``text``.

    A section runs from its heading to the next heading of the same or a
    higher level. ``rubrik`` is given with its ``#`` marks; if no section
    has that title it is appended at the end. Lines inside a code fence are
    never read as headings.
    """
    wanted = _heading(rubrik.strip())
    if wanted is None:
        raise ValidationError(
            code="invalid_heading",
            message="rubrik must be a Markdown heading, e.g. '### Betalning'",
            details=rubrik,
        )
    level, title = wanted
    block = f"{rubrik.strip()}\n\n{text.strip()}\n"

    lines = document.split("\n")
    start = end = None
    in_fence = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        found = _heading(line)
        if found is None:
            continue
        if start is None:
            if found == (level, title):
                start = index
        elif found[0] <= level:
            end = index
            break
    if start is None:
        return document.rstrip("\n") + "\n\n" + block
    tail = "\n".join(lines[end:]) if end is not None else ""
    head = "\n".join(lines[:start]).rstrip("\n")
    parts = [p for p in (head, block.rstrip("\n"), tail) if p]
    return "\n\n".join(parts).rstrip("\n") + "\n"


def update_section(
    *, rubrik: str, text: str, change_summary: str, actor: str
) -> dict:
    current = AgentInstructionRepository.get_active(SCOPE)
    merged = merge_section(current["content_markdown"], rubrik, text)
    if merged == current["content_markdown"]:
        return {"changed": False, "version": current["version"]}
    saved = AgentInstructionRepository.update(
        scope=SCOPE,
        content_markdown=merged,
        change_summary=change_summary,
        created_by=actor,
    )
    return {"changed": True, "version": saved["version"], "rubrik": rubrik.strip()}
