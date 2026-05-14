"""Read-only system instructions for agents.

System instructions contain critical, stable documentation about how the system
works (SIE4 import, API behavior, accounting principles). These are read from
version-controlled files and cannot be modified by agents.

Company-specific instructions are stored separately and can be updated by agents.
"""

import os
from typing import Dict, List, Optional

# Base directory for system instruction documents
DOCS_TO_AGENT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "to_agent"
)

# Ordered list of system instruction files
# These are read-only and contain system-critical information
SYSTEM_INSTRUCTION_FILES: List[tuple] = [
    ("01_drift_och_atkomst.md", "Drift och åtkomst"),
    ("02_bokforingsprocess.md", "Bokföringsprocess"),
    ("03_bokforingsinstruktion.md", "Bokföringsinstruktion"),
    ("04_sie4_import_och_rakenskapsar.md", "SIE4-import och räkenskapsår"),
]


def get_system_instructions() -> Dict:
    """Return all system instructions as a combined document.
    
    These instructions are read-only and contain system-critical information
    that agents should not be able to modify.
    """
    sections = []
    
    for filename, title in SYSTEM_INSTRUCTION_FILES:
        filepath = os.path.join(DOCS_TO_AGENT_DIR, filename)
        content = _read_file(filepath)
        if content:
            sections.append(f"# {title}\n\n{content}")
    
    combined_content = "\n\n---\n\n".join(sections)
    
    return {
        "scope": "system",
        "content_markdown": combined_content,
        "source": "version_controlled_files",
        "files": [f[0] for f in SYSTEM_INSTRUCTION_FILES],
        "is_editable": False,
        "description": "Systeminstruktioner är skrivskyddade och innehåller kritisk information om hur systemet fungerar."
    }


def get_accounting_system_instructions() -> Dict:
    """Return system instructions specifically for accounting agent."""
    return get_system_instructions()


def get_invoicing_system_instructions() -> Dict:
    """Return system instructions specifically for invoicing agent.
    
    Currently returns the same as accounting, but can be customized.
    """
    # For now, invoicing uses a subset or the same system instructions
    # In the future, this could load different files
    return get_system_instructions()


def _read_file(filepath: str) -> Optional[str]:
    """Read a file and return its contents, or None if not found."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return None
    except Exception as e:
        return f"[Fel vid läsning av fil: {str(e)}]"


def list_available_files() -> List[Dict]:
    """List all available system instruction files with their status."""
    result = []
    for filename, title in SYSTEM_INSTRUCTION_FILES:
        filepath = os.path.join(DOCS_TO_AGENT_DIR, filename)
        exists = os.path.exists(filepath)
        result.append({
            "filename": filename,
            "title": title,
            "exists": exists,
            "path": filepath if exists else None
        })
    return result
