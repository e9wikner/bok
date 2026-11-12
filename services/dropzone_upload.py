"""The dropzone from the browser: put a file in the folder the SMB share serves.

The web view of the dropzone is not a second intake path. An upload is
written into the same directory tree the ``Bokforing`` share exports, into
one of the folders the scanner already routes (``services/dropzone.py``), and
the scanner picks it up on its next tick exactly as it would a file copied in
over SMB: same classification by folder, same ``_Inläst``/``_Problem``
handling, same agent pass. A file dropped in the browser and one dropped in
Finder are indistinguishable afterwards, which is the point.

Only the folders listed by :func:`drop_targets` can be written to. The caller
names a folder from that list, never a path, so nothing here can be steered
outside the dropzone or into ``_Inläst``/``_Problem``.

The file is written under a ``.part`` name (which the scanner ignores) and
renamed into place, so the scanner never sees a half-written file.

The folder is the only classification: there is no comment field. The web
view shows the share's folders as they are on disk, so what a file becomes
is decided by where it is dropped, as on the share.
"""

import hashlib
import logging
import os
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from domain.types import IntakeSourceType
from repositories.account_repo import AccountRepository
from services.bank_inputs import BankInputError, is_statement_account
from services.dropzone import (
    INGESTED_DIR_NAME,
    PROBLEM_DIR_NAME,
    PROBLEM_NOTE_SUFFIX,
    RESERVED_DIR_NAMES,
    SIE4_EXTENSIONS,
    STATEMENT_FOLDERS,
    DropzoneScanner,
    _is_ignored,
    _is_sidecar,
    folder_key,
    get_scanner,
    statement_account_code,
)

logger = logging.getLogger(__name__)

MAX_DROP_BYTES = 10 * 1024 * 1024
#: Files per upload request.
MAX_FILES_PER_DROP = 50
#: How many problem and recently read-in files the listing returns.
LISTING_LIMIT = 50

#: The type folders, in the order the share's README lists them. The folder
#: name on disk wins if it exists (an NFD spelling from a Mac, say).
TYPE_FOLDERS: tuple[tuple[str, IntakeSourceType, str], ...] = (
    ("Kvitton", IntakeSourceType.RECEIPT, "Kvitton"),
    ("Leverantörsfakturor", IntakeSourceType.SUPPLIER_INVOICE, "Leverantörsfakturor"),
    ("Kundfakturor", IntakeSourceType.CUSTOMER_INVOICE, "Kundfakturor"),
    ("Utlägg", IntakeSourceType.REIMBURSEMENT, "Utlägg"),
    ("Övrigt", IntakeSourceType.OTHER, "Övrigt"),
)
STATEMENT_ROOT_NAME = "Kontoutdrag"
SIE4_FOLDER_NAME = "SIE4-import"


