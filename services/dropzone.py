"""Folder-based intake: pick up files left in a synced dropzone directory.

The dropzone is an ordinary directory tree — in practice a Syncthing-shared
folder — where the owner drops receipts, invoices and account statements from
any device. A background thread walks it, hands each file to the *existing*
intake services, and moves it out of the way afterwards:

    Bokföring/
      Kvitton/                     -> source_type = receipt
      Leverantörsfakturor/         -> source_type = supplier_invoice
      Kundfakturor/                -> source_type = customer_invoice
      Utlägg/                      -> source_type = reimbursement
      Övrigt/                      -> source_type = other
      Kontoutdrag/1930 Företagskonto/  -> account statement for account 1930
      SIE4-import/                 -> whole-year SIE4 ledger export, imported
      _Inläst/2026-09/             <- ingested files are moved here
      _Problem/                    <- rejected files, with a .txt saying why

The scanner is a *caller* of ``IntakeService`` and ``BankInputService``, never a
parallel ingest path, so validation, storage, dedupe and the audit trail behave
exactly as they do for a browser upload. It never deletes anything: every file
either stays put or is moved.
"""

from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
import logging
import mimetypes
import os
import re
import shutil
import threading
import time
import unicodedata

from config import settings
from domain.types import IntakeSourceType
from repositories.account_repo import AccountRepository
from services.bank_inputs import (
    BankInputError,
    BankInputService,
    DuplicateBankInputError,
    is_statement_account,
)
from services.intake import DuplicateIntakeSourceError, IntakeError, IntakeService

logger = logging.getLogger(__name__)

DROPZONE_ACTOR = "dropzone"
INGESTED_DIR_NAME = "_Inläst"
PROBLEM_DIR_NAME = "_Problem"
FOLDER_MESSAGE_FILENAME = "_meddelande.txt"
PROBLEM_NOTE_SUFFIX = ".problem.txt"
LOCK_FILENAME = ".dropzone.lock"


def folder_key(name: str) -> str:
    """Normalise a folder or file name for comparison.

    macOS stores names as NFD and Linux as NFC, so a ``Leverantörsfakturor/``
    folder created on a laptop does not compare equal to an NFC constant on the
    server. Normalising both sides is what keeps the mapping from silently
    falling through to an unclassified source.
    """
    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", name).casefold())


SOURCE_TYPE_FOLDERS = {
    folder_key("Kvitton"): IntakeSourceType.RECEIPT,
    folder_key("Leverantörsfakturor"): IntakeSourceType.SUPPLIER_INVOICE,
    folder_key("Kundfakturor"): IntakeSourceType.CUSTOMER_INVOICE,
    folder_key("Utlägg"): IntakeSourceType.REIMBURSEMENT,
    folder_key("Övrigt"): IntakeSourceType.OTHER,
}

# "Kontoutdrag" covers bank, tax-account, card and payment-provider statements
# alike. "Bank" stays accepted so an existing folder keeps working.
STATEMENT_FOLDERS = {folder_key("Kontoutdrag"), folder_key("Bank")}

# A whole-year SIE4 export is the one dropzone input that writes vouchers
# directly instead of queueing a document for the agent to classify.
SIE4_FOLDERS = {folder_key("SIE4-import")}

# ".txt" is reserved for sidecar metadata (see _is_sidecar), so a SIE4 file
# saved as .txt would be read as an explanation and never imported. The
# accepted extensions are the ones SIE exporters actually emit.
SIE4_EXTENSIONS = {".se", ".si", ".sie", ".sie4"}

RESERVED_DIR_NAMES = {folder_key(INGESTED_DIR_NAME), folder_key(PROBLEM_DIR_NAME)}

IGNORED_NAME_PATTERNS = (
    ".stfolder",
    ".stversions",
    ".stignore",
    "~syncthing~*.tmp",
    "*.sync-conflict-*",
    ".ds_store",
    "._*",
    "thumbs.db",
    "desktop.ini",
    "*.part",
    "*.tmp",
    "*.crdownload",
    LOCK_FILENAME,
)

