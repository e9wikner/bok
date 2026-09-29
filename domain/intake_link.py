"""Domain types for `flode-underlag` (SPEC-flode-underlag.md §5, §6).

`IntakeLinkBasis` is one row of `intake_link_basis` (migration 032): why an
underlag was linked to an already posted voucher after the fact -- the
interpretation the server compared and, for `basis = "decision"`, the
answered decision. `VoucherSourceReference` is one row of
`voucher_source_references` (D2): a difference voucher (A-121) that refers
to the receipt through the voucher carrying the link (A-118).

Both are frozen: the tables are append-only in three layers, and a value
that cannot be changed in memory is the first of them a reader meets.
`LinkResult` is §6.6's answer, the same for the tool and the route.

No logic here beyond `to_dict`. The checks live in
`services/intake_link.py`; the SQL in `repositories/intake_link_repo.py`.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

# §6.4: exactly one of two. `exact_match` without a human, `decision` with
# an answered decision about the source.
LinkBasis = Literal["exact_match", "decision"]


@dataclass(frozen=True)
class IntakeLinkBasis:
    """One `intake_link_basis` row (§5)."""

    intake_source_id: str
    voucher_id: str
    basis: LinkBasis
    interpretation_id: str
    actor: str
    decision_id: Optional[str] = None
    agent_run_id: Optional[str] = None
    thread_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    #: The `voucher_intake_sources` row this is the basis of (migration
    #: 034). Set by the service once the link is written.
    link_id: Optional[str] = None


# underlag-ersatt: an unlink is either a logged-in human's (the route with a
# JWT) or rests on an answered decision about the underlag.
UnlinkBasis = Literal["human", "decision"]


@dataclass(frozen=True)
class IntakeUnlink:
    """One `voucher_intake_unlinks` row (migration 035): *link_id* no
    longer holds. The link row itself stays."""

    link_id: str
    intake_source_id: str
    voucher_id: str
    basis: UnlinkBasis
    reason: str
    actor: str
    decision_id: Optional[str] = None
    agent_run_id: Optional[str] = None
    thread_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class UnlinkResult:
    """What `koppla_bort_underlag` and `POST /intake/{id}/unlink` answer.
    `orphaned_references` are the vouchers (numbers) booked on the underlag
    through this link (D2, A-121 via A-118): their reference stands, but
    whether they should be corrected is a human's call;
    `missing_attachments` is the counter after the unlink."""

    source_id: str
    voucher_id: str
    voucher_number: Optional[str]
    link_id: str
    basis: UnlinkBasis
    decision_id: Optional[str]
    reason: str
    replayed: bool
    orphaned_references: List[str]
    missing_attachments: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VoucherSourceReference:
    """One `voucher_source_references` row (§5, D2): *voucher_id* has its
    underlag through *via_voucher_id*'s link to *intake_source_id*."""

    voucher_id: str
    intake_source_id: str
    via_voucher_id: str
    decision_id: str
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class LinkResult:
    """§6.6: what `koppla_underlag` and `POST /intake/{id}/link` answer.
    `missing_attachments` is the counter after the link."""

    source_id: str
    voucher_id: str
    voucher_number: Optional[str]
    basis: LinkBasis
    interpretation_id: str
    decision_id: Optional[str]
    replayed: bool
    missing_attachments: int

    def to_dict(self) -> Dict[str, Any]:
        """In §6.6's key order."""
        return asdict(self)