class DropzoneUploadError(Exception):
    """An upload the dropzone cannot take. ``status`` is the HTTP status."""

    def __init__(self, message: str, code: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


@dataclass(frozen=True)
class DropTarget:
    """A folder a file can be dropped into from the browser."""

    #: Path relative to the dropzone root, with ``/``. The folder's identity.
    folder: str
    label: str
    kind: str  # "voucher_source", "bank_input" or "sie4_import"
    source_type: str | None = None
    account_code: str | None = None
    account_name: str | None = None

    def as_dict(self, pending: int) -> dict:
        return {
            "folder": self.folder,
            "label": self.label,
            "kind": self.kind,
            "source_type": self.source_type,
            "account_code": self.account_code,
            "account_name": self.account_name,
            "pending_count": pending,
        }


def _existing_child(parent: Path, name: str) -> Path:
    """The child of ``parent`` named ``name``, in its on-disk spelling."""
    wanted = folder_key(name)
    try:
        for entry in parent.iterdir():
            if (
                entry.is_dir()
                and not entry.is_symlink()
                and folder_key(entry.name) == wanted
            ):
                return entry
    except OSError:
        pass
    return parent / name


def drop_targets(scanner: DropzoneScanner | None = None) -> list[DropTarget]:
    """The folders the browser may drop into.

    The share's folders, in the share's layout: the five type folders,
    ``Kontoutdrag`` and ``SIE4-import`` always (created on first drop if
    missing), and every other top-level folder someone made on the share (read
    in without a type, the agent classifies). ``Kontoutdrag`` has no account
    subfolders: a statement's file name says which account it is for.
    """
    root = (scanner or get_scanner()).root
    targets: list[DropTarget] = []
    known = {folder_key(name) for name, _, _ in TYPE_FOLDERS}
    known |= STATEMENT_FOLDERS | RESERVED_DIR_NAMES | {folder_key(SIE4_FOLDER_NAME)}
    for name, source_type, label in TYPE_FOLDERS:
        folder = _existing_child(root, name)
        targets.append(
            DropTarget(
                folder=folder.name,
                label=label,
                kind="voucher_source",
                source_type=source_type.value,
            )
        )

    other: list[Path] = []
    try:
        other = sorted(
            entry
            for entry in root.iterdir()
            if entry.is_dir()
            and not entry.is_symlink()
            and not _is_ignored(entry.name)
            and not entry.name.startswith(".")
            and folder_key(entry.name) not in known
        )
    except OSError:
        pass
    for entry in other:
        name = unicodedata.normalize("NFC", entry.name)
        targets.append(DropTarget(folder=entry.name, label=name, kind="voucher_source"))

    statements = _existing_child(root, STATEMENT_ROOT_NAME)
    targets.append(
        DropTarget(folder=statements.name, label="Kontoutdrag", kind="bank_input")
    )

    sie4 = _existing_child(root, SIE4_FOLDER_NAME)
    targets.append(
        DropTarget(folder=sie4.name, label="SIE4-import", kind="sie4_import")
    )
    return targets


def _target_for(folder: str, scanner: DropzoneScanner) -> DropTarget:
    wanted = folder_key(folder)
    for target in drop_targets(scanner):
        if folder_key(target.folder) == wanted:
            return target
    raise DropzoneUploadError(
        "Mappen finns inte i dropzonen.", "unknown_dropzone_folder", status=404
    )


def _clean_filename(filename: str | None) -> str:
    """The name the file gets in the folder. Only a bare, visible name."""
    name = unicodedata.normalize("NFC", (filename or "").replace("\\", "/"))
    name = name.rsplit("/", 1)[-1].strip()
    if not name or name in {".", ".."} or "\x00" in name:
        raise DropzoneUploadError("Filen saknar namn.", "invalid_filename")
    if name.startswith(".") or _is_ignored(name):
        raise DropzoneUploadError(
            f"Filnamnet {name} hoppas över av dropzonen. Döp om filen.",
            "invalid_filename",
        )
    if _is_sidecar(Path(name)):
        raise DropzoneUploadError(
            "En .txt-fil läses aldrig som underlag i dropzonen.",
            "sidecar_filename",
        )
    if len(name.encode("utf-8")) > 200:
        stem, suffix = os.path.splitext(name)
        name = (
            stem.encode("utf-8")[: 200 - len(suffix.encode("utf-8"))].decode(
                "utf-8", errors="ignore"
            )
            + suffix
        )
    return name


def _check_statement(name: str, content: bytes) -> None:
    """Say at once what the scanner would otherwise put in ``_Problem/``.

    The scanner decides again when it reads the file; this only spares a
    round trip through the share for a name that cannot work.
    """
    if Path(name).suffix.lower() != ".csv":
        raise DropzoneUploadError(
            "Kontoutdrag måste vara CSV-filer.", "not_csv_statement"
        )
    try:
        code = statement_account_code(name, content)
    except BankInputError:
        raise DropzoneUploadError(
            'Börja filnamnet med kontokoden, till exempel "1930 oktober.csv", '
            "så att utdraget hamnar på rätt konto.",
            "statement_account_unknown",
        )
    account = AccountRepository.get(code)
    if not account or not account.active:
        raise DropzoneUploadError(
            f"Konto {code} finns inte i kontoplanen, eller är inaktivt.",
            "statement_account_missing",
        )
    if not is_statement_account(account):
        raise DropzoneUploadError(
            f"Konto {code} är inte ett tillgångs- eller skuldkonto och kan inte "
            "ta emot kontoutdrag.",
            "statement_account_type",
        )


def _free_destination(folder: Path, filename: str) -> Path:
    """Never overwrite a file, nor give a new file someone else's sidecar."""
    stem, suffix = os.path.splitext(filename)
    counter = 1
    while True:
        name = filename if counter == 1 else f"{stem} ({counter}){suffix}"
        candidate = folder / name
        sidecar = folder / f"{Path(name).stem}.txt"
        if not candidate.exists() and not sidecar.exists():
            return candidate
        counter += 1


def drop_file(
    *,
    folder: str,
    filename: str | None,
    content: bytes,
    actor: str,
    scanner: DropzoneScanner | None = None,
) -> dict:
    """Write one file into a dropzone folder for the scanner to pick up."""
    scanner = scanner or get_scanner()
    if not settings.dropzone_enabled:
        raise DropzoneUploadError(
            "Dropzonen är avstängd på servern (DROPZONE_ENABLED), så en fil här "
            "skulle aldrig läsas in.",
            "dropzone_disabled",
            status=409,
        )
    root = scanner.root
    if not root.is_dir():
        raise DropzoneUploadError(
            "Dropzonens mapp finns inte på servern.", "dropzone_dir_missing", status=503
        )

    target = _target_for(folder, scanner)
    name = _clean_filename(filename)
    if not content:
        raise DropzoneUploadError("Filen är tom.", "empty_file")
    if len(content) > MAX_DROP_BYTES:
        raise DropzoneUploadError("Filen är större än 10 MB.", "file_too_large")
    if (
        target.kind == "sie4_import"
        and Path(name).suffix.lower() not in SIE4_EXTENSIONS
    ):
        raise DropzoneUploadError(
            "SIE4-import tar bara emot bokföringsexporter (.se, .si, .sie eller .sie4).",
            "not_sie4",
        )
    if target.kind == "bank_input":
        _check_statement(name, content)

    directory = root.joinpath(*target.folder.split("/"))
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.resolve().is_relative_to(root.resolve()):
        raise DropzoneUploadError(
            "Mappen finns inte i dropzonen.", "unknown_dropzone_folder", status=404
        )

    temporary = directory / f".webb-{uuid.uuid4().hex}.part"
    try:
        temporary.write_bytes(content)
        destination = _free_destination(directory, name)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()

    logger.info(
        "Dropzone upload by %s: %s (%d bytes)",
        actor,
        destination.relative_to(root).as_posix(),
        len(content),
    )
    return {
        "folder": target.folder,
        "filename": destination.name,
        "size_bytes": len(content),
    }


def _file_entry(path: Path, root: Path) -> dict:
    stat = path.stat()
    return {
        "folder": path.parent.relative_to(root).as_posix(),
        "filename": unicodedata.normalize("NFC", path.name),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


#: sha256 per archived file, keyed by path, mtime and size: the listing is
#: polled, and the archive does not change under a file once it is there.
_HASHES: dict[tuple[str, int, int], str] = {}


def _sha256(path: Path) -> str | None:
    try:
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        if key not in _HASHES:
            if len(_HASHES) > 4 * LISTING_LIMIT:
                _HASHES.clear()
            _HASHES[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        return _HASHES[key]
    except OSError:
        return None


def _ingested_outcome(path: Path) -> dict | None:
    """What became of a read-in file, so the view can say it.

    The archive is only a folder; the file is found in the books by its
    sha256, the same way the scanner deduplicates it. An underlag says which
    vouchers it supports now, or the decision it waits on (a fiscal-year card
    for an underlag dated outside every year, the agent's abstention); a
    statement says how many transactions it brought in. ``None`` when the
    file is in neither (an SIE file, or one read in before the database was
    reset).
    """
    from repositories.bank_input_repo import BankInputRepository
    from repositories.decision_repo import DecisionRepository
    from repositories.intake_repo import IntakeRepository
    from repositories.voucher_repo import VoucherRepository
    from services.decision_service import (
        _INTAKE_OPEN_STATUSES,
        _INTAKE_PREFIX,
        _SYNTHETIC_VIEW_KEY,
    )
    from services.fiscal_year_proposal import FiscalYearProposalService

    sha256 = _sha256(path)
    if sha256 is None:
        return None
    source = IntakeRepository.get_by_sha256(sha256)
    if source is None:
        statement = BankInputRepository.get_by_sha256(sha256)
        if statement is None:
            return None
        return {
            "kind": "statement",
            "status": statement.status.value,
            "imported_count": statement.imported_count,
            "skipped_count": statement.skipped_count,
            "parse_error": statement.parse_error,
        }

    vouchers = []
    for link in IntakeRepository.list_links_for_source(source.id):
        voucher = VoucherRepository.get(link.voucher_id)
        if voucher is not None:
            vouchers.append(
                {
                    "id": voucher.id,
                    "series": voucher.series.value,
                    "number": voucher.number,
                    "date": voucher.date.isoformat(),
                }
            )

    warning = None
    decision = None
    if not vouchers:
        warning = FiscalYearProposalService.source_date_warning(source.id)
        decision_id = (warning or {}).get("decision_id")
        if decision_id is None:
            open_decisions = DecisionRepository.list_open_for_source(source.id)
            if open_decisions:
                decision_id = open_decisions[0].id
        if decision_id is not None:
            found = DecisionRepository.get(decision_id)
            if found is not None and found.status == "open":
                decision = {
                    "id": found.id,
                    "view_key": found.view_key,
                    "title": found.title,
                }
        elif source.status.value in _INTAKE_OPEN_STATUSES:
            decision = {
                "id": f"{_INTAKE_PREFIX}{source.id}",
                "view_key": _SYNTHETIC_VIEW_KEY,
                "title": source.original_filename,
            }

    return {
        "kind": "underlag",
        "source_id": source.id,
        "status": source.status.value,
        "vouchers": vouchers,
        "decision": decision,
        "warning": (warning or {}).get("message"),
    }


def _read_note(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    # The first paragraph is the explanation; the rest is file/folder/code.
    return text.split("\n\n", 1)[0].strip() or None


def _files_under(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        dirnames[:] = [d for d in dirnames if not _is_ignored(d)]
        for filename in filenames:
            path = Path(dirpath) / filename
            if _is_ignored(filename) or path.is_symlink() or not path.is_file():
                continue
            found.append(path)
    return found


def _newest(paths: list[Path]) -> list[Path]:
    def mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    return sorted(paths, key=mtime, reverse=True)[:LISTING_LIMIT]


def dropzone_overview(scanner: DropzoneScanner | None = None) -> dict:
    """What the web view shows: the folders, and what is in them.

    ``pending`` is what the scanner has yet to read; ``problems`` is
    ``_Problem/`` with the reason from each ``.problem.txt``; ``ingested`` is
    the most recently read-in files in ``_Inläst/``. All read straight off the
    folder, so the view and the share never disagree.
    """
    scanner = scanner or get_scanner()
    root = scanner.root
    pending_paths = scanner.pending_files() if root.is_dir() else []
    pending = []
    for path in pending_paths:
        if not path.exists():
            continue
        entry = _file_entry(path, root)
        # A file the scanner tried and failed on stays put and is retried;
        # without the reason it looks exactly like one about to be read in.
        entry["error"] = scanner.file_error(path)
        pending.append(entry)

    counts: dict[str, int] = {}
    for entry in pending:
        key = folder_key(entry["folder"])
        counts[key] = counts.get(key, 0) + 1

    problems: list[dict] = []
    problem_dir = scanner._reserved_dir(PROBLEM_DIR_NAME)
    problem_files = [
        p
        for p in _files_under(problem_dir)
        if not p.name.endswith(PROBLEM_NOTE_SUFFIX) and not _is_sidecar(p)
    ]
    for path in _newest(problem_files):
        entry = _file_entry(path, root)
        entry["reason"] = _read_note(path.with_name(path.name + PROBLEM_NOTE_SUFFIX))
        problems.append(entry)

    ingested_dir = scanner._reserved_dir(INGESTED_DIR_NAME)
    ingested_files = [p for p in _files_under(ingested_dir) if not _is_sidecar(p)]
    ingested = []
    for path in _newest(ingested_files):
        entry = _file_entry(path, root)
        entry["outcome"] = _ingested_outcome(path)
        ingested.append(entry)

    return {
        "enabled": settings.dropzone_enabled,
        "quiet_seconds": scanner.quiet_seconds,
        "scan_interval_seconds": settings.dropzone_scan_interval_seconds,
        "max_bytes": MAX_DROP_BYTES,
        "targets": [
            t.as_dict(counts.get(folder_key(t.folder), 0))
            for t in drop_targets(scanner)
        ],
        "pending": pending,
        "problems": problems,
        "ingested": ingested,
        "status": scanner.status(),
    }
