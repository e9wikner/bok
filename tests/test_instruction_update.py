"""`uppdatera_instruktioner`: one section of the company instructions at a time."""

import pytest

from domain.validation import ValidationError
from services.instruction_update import merge_section

DOC = """# Bokföringsinstruktioner

## Kontoutdrag som underlag

### Betalning

gammal text

### Annat

kvar

## Utlägg

oförändrat
"""


def test_replaces_only_the_named_section():
    out = merge_section(DOC, "### Betalning", "ny text")
    assert "ny text" in out and "gammal text" not in out
    assert "### Annat\n\nkvar" in out and "## Utlägg\n\noförändrat" in out


def test_title_match_ignores_case_and_appends_when_missing():
    assert "gammal" not in merge_section(DOC, "### betalning", "x")
    out = merge_section(DOC, "### Ny rubrik", "text")
    assert out.startswith(DOC.rstrip("\n")) and out.endswith("### Ny rubrik\n\ntext\n")


def test_same_text_is_a_no_op():
    once = merge_section(DOC, "### Betalning", "ny")
    assert merge_section(once, "### Betalning", "ny") == once


def test_heading_inside_a_code_fence_is_not_a_section():
    doc = "# D\n\n```\n### Betalning\n```\n"
    assert merge_section(doc, "### Betalning", "x").count("### Betalning") == 2


def test_rubrik_must_be_a_heading():
    with pytest.raises(ValidationError):
        merge_section(DOC, "Betalning", "x")
