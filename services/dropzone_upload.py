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
    _is_usable_statement_folder,
    account_code_from_folder,
    folder_key,
    get_scanner,
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

    The share's folders, in the share's layout: the five type folders and
    ``SIE4-import`` always (created on first drop if missing), every other
    top-level folder someone made on the share (read in without a type, the
    agent classifies), and every ``Kontoutdrag/<konto>`` folder that exists
    and names a usable statement account. A statement folder is not invented
    here: which accounts get one is decided on the share, as before.
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

    statement_roots: list[Path] = []
    try:
        statement_roots = sorted(
            entry
            for entry in root.iterdir()
            if entry.is_dir()
            and not entry.is_symlink()
            and folder_key(entry.name) in STATEMENT_FOLDERS
        )
    except OSError:
        pass
    for statement_root in statement_roots:
        try:
            children = sorted(statement_root.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir() or child.is_symlink() or _is_ignored(child.name):
                continue
            if not _is_usable_statement_folder(child.name):
                continue
            code = account_code_from_folder(child.name)
            account = AccountRepository.get(code) if code else None
            targets.append(
                DropTarget(
                    folder=f"{statement_root.name}/{child.name}",
                    label=unicodedata.normalize("NFC", child.name),
                    kind="bank_input",
                    account_code=code,
                    account_name=account.name if account else None,
                )
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
    pending = [_file_entry(p, root) for p in pending_paths if p.exists()]

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
    ingested = [_file_entry(p, root) for p in _newest(ingested_files)]

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