MIME_TYPE_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".csv": "text/csv",
    ".heic": "image/heic",
    ".heif": "image/heif",
}

ACCOUNT_FOLDER_PATTERN = re.compile(r"^(\d{3,6})(?:[\s\-_.].*)?$")


class Sie4DropzoneError(Exception):
    """A SIE4 file could not be imported, explained in Swedish.

    Carries its own message rather than going through ``problem_message_for``:
    the useful thing to say about a rejected ledger export is which fiscal year
    it covers and what already occupies it, which no error code conveys.
    """

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass
class DropzoneRoute:
    """Where a dropzone file belongs, derived from its folder."""

    kind: str  # "voucher_source", "bank_input", "sie4_import" or "problem"
    source_type: str | None = None
    account_code: str | None = None
    problem_message: str | None = None


@dataclass
class ScanState:
    """Mutable record of what the scanner last did."""

    last_scan_at: datetime | None = None
    last_scan_duration_ms: int | None = None
    last_error: str | None = None
    last_ingested_count: int = 0
    last_problem_count: int = 0


@dataclass
class ScanResult:
    """Outcome counts for a single tick."""

    ingested: int = 0
    problems: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class DropzoneScanner:
    """Walk the dropzone once per tick and route files into intake."""

    def __init__(
        self,
        root: str | os.PathLike[str] | None = None,
        quiet_seconds: int | None = None,
        max_files_per_scan: int | None = None,
    ):
        self._root_override = Path(root) if root is not None else None
        self._quiet_seconds_override = quiet_seconds
        self._max_files_override = max_files_per_scan
        self._observations: dict[str, tuple[float, int]] = {}
        self._state = ScanState()

    # --- configuration -------------------------------------------------

    @property
    def root(self) -> Path:
        if self._root_override is not None:
            return self._root_override
        return Path(settings.dropzone_dir)

    @property
    def quiet_seconds(self) -> int:
        if self._quiet_seconds_override is not None:
            return self._quiet_seconds_override
        return settings.dropzone_quiet_seconds

    @property
    def max_files_per_scan(self) -> int:
        if self._max_files_override is not None:
            return self._max_files_override
        return max(1, settings.dropzone_max_files_per_scan)

    # --- scanning ------------------------------------------------------

    def scan_once(self) -> ScanResult:
        """Run one tick. Never raises — a dead scanner is the worst outcome."""
        started_at = time.monotonic()
        result = ScanResult()
        error: str | None = None
        try:
            self._scan(result)
        except Exception as exc:  # pragma: no cover - defensive
            error = f"{type(exc).__name__}: {exc}"
            logger.exception("Dropzone scan failed")
        if result.errors and error is None:
            error = result.errors[-1]

        self._state.last_scan_at = datetime.now()
        self._state.last_scan_duration_ms = int((time.monotonic() - started_at) * 1000)
        self._state.last_error = error
        self._state.last_ingested_count = result.ingested
        self._state.last_problem_count = result.problems
        return result

    def _scan(self, result: ScanResult) -> None:
        root = self.root
        if not root.is_dir():
            result.errors.append(f"dropzone_dir_missing: {root}")
            return

        budget = self.max_files_per_scan
        attempted = 0
        candidates = self.candidate_files()
        self._forget_gone_files(candidates)
        for path in candidates:
            if attempted >= budget:
                break
            if _is_sidecar(path):
                continue
            if not self._is_stable(path):
                result.skipped += 1
                continue
            attempted += 1
            try:
                self._process_file(path, result)
            except Exception as exc:
                # One bad file must never kill the scanner, and a file we do not
                # understand stays where it is so the next tick can retry it.
                logger.exception("Dropzone could not process %s", path)
                result.errors.append(f"{path.name}: {type(exc).__name__}: {exc}")
            time.sleep(0)  # yield the GIL between files

    def _forget_gone_files(self, candidates: list[Path]) -> None:
        """Drop stability observations for files that are no longer there."""
        live = {str(path) for path in candidates}
        for key in list(self._observations):
            if key not in live:
                del self._observations[key]

    def candidate_files(self) -> list[Path]:
        """List files eligible for ingestion, in folder and name order."""
        root = self.root
        if not root.is_dir():
            return []

        candidates: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            current = Path(dirpath)
            dirnames[:] = sorted(
                name
                for name in dirnames
                if not _is_ignored(name)
                and not (current == root and folder_key(name) in RESERVED_DIR_NAMES)
                and not (current / name).is_symlink()
            )
            for filename in sorted(filenames):
                if _is_ignored(filename):
                    continue
                path = current / filename
                if path.is_symlink() or not path.is_file():
                    continue
                if not self._is_within_root(path):
                    continue
                candidates.append(path)
        return candidates

    def pending_files(self) -> list[Path]:
        """Files waiting to be ingested, excluding sidecar metadata."""
        return [path for path in self.candidate_files() if not _is_sidecar(path)]

    def _is_stable(self, path: Path) -> bool:
        """Refuse to read a file that may still be being written.

        Reading a half-written file would store corrupt bytes under a *valid*
        sha256, and dedupe would then reject the good copy forever.
        """
        key = str(path)
        try:
            stat = path.stat()
        except OSError:
            self._observations.pop(key, None)
            return False

        signature = (stat.st_mtime, stat.st_size)
        previous = self._observations.get(key)
        self._observations[key] = signature
        if previous is not None and previous != signature:
            return False
        return (time.time() - stat.st_mtime) >= self.quiet_seconds

    # --- routing -------------------------------------------------------

    def route_for(self, path: Path) -> DropzoneRoute:
        """Decide what a file is, based on the folder it was dropped in."""
        parts = path.relative_to(self.root).parts
        if len(parts) == 1:
            return DropzoneRoute(kind="voucher_source")

        top = folder_key(parts[0])
        if top in SOURCE_TYPE_FOLDERS:
            return DropzoneRoute(
                kind="voucher_source",
                source_type=SOURCE_TYPE_FOLDERS[top].value,
            )
        if top in STATEMENT_FOLDERS:
            return self._statement_route(parts)
        if top in SIE4_FOLDERS:
            return self._sie4_route(path)
        # An unrecognised folder is not an error: the file is ingested without a
        # type and the agent classifies it.
        return DropzoneRoute(kind="voucher_source")

    def _statement_route(self, parts: tuple[str, ...]) -> DropzoneRoute:
        if len(parts) < 3:
            return DropzoneRoute(
                kind="problem",
                problem_message=(
                    f"Kontoutdrag måste ligga i en undermapp som börjar med kontokoden. "
                    f"Skapa till exempel {parts[0]}/1930 Företagskonto/ och lägg filen där."
                ),
            )
        account_code = account_code_from_folder(parts[1])
        if not account_code:
            return DropzoneRoute(
                kind="problem",
                problem_message=(
                    f'Mappen "{parts[1]}" börjar inte med en kontokod. Döp om den så att '
                    'den inleds med kontots nummer, till exempel "1930 Företagskonto".'
                ),
            )
        return DropzoneRoute(kind="bank_input", account_code=account_code)

    def _sie4_route(self, path: Path) -> DropzoneRoute:
        """Only recognised SIE extensions are treated as ledger exports.

        Anything else in the folder is bounced rather than ingested as an
        untyped document: silently filing a stray PDF as a receipt from a
        folder the owner meant for whole-year imports would be worse than
        saying so.
        """
        extension = path.suffix.lower()
        if extension in SIE4_EXTENSIONS:
            return DropzoneRoute(kind="sie4_import")
        return DropzoneRoute(
            kind="problem",
            problem_message=(
                f"Filtypen {extension or 'okänd'} känns inte igen som en "
                "SIE4-fil. SIE4-import/ tar bara emot bokföringsexporter "
                "(.se, .si, .sie eller .sie4). Lägg underlag i Kvitton/, "
                "Leverantörsfakturor/, Kundfakturor/, Utlägg/ eller Övrigt/ "
                "i stället."
            ),
        )

    # --- ingestion -----------------------------------------------------

    def _process_file(self, path: Path, result: ScanResult) -> None:
        route = self.route_for(path)
        if route.kind == "problem":
            self._reject(path, route.problem_message or "", "dropzone_folder_layout")
            result.problems += 1
            return

        content = path.read_bytes()
        filename = unicodedata.normalize("NFC", path.name)
        mime_type = mime_type_for(filename)

        try:
            if route.kind == "bank_input":
                self._ingest_bank_input(filename, mime_type, content, route)
            elif route.kind == "sie4_import":
                self._ingest_sie4(filename, content)
            else:
                self._ingest_source(path, filename, mime_type, content, route)
        except (DuplicateIntakeSourceError, DuplicateBankInputError):
            # A duplicate is a success: the file *is* in the system. Tidying it
            # away anyway is what makes re-dropping a half-processed folder safe.
            self._archive(path)
            result.ingested += 1
        except Sie4DropzoneError as exc:
            self._reject(path, exc.message, exc.code)
            result.problems += 1
        except (IntakeError, BankInputError) as exc:
            self._reject(path, problem_message_for(exc, route, filename), exc.code)
            result.problems += 1
        else:
            self._archive(path)
            result.ingested += 1

    def _ingest_source(
        self,
        path: Path,
        filename: str,
        mime_type: str,
        content: bytes,
        route: DropzoneRoute,
    ) -> None:
        IntakeService().create_source_from_upload_content(
            filename=filename,
            content_type=mime_type,
            content=content,
            explanation=self._file_explanation(path),
            source_type=route.source_type,
            actor=DROPZONE_ACTOR,
            agent_guidance=self._folder_guidance(path.parent),
        )

    def _ingest_sie4(self, filename: str, content: bytes) -> None:
        """Import a whole-year SIE4 export, but only into an empty fiscal year.

        Every other dropzone input queues a document for an agent to classify
        and a human to approve. This one writes *posted* vouchers, and posted
        vouchers are immutable under BFL — there is no undo, only B-series
        reversals. So the guard matters more than the convenience: a file is
        imported only when the fiscal year it covers holds no vouchers yet.
        Bootstrapping history stays hands-off, while auto-posting on top of a
        year that is already booked becomes impossible.
        """
        from domain.validation import ValidationError
        from repositories.voucher_repo import VoucherRepository
        from services.sie4_import import SIE4Importer, SIE4Parser

        try:
            text = SIE4Parser.decode_bytes(content)
        except UnicodeDecodeError:
            raise Sie4DropzoneError(
                "Filen gick inte att teckentolka. En SIE4-fil ska vara sparad "
                "som PC8/CP437 eller UTF-8. Exportera om den från ditt "
                "bokföringsprogram och lägg tillbaka den.",
                "sie4_decode_failed",
            )

        importer = SIE4Importer(
            api_url=settings.api_url,
            api_key=settings.api_key,
        )
        try:
            data = importer.parser.parse_content(text)
        except Exception as exc:
            raise Sie4DropzoneError(
                f"Filen kunde inte tolkas som SIE4: {exc}. Kontrollera att det "
                "är en fullständig SIE4-export och inte en delvis sparad fil.",
                "sie4_parse_failed",
            )

        encoding_issues = SIE4Parser.find_encoding_issues(data)
        if encoding_issues:
            raise Sie4DropzoneError(
                "Filen innehåller tecken som ser felkodade ut — till exempel "
                f"{encoding_issues[0]}. Exportera om den med rätt teckenkodning "
                "(#FORMAT PC8 ska sparas som CP437) så att å, ä och ö blir rätt.",
                "sie4_encoding_issues",
            )

        try:
            fiscal_year_id = importer.resolve_fiscal_year(data)
        except ValidationError as exc:
            raise Sie4DropzoneError(
                f"Räkenskapsåret kunde inte avgöras: {exc.message}. En SIE4-fil "
                "måste innehålla en giltig #RAR 0-rad med räkenskapsårets "
                "start- och slutdatum.",
                exc.code,
            )

        _, existing_vouchers = VoucherRepository.list_all(
            fiscal_year_id=fiscal_year_id, limit=1
        )
        if existing_vouchers:
            # Read the dates back from the resolution rather than from the
            # parsed file: they are already normalised to ISO there, and it
            # does not depend on resolve_fiscal_year having rejected None.
            resolution = importer.fiscal_year_resolution or {}
            period = f"{resolution.get('start')}–{resolution.get('end')}"
            raise Sie4DropzoneError(
                f"Räkenskapsåret {period} innehåller redan {existing_vouchers} "
                "verifikationer, så filen importerades inte. Automatisk import "
                "sker bara till ett tomt räkenskapsår, eftersom bokförda "
                "verifikationer inte kan ändras eller tas bort i efterhand. "
                "Vill du ändå importera filen får du göra det manuellt under "
                "Import i webbgränssnittet, efter att ha kontrollerat vad som "
                "redan är bokfört på året.",
                "sie4_fiscal_year_not_empty",
            )

        if not importer.import_content(text, fiscal_year_id):
            imported = importer.imported
            reasons = "; ".join(importer.errors[:5]) or "okänt fel"
            raise Sie4DropzoneError(
                "Importen gick inte igenom fullständigt. "
                f"{imported['vouchers']} verifikationer och "
                f"{imported['accounts']} konton bokfördes, men minst en post "
                f"kunde inte bokföras. Orsak: {reasons}. "
                "OBS: de verifikationer som redan bokförts ligger kvar och kan "
                "inte tas bort — lägg inte tillbaka filen i mappen igen, utan "
                "stäm av räkenskapsåret först.",
                "sie4_import_incomplete",
            )

        logger.info(
            "Dropzone imported SIE4 %s: %s vouchers, %s accounts, fiscal year %s",
            filename,
            importer.imported["vouchers"],
            importer.imported["accounts"],
            fiscal_year_id,
        )

    def _ingest_bank_input(
        self,
        filename: str,
        mime_type: str,
        content: bytes,
        route: DropzoneRoute,
    ) -> None:
        service = BankInputService()
        connection_id = service.resolve_connection_reference(
            f"account:{route.account_code}"
        )
        service.create_from_upload_content(
            filename=filename,
            content_type=mime_type,
            content=content,
            bank_connection_id=connection_id,
            actor=DROPZONE_ACTOR,
        )

    # --- sidecar metadata ----------------------------------------------

    def _folder_guidance(self, folder: Path) -> str | None:
        """Read ``_meddelande.txt`` — guidance for every file in that folder.

        The message stays in place: it describes the folder, not one file, and
        moving it after the first pickup would silently drop the guidance for
        every file dropped there later.
        """
        return _read_sidecar(_find_sidecar(folder, FOLDER_MESSAGE_FILENAME))

    def _file_explanation(self, path: Path) -> str | None:
        """Read ``<filnamn>.txt`` beside a file — that file's explanation."""
        return _read_sidecar(self._file_sidecar(path))

    def _file_sidecar(self, path: Path) -> Path | None:
        sidecar = _find_sidecar(path.parent, f"{path.stem}.txt")
        if sidecar is None:
            return None
        if folder_key(sidecar.name) == folder_key(FOLDER_MESSAGE_FILENAME):
            return None
        return sidecar

    # --- disposal ------------------------------------------------------

    def _archive(self, path: Path) -> Path:
        destination = (
            self._reserved_dir(INGESTED_DIR_NAME) / datetime.now().strftime("%Y-%m")
        )
        return self._move_with_sidecar(path, destination)

    def _reject(self, path: Path, message: str, code: str) -> Path:
        destination = self._reserved_dir(PROBLEM_DIR_NAME)
        folder = path.parent.relative_to(self.root)
        moved = self._move_with_sidecar(path, destination)
        note = moved.with_name(moved.name + PROBLEM_NOTE_SUFFIX)
        note.write_text(
            "\n".join(
                [
                    message,
                    "",
                    f"Fil: {path.name}",
                    f"Mapp: {folder.as_posix() if folder.parts else '.'}",
                    f"Felkod: {code}",
                    f"Tidpunkt: {datetime.now().isoformat(timespec='seconds')}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        logger.warning("Dropzone rejected %s (%s)", path, code)
        return moved

    def _reserved_dir(self, name: str) -> Path:
        """Return ``_Inläst``/``_Problem``, reusing an existing NFD spelling.

        A folder created on macOS arrives with its ``ä`` decomposed; writing to
        the NFC name would leave two archive folders side by side.
        """
        wanted = folder_key(name)
        try:
            entries = list(self.root.iterdir())
        except OSError:
            return self.root / name
        for entry in entries:
            if entry.is_dir() and folder_key(entry.name) == wanted:
                return entry
        return self.root / name

    def _move_with_sidecar(self, path: Path, destination_dir: Path) -> Path:
        sidecar = self._file_sidecar(path)
        moved = self._move(path, destination_dir)
        if sidecar is not None and sidecar.exists():
            self._move(sidecar, destination_dir)
        return moved

    def _move(self, path: Path, destination_dir: Path) -> Path:
        destination_dir.mkdir(parents=True, exist_ok=True)
        target = _unique_destination(destination_dir, path.name)
        if not self._is_within_root(target):
            raise ValueError(f"Dropzone move target escapes root: {target}")
        shutil.move(str(path), str(target))
        self._observations.pop(str(path), None)
        return target

    def _is_within_root(self, path: Path) -> bool:
        """Mirror ``IntakeService.resolve_source_file`` containment checking."""
        root = self.root.resolve()
        try:
            candidate = path.resolve()
        except OSError:
            return False
        return candidate != root and candidate.is_relative_to(root)

    # --- status --------------------------------------------------------

    def unknown_account_folders(self) -> list[str]:
        """Statement folders whose account code cannot be used.

        Reported so a mistyped or unseeded folder is visible *before* forty
        statements are dropped into it and bounce one by one.
        """
        unknown: list[str] = []
        root = self.root
        if not root.is_dir():
            return unknown

        for statement_root in sorted(root.iterdir()):
            if not statement_root.is_dir() or statement_root.is_symlink():
                continue
            if folder_key(statement_root.name) not in STATEMENT_FOLDERS:
                continue
            for folder in sorted(statement_root.iterdir()):
                if not folder.is_dir() or folder.is_symlink() or _is_ignored(folder.name):
                    continue
                if not _is_usable_statement_folder(folder.name):
                    unknown.append(f"{statement_root.name}/{folder.name}")
        return unknown

    def status(self) -> dict:
        """Snapshot for the status endpoint."""
        state = self._state
        return {
            "enabled": settings.dropzone_enabled,
            "dropzone_dir": str(self.root),
            "scan_interval_seconds": settings.dropzone_scan_interval_seconds,
            "last_scan_at": state.last_scan_at.isoformat() if state.last_scan_at else None,
            "last_scan_duration_ms": state.last_scan_duration_ms,
            "pending_file_count": len(self.pending_files()),
            "ingested_total": _count_files(self._reserved_dir(INGESTED_DIR_NAME)),
            "problem_file_count": _count_files(
                self._reserved_dir(PROBLEM_DIR_NAME),
                exclude_suffix=PROBLEM_NOTE_SUFFIX,
            ),
            "unknown_account_folders": self.unknown_account_folders(),
            "last_error": state.last_error,
        }


class DropzoneRunner:
    """Run a scanner on an interval in a background thread."""

    def __init__(self, scanner: DropzoneScanner):
        self.scanner = scanner
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock_path: Path | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """Start the thread. Returns False if it could not take the lock."""
        if self.running:
            return True
        root = self.scanner.root
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("Dropzone directory %s is unusable: %s", root, exc)
            return False

        self._lock_path = _acquire_lock(root)
        if self._lock_path is None:
            logger.warning(
                "Dropzone scanner not started: %s is held by another process",
                root / LOCK_FILENAME,
            )
            return False

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="dropzone-scanner",
            daemon=True,
        )
        self._thread.start()
        logger.info("Dropzone scanner watching %s", root)
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None
        _release_lock(self._lock_path)
        self._lock_path = None

    def _run(self) -> None:
        while not self._stop.is_set():
            self.scanner.scan_once()
            self._stop.wait(max(1, settings.dropzone_scan_interval_seconds))


_scanner = DropzoneScanner()
_runner = DropzoneRunner(_scanner)


def get_scanner() -> DropzoneScanner:
    """Return the process-wide scanner."""
    return _scanner


def start_background_scanner() -> bool:
    """Start folder pickup if it is enabled. Safe to call when it is not."""
    if not settings.dropzone_enabled:
        logger.info("Dropzone disabled (DROPZONE_ENABLED=false)")
        return False
    return _runner.start()


def stop_background_scanner() -> None:
    _runner.stop()


def dropzone_status() -> dict:
    """Status of folder pickup, for the intake page and the status endpoint."""
    return _scanner.status()


# --- helpers -----------------------------------------------------------


def account_code_from_folder(name: str) -> str | None:
    """Extract the leading account code from a statement folder name.

    ``1930``, ``1930 Företagskonto`` and ``1930-Företagskonto`` are equivalent:
    the leading token is the account code, the rest is a human label.
    """
    match = ACCOUNT_FOLDER_PATTERN.match(unicodedata.normalize("NFC", name).strip())
    return match.group(1) if match else None


def mime_type_for(filename: str) -> str:
    """Best-effort MIME type from a filename, for the service validators."""
    extension = Path(filename).suffix.lower()
    if extension in MIME_TYPE_BY_EXTENSION:
        return MIME_TYPE_BY_EXTENSION[extension]
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def problem_message_for(
    exc: IntakeError | BankInputError,
    route: DropzoneRoute,
    filename: str,
) -> str:
    """Explain a rejection in Swedish, in terms of what to do about it."""
    code = exc.code
    extension = Path(filename).suffix.lower()

    if code == "unsupported_mime_type":
        if extension in (".heic", ".heif"):
            return (
                "HEIC stöds inte. Spara om bilden som JPEG och lägg tillbaka den "
                '— eller ställ in kameran på "Mest kompatibla".'
            )
        return (
            f"Filtypen {extension or 'okänd'} stöds inte som underlag. "
            "Underlag måste vara PDF, JPEG, PNG, GIF eller WEBP."
        )
    if code in ("file_too_large", "bank_input_file_too_large"):
        return (
            "Filen är större än 10 MB. Komprimera eller dela upp den och lägg "
            "tillbaka den i mappen."
        )
    if code == "bank_connection_not_found":
        return (
            f"Konto {route.account_code} finns inte i kontoplanen. Lägg upp kontot "
            "i kontoplanen först, eller flytta filen till en mapp för ett konto "
            "som finns."
        )
    if code == "unsupported_statement_account_type":
        return (
            f"Konto {route.account_code} är inte ett tillgångs- eller skuldkonto "
            "och kan därför inte ta emot kontoutdrag. Flytta filen till en mapp "
            "för ett bank- eller skuldkonto."
        )
    if code == "inactive_bank_connection":
        return (
            f"Kontot {route.account_code} är inaktivt. Aktivera kontot i "
            "kontoplanen, eller flytta filen till en mapp för ett aktivt konto."
        )
    if code in ("unsupported_bank_input_file", "unsupported_bank_input_mime_type"):
        return (
            "Kontoutdrag måste vara CSV-filer. Exportera utdraget som CSV och "
            "lägg tillbaka det i mappen."
        )
    if code == "invalid_source_type":
        return (
            "Mappen motsvarar ingen känd underlagstyp. Flytta filen till Kvitton/, "
            "Leverantörsfakturor/, Kundfakturor/, Utlägg/ eller Övrigt/."
        )
    return f"Filen kunde inte läsas in: {exc.message} ({code})."


def _is_ignored(name: str) -> bool:
    lowered = unicodedata.normalize("NFC", name).lower()
    return any(fnmatch(lowered, pattern) for pattern in IGNORED_NAME_PATTERNS)


def _is_sidecar(path: Path) -> bool:
    """``.txt`` is always sidecar metadata, never source material."""
    return path.suffix.lower() == ".txt"


def _find_sidecar(folder: Path, name: str) -> Path | None:
    """Find a sidecar by name, tolerating NFC/NFD and case differences."""
    wanted = folder_key(name)
    try:
        entries = list(folder.iterdir())
    except OSError:
        return None
    for entry in entries:
        if entry.is_file() and not entry.is_symlink() and folder_key(entry.name) == wanted:
            return entry
    return None


def _read_sidecar(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    return text or None


def _is_usable_statement_folder(name: str) -> bool:
    code = account_code_from_folder(name)
    if not code:
        return False
    account = AccountRepository.get(code)
    return bool(account and account.active and is_statement_account(account))


def _unique_destination(destination_dir: Path, filename: str) -> Path:
    """Never overwrite: ``namn.pdf`` becomes ``namn (2).pdf`` on collision."""
    candidate = destination_dir / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 2
    while True:
        candidate = destination_dir / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _count_files(folder: Path, exclude_suffix: str | None = None) -> int:
    if not folder.is_dir():
        return 0
    count = 0
    for dirpath, _dirnames, filenames in os.walk(folder, followlinks=False):
        for filename in filenames:
            if exclude_suffix and filename.endswith(exclude_suffix):
                continue
            if _is_ignored(filename):
                continue
            count += 1
    return count


# Locks this process holds. The lock file alone cannot tell "another worker in
# this process tree" from "a leftover file written by a process that has since
# died and whose pid we now reuse", so ownership within the process is tracked
# here and staleness is only ever inferred for a pid we do not hold.
_held_locks: set[str] = set()
_held_locks_guard = threading.Lock()


def _acquire_lock(root: Path) -> Path | None:
    """Take an exclusive lock file so only one scanner walks the tree."""
    lock_path = root / LOCK_FILENAME
    key = os.path.abspath(lock_path)
    with _held_locks_guard:
        if key in _held_locks:
            return None
        for _attempt in range(2):
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                if not _lock_is_stale(lock_path):
                    return None
                try:
                    lock_path.unlink()
                except OSError:
                    return None
                continue
            except OSError as exc:
                logger.error("Could not create dropzone lock %s: %s", lock_path, exc)
                return None
            with os.fdopen(fd, "w") as handle:
                handle.write(str(os.getpid()))
            _held_locks.add(key)
            return lock_path
    return None


def _lock_is_stale(lock_path: Path) -> bool:
    try:
        pid = int(lock_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return True
    return False


def _release_lock(lock_path: Path | None) -> None:
    if lock_path is None:
        return
    with _held_locks_guard:
        _held_locks.discard(os.path.abspath(lock_path))
        try:
            lock_path.unlink()
        except OSError:
            pass
