"""Repository for versioned agent instruction documents."""

from datetime import datetime
from typing import Dict, List, Optional
import uuid

from db.database import db


DEFAULT_ACCOUNTING_INSTRUCTIONS = """# Bokföringsinstruktioner

## Måste alltid följas
- Bokför enligt dubbel bokföring: debet måste alltid vara lika med kredit.
- Använd endast aktiva konton i kontoplanen.
- Bokför inte i låsta perioder.
- Ange tydlig verifikationstext som beskriver affärshändelsen.

## Agentens arbetssätt
- Läs dessa instruktioner innan bokföring.
- Läs tidigare postade verifikationer och korrigeringar via API:t när instruktionerna behöver förbättras.
- Bokför direkt när underlaget är tillräckligt tydligt.
- Uppdatera instruktionerna med generell vägledning när mänskliga korrigeringar visar återkommande mönster.

## Standardprinciper
- Bankkonto är normalt 1920 om inget annat framgår.
- Ingående moms bokförs normalt på 2640 när underlaget visar avdragsgill moms.
- Utgående moms bokförs normalt på 2610 vid försäljning med 25 procent moms.
- Använd inte procentuell fördelning mellan konton om historiken visar att en rad är fast avgift och en annan rad varierar.

## Korrigeringar
- Postade verifikationer ändras inte direkt.
- Fel rättas med korrigeringsverifikation i B-serien.
- Läs korrigeringar som stark signal för hur framtida liknande händelser bör bokföras.
"""


class AgentInstructionRepository:
    """Manage active instruction documents and immutable versions."""

    @staticmethod
    def get_active(scope: str) -> Dict:
        """Return the active instruction document, creating a default if needed."""
        document = AgentInstructionRepository._get_document(scope)
        if not document:
            return AgentInstructionRepository.update(
                scope=scope,
                content_markdown=DEFAULT_ACCOUNTING_INSTRUCTIONS,
                change_summary="Initial accounting instructions",
                created_by="system",
            )

        version = AgentInstructionRepository._get_version(document["active_version_id"])
        return AgentInstructionRepository._response(document, version)

    @staticmethod
    def update(
        scope: str,
        content_markdown: str,
        change_summary: Optional[str] = None,
        created_by: str = "system",
    ) -> Dict:
        """Create a new version and make it active."""
        now = datetime.now()
        document = AgentInstructionRepository._get_document(scope)

        with db.transaction():
            if not document:
                document_id = str(uuid.uuid4())
                db.execute(
                    """INSERT INTO agent_instruction_documents
                       (id, scope, created_at, updated_at)
                       VALUES (?, ?, ?, ?)""",
                    (document_id, scope, now, now),
                )
                version_number = 1
            else:
                document_id = document["id"]
                version_number = AgentInstructionRepository._next_version(document_id)

            version_id = str(uuid.uuid4())
            db.execute(
                """INSERT INTO agent_instruction_versions
                   (id, document_id, version, content_markdown, change_summary, created_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    version_id,
                    document_id,
                    version_number,
                    content_markdown,
                    change_summary,
                    created_by,
                    now,
                ),
            )
            db.execute(
                """UPDATE agent_instruction_documents
                   SET active_version_id = ?, updated_at = ?
                   WHERE id = ?""",
                (version_id, now, document_id),
            )

        document = AgentInstructionRepository._get_document(scope)
        version = AgentInstructionRepository._get_version(version_id)
        return AgentInstructionRepository._response(document, version)

    @staticmethod
    def list_versions(scope: str) -> List[Dict]:
        """List versions for a scope, newest first."""
        document = AgentInstructionRepository._get_document(scope)
        if not document:
            AgentInstructionRepository.get_active(scope)
            document = AgentInstructionRepository._get_document(scope)

        rows = db.execute(
            """SELECT * FROM agent_instruction_versions
               WHERE document_id = ?
               ORDER BY version DESC""",
            (document["id"],),
        ).fetchall()
        return [AgentInstructionRepository._version_response(row) for row in rows]

    @staticmethod
    def _get_document(scope: str):
        return db.execute(
            "SELECT * FROM agent_instruction_documents WHERE scope = ? LIMIT 1",
            (scope,),
        ).fetchone()

    @staticmethod
    def _get_version(version_id: str):
        return db.execute(
            "SELECT * FROM agent_instruction_versions WHERE id = ? LIMIT 1",
            (version_id,),
        ).fetchone()

    @staticmethod
    def _next_version(document_id: str) -> int:
        row = db.execute(
            "SELECT MAX(version) AS max_version FROM agent_instruction_versions WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        return int(row["max_version"] or 0) + 1

    @staticmethod
    def _response(document, version) -> Dict:
        return {
            "id": document["id"],
            "scope": document["scope"],
            "active_version_id": document["active_version_id"],
            "updated_at": document["updated_at"],
            **AgentInstructionRepository._version_response(version),
        }

    @staticmethod
    def _version_response(version) -> Dict:
        return {
            "version_id": version["id"],
            "version": version["version"],
            "content_markdown": version["content_markdown"],
            "change_summary": version["change_summary"],
            "created_by": version["created_by"],
            "created_at": version["created_at"],
        }
