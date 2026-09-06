"""Tests for folder-based intake (the Syncthing dropzone)."""

from pathlib import Path
import os
import unicodedata

import pytest

from api.routes.intake import get_dropzone_status
from config import settings
from db.database import db
from domain.types import IntakeSourceType
from repositories.account_repo import AccountRepository
from repositories.bank_input_repo import BankInputRepository
from repositories.intake_repo import IntakeRepository
from services.bank_integration import BankIntegrationService
from services.dropzone import (
    INGESTED_DIR_NAME,
    PROBLEM_DIR_NAME,
    DropzoneScanner,
    account_code_from_folder,
    mime_type_for,
)

PDF_BYTES = b"%PDF-1.4 dropzone receipt"
CSV_BYTES = (
    "Datum;Beskrivning;Belopp;Saldo\n"
    "2026-09-01;Kaffe;-45,00;1000,00\n"
).encode("utf-8")


@pytest.fixture
def dropzone_dir(tmp_path):
    """Use an isolated dropzone root for each test."""
    original = settings.dropzone_dir
    root = tmp_path / "dropzone"
    root.mkdir()
    settings.dropzone_dir = str(root)
    yield root
    settings.dropzone_dir = original


@pytest.fixture
def storage_dirs(tmp_path):
    """Use isolated intake and bank-input storage for each test."""
    original_intake = settings.intake_dir
    original_bank = settings.bank_input_dir
    settings.intake_dir = str(tmp_path / "intake")
    settings.bank_input_dir = str(tmp_path / "bank-inputs")
    yield
    settings.intake_dir = original_intake
    settings.bank_input_dir = original_bank


@pytest.fixture
def scanner(dropzone_dir, storage_dirs):
    """Scanner with the stability gate satisfied immediately."""
    return DropzoneScanner(quiet_seconds=0)


def _drop(root: Path, relative: str, content: bytes = PDF_BYTES) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _ingested_files(root: Path) -> list[Path]:
    return sorted(p for p in (root / INGESTED_DIR_NAME).rglob("*") if p.is_file())


def _problem_files(root: Path) -> list[Path]:
    return sorted(p for p in (root / PROBLEM_DIR_NAME).rglob("*") if p.is_file())


def _sources() -> list:
    return IntakeRepository().list_by_status(status=None, limit=100, offset=0)


def _statement_account(code: str = "1930", name: str = "Företagskonto") -> None:
    if not AccountRepository.exists(code):
        AccountRepository.create(code, name, "asset")


# --- 1: receipt folder -------------------------------------------------


def test_pdf_in_kvitton_becomes_a_receipt_and_is_archived(test_db, scanner, dropzone_dir):
    _drop(dropzone_dir, "Kvitton/kvitto-taxi.pdf")

    result = scanner.scan_once()

    assert result.ingested == 1
    sources = _sources()
    assert len(sources) == 1
    assert sources[0].source_type == IntakeSourceType.RECEIPT
    assert sources[0].original_filename == "kvitto-taxi.pdf"
    assert sources[0].uploaded_by == "dropzone"
    assert not (dropzone_dir / "Kvitton/kvitto-taxi.pdf").exists()
    archived = _ingested_files(dropzone_dir)
    assert [p.name for p in archived] == ["kvitto-taxi.pdf"]
    # _Inläst/YYYY-MM/
    assert archived[0].parent.parent.name == INGESTED_DIR_NAME


# --- 2: unknown folder -------------------------------------------------


def test_file_in_unknown_folder_is_ingested_without_a_type(test_db, scanner, dropzone_dir):
    _drop(dropzone_dir, "Diverse/underlag.pdf")

    scanner.scan_once()

    sources = _sources()
    assert len(sources) == 1
    assert sources[0].source_type is None
    assert _problem_files(dropzone_dir) == []


def test_file_in_dropzone_root_is_ingested_without_a_type(test_db, scanner, dropzone_dir):
    _drop(dropzone_dir, "underlag.pdf")

    scanner.scan_once()

    assert len(_sources()) == 1
    assert _sources()[0].source_type is None


# --- 3: account statements ---------------------------------------------


def test_csv_in_account_folder_creates_bank_input(test_db, scanner, dropzone_dir):
    _statement_account()
    _drop(dropzone_dir, "Kontoutdrag/1930/utdrag.csv", CSV_BYTES)

    scanner.scan_once()

    inputs = BankInputRepository().list_by_status(status=None, limit=10, offset=0)
    assert len(inputs) == 1
    connection = BankIntegrationService().get_connection(inputs[0].bank_connection_id)
    assert connection is not None
    assert connection.account_number == "1930"
    assert [p.name for p in _ingested_files(dropzone_dir)] == ["utdrag.csv"]


def test_account_folder_label_after_the_code_is_ignored(test_db, scanner, dropzone_dir):
    _statement_account()
    _drop(dropzone_dir, "Kontoutdrag/1930 Företagskonto/utdrag.csv", CSV_BYTES)

    scanner.scan_once()

    inputs = BankInputRepository().list_by_status(status=None, limit=10, offset=0)
    assert len(inputs) == 1
    connection = BankIntegrationService().get_connection(inputs[0].bank_connection_id)
    assert connection.account_number == "1930"


def test_legacy_bank_folder_alias_is_accepted(test_db, scanner, dropzone_dir):
    _statement_account()
    _drop(dropzone_dir, "Bank/1930-Företagskonto/utdrag.csv", CSV_BYTES)

    scanner.scan_once()

    inputs = BankInputRepository().list_by_status(status=None, limit=10, offset=0)
    assert len(inputs) == 1
    assert _problem_files(dropzone_dir) == []


def test_repeated_statements_reuse_one_connection(test_db, scanner, dropzone_dir):
    _statement_account()
    _drop(dropzone_dir, "Kontoutdrag/1930/utdrag-1.csv", CSV_BYTES)
    scanner.scan_once()
    _drop(
        dropzone_dir,
        "Kontoutdrag/1930/utdrag-2.csv",
        CSV_BYTES.replace(b"Kaffe", b"Lunch"),
    )
    scanner.scan_once()

    inputs = BankInputRepository().list_by_status(status=None, limit=10, offset=0)
    assert len(inputs) == 2
    assert len({item.bank_connection_id for item in inputs}) == 1
    connections = [
        conn
        for conn in BankIntegrationService().get_connections()
        if conn.account_number == "1930"
    ]
    assert len(connections) == 1


def test_statement_for_missing_account_explains_how_to_fix_it(test_db, scanner, dropzone_dir):
    _drop(dropzone_dir, "Kontoutdrag/1630 Skattekonto/utdrag.csv", CSV_BYTES)

    result = scanner.scan_once()

    assert result.problems == 1
    assert not (dropzone_dir / "Kontoutdrag/1630 Skattekonto/utdrag.csv").exists()
    note = next(p for p in _problem_files(dropzone_dir) if p.name.endswith(".problem.txt"))
    text = note.read_text(encoding="utf-8")
    assert "Konto 1630 finns inte i kontoplanen" in text
    assert "Lägg upp kontot i kontoplanen först" in text
    assert "bank_connection_not_found" in text


def test_statement_ingests_after_the_account_is_added(test_db, scanner, dropzone_dir):
    _drop(dropzone_dir, "Kontoutdrag/1630 Skattekonto/utdrag.csv", CSV_BYTES)
    scanner.scan_once()
    assert BankInputRepository().list_by_status(status=None, limit=10, offset=0) == []

    AccountRepository.create("1630", "Skattekonto", "asset")
    _drop(dropzone_dir, "Kontoutdrag/1630 Skattekonto/utdrag.csv", CSV_BYTES)

    scanner.scan_once()

    inputs = BankInputRepository().list_by_status(status=None, limit=10, offset=0)
    assert len(inputs) == 1


def test_statement_for_revenue_account_is_rejected(test_db, scanner, dropzone_dir):
    AccountRepository.create("3010", "Försäljning tjänster", "revenue")
    _drop(dropzone_dir, "Kontoutdrag/3010/utdrag.csv", CSV_BYTES)

    scanner.scan_once()

    assert BankInputRepository().list_by_status(status=None, limit=10, offset=0) == []
    note = next(p for p in _problem_files(dropzone_dir) if p.name.endswith(".problem.txt"))
    text = note.read_text(encoding="utf-8")
    assert "inte ett tillgångs- eller skuldkonto" in text


def test_statement_without_account_folder_is_rejected(test_db, scanner, dropzone_dir):
    _drop(dropzone_dir, "Kontoutdrag/utdrag.csv", CSV_BYTES)

    scanner.scan_once()

    note = next(p for p in _problem_files(dropzone_dir) if p.name.endswith(".problem.txt"))
    assert "undermapp som börjar med kontokoden" in note.read_text(encoding="utf-8")


def test_statement_folder_without_account_code_is_rejected(test_db, scanner, dropzone_dir):
    _drop(dropzone_dir, "Kontoutdrag/Företagskontot/utdrag.csv", CSV_BYTES)

    scanner.scan_once()

    note = next(p for p in _problem_files(dropzone_dir) if p.name.endswith(".problem.txt"))
    assert "börjar inte med en kontokod" in note.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "folder,expected",
    [
        ("1930", "1930"),
        ("1930 Företagskonto", "1930"),
        ("1930-Företagskonto", "1930"),
        ("1930_Företagskonto", "1930"),
        ("Företagskonto", None),
        ("19", None),
        ("1930Företagskonto", None),
    ],
)
def test_account_code_parsing(folder, expected):
    assert account_code_from_folder(folder) == expected


# --- 4: stability gate -------------------------------------------------


def test_file_still_being_written_is_not_read(test_db, dropzone_dir, storage_dirs):
    slow_scanner = DropzoneScanner(quiet_seconds=60)
    path = _drop(dropzone_dir, "Kvitton/halv.pdf")

    slow_scanner.scan_once()

    assert _sources() == []
    assert path.exists()

    # The file settles: its mtime moves outside the quiet window. That is still
    # a change since the previous observation, so it is read on the tick after.
    old = os.stat(path).st_mtime - 3600
    os.utime(path, (old, old))
    slow_scanner.scan_once()
    assert _sources() == []

    slow_scanner.scan_once()

    assert len(_sources()) == 1


def test_file_changed_between_ticks_is_not_read(test_db, dropzone_dir, storage_dirs):
    gated = DropzoneScanner(quiet_seconds=0)
    path = _drop(dropzone_dir, "Kvitton/växande.pdf")
    gated._is_stable(path)  # first observation

    path.write_bytes(PDF_BYTES + b" more bytes")

    assert gated._is_stable(path) is False
    assert gated._is_stable(path) is True


# --- 5: duplicates -----------------------------------------------------


def test_duplicate_file_is_tidied_away_without_a_second_source(
    test_db, scanner, dropzone_dir
):
    _drop(dropzone_dir, "Kvitton/kvitto.pdf")
    scanner.scan_once()
    _drop(dropzone_dir, "Kvitton/kvitto.pdf")

    result = scanner.scan_once()

    assert result.ingested == 1
    assert result.problems == 0
    assert len(_sources()) == 1
    assert not (dropzone_dir / "Kvitton/kvitto.pdf").exists()
    assert len(_ingested_files(dropzone_dir)) == 2
    assert _problem_files(dropzone_dir) == []


# --- 6: rejections -----------------------------------------------------


def test_unsupported_file_type_is_moved_to_problem_with_a_note(
    test_db, scanner, dropzone_dir
):
    _drop(dropzone_dir, "Kvitton/anteckning.docx", b"not a receipt")

    result = scanner.scan_once()

    assert result.problems == 1
    assert not (dropzone_dir / "Kvitton/anteckning.docx").exists()
    names = [p.name for p in _problem_files(dropzone_dir)]
    assert "anteckning.docx" in names
    note = dropzone_dir / PROBLEM_DIR_NAME / "anteckning.docx.problem.txt"
    assert "stöds inte" in note.read_text(encoding="utf-8")


def test_heic_note_says_how_to_get_the_photo_in(test_db, scanner, dropzone_dir):
    _drop(dropzone_dir, "Kvitton/IMG_0042.HEIC", b"\x00\x00\x00 ftypheic")

    scanner.scan_once()

    note = dropzone_dir / PROBLEM_DIR_NAME / "IMG_0042.HEIC.problem.txt"
    text = note.read_text(encoding="utf-8")
    assert "HEIC stöds inte" in text
    assert "Spara om bilden som JPEG" in text
    assert "Mest kompatibla" in text


def test_oversized_file_is_moved_to_problem(test_db, scanner, dropzone_dir):
    _drop(dropzone_dir, "Kvitton/stor.pdf", b"%PDF-1.4" + b"x" * (10 * 1024 * 1024))

    scanner.scan_once()

    note = dropzone_dir / PROBLEM_DIR_NAME / "stor.pdf.problem.txt"
    assert "större än 10 MB" in note.read_text(encoding="utf-8")


# --- 7 & 8: sidecar metadata -------------------------------------------


def test_folder_message_becomes_agent_guidance(test_db, scanner, dropzone_dir):
    _write(dropzone_dir, "Kvitton/_meddelande.txt", "Allt här är betalt med företagskort.")
    _drop(dropzone_dir, "Kvitton/kvitto.pdf")

    scanner.scan_once()

    sources = _sources()
    assert len(sources) == 1
    assert sources[0].agent_guidance == "Allt här är betalt med företagskort."
    # The message describes the folder, not one file, so it stays put.
    assert (dropzone_dir / "Kvitton/_meddelande.txt").exists()


def test_file_sidecar_becomes_that_files_explanation(test_db, scanner, dropzone_dir):
    _drop(dropzone_dir, "Kvitton/kvitto-taxi.pdf")
    _write(dropzone_dir, "Kvitton/kvitto-taxi.txt", "Taxi till kundmöte")
    _drop(dropzone_dir, "Kvitton/kvitto-lunch.pdf", PDF_BYTES + b" lunch")

    scanner.scan_once()

    by_name = {source.original_filename: source for source in _sources()}
    assert by_name["kvitto-taxi.pdf"].explanation == "Taxi till kundmöte"
    assert by_name["kvitto-lunch.pdf"].explanation is None
    assert not (dropzone_dir / "Kvitton/kvitto-taxi.txt").exists()
    assert "kvitto-taxi.txt" in [p.name for p in _ingested_files(dropzone_dir)]


def test_sidecars_are_never_ingested_as_sources(test_db, scanner, dropzone_dir):
    _write(dropzone_dir, "Kvitton/_meddelande.txt", "Guidance")
    _write(dropzone_dir, "Kvitton/lös-anteckning.txt", "Ingen fil hör till")

    result = scanner.scan_once()

    assert result.ingested == 0
    assert result.problems == 0
    assert _sources() == []
    assert _problem_files(dropzone_dir) == []


# --- 9: ignored names --------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    [
        "Kvitton/kvitto.pdf.sync-conflict-20260904-101112-ABCDEFG.pdf",
        "Kvitton/~syncthing~kvitto.pdf.tmp",
        "Kvitton/.DS_Store",
        "Kvitton/kvitto.pdf.part",
        "Kvitton/._kvitto.pdf",
        ".stignore",
    ],
)
def test_ignored_names_are_left_alone(test_db, scanner, dropzone_dir, relative):
    path = _drop(dropzone_dir, relative)

    scanner.scan_once()

    assert path.exists()
    assert _sources() == []
    assert _problem_files(dropzone_dir) == []


# --- 10: Unicode normalisation -----------------------------------------


def test_nfd_folder_name_maps_to_the_same_source_type(test_db, scanner, dropzone_dir):
    nfd_folder = unicodedata.normalize("NFD", "Leverantörsfakturor")
    assert nfd_folder != "Leverantörsfakturor"
    _drop(dropzone_dir, f"{nfd_folder}/faktura.pdf")

    scanner.scan_once()

    sources = _sources()
    assert len(sources) == 1
    assert sources[0].source_type == IntakeSourceType.SUPPLIER_INVOICE


def test_lowercase_folder_name_maps_to_the_same_source_type(
    test_db, scanner, dropzone_dir
):
    _drop(dropzone_dir, "utlägg/utlägg.pdf")

    scanner.scan_once()

    assert _sources()[0].source_type == IntakeSourceType.REIMBURSEMENT


# --- 11: symlinks ------------------------------------------------------


def test_symlink_outside_the_root_is_not_read(test_db, scanner, dropzone_dir, tmp_path):
    outside = tmp_path / "secret.pdf"
    outside.write_bytes(b"%PDF-1.4 secret")
    link = dropzone_dir / "Kvitton" / "lank.pdf"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside)

    scanner.scan_once()

    assert _sources() == []
    assert link.is_symlink()
    assert outside.exists()


def test_symlinked_directory_is_not_walked(test_db, scanner, dropzone_dir, tmp_path):
    outside_dir = tmp_path / "elsewhere"
    outside_dir.mkdir()
    (outside_dir / "kvitto.pdf").write_bytes(PDF_BYTES)
    (dropzone_dir / "Kvitton").mkdir()
    (dropzone_dir / "Kvitton" / "extern").symlink_to(outside_dir)

    scanner.scan_once()

    assert _sources() == []
    assert (outside_dir / "kvitto.pdf").exists()


# --- 12: collisions ----------------------------------------------------


def test_destination_collision_keeps_both_files(test_db, scanner, dropzone_dir):
    _drop(dropzone_dir, "Kvitton/kvitto.pdf")
    scanner.scan_once()
    _drop(dropzone_dir, "Kvitton/kvitto.pdf", PDF_BYTES + b" annan dag")

    scanner.scan_once()

    names = sorted(p.name for p in _ingested_files(dropzone_dir))
    assert names == ["kvitto (2).pdf", "kvitto.pdf"]
    assert len(_sources()) == 2


# --- 13: unexpected failures -------------------------------------------


def test_unexpected_failure_leaves_the_file_and_the_scanner_alive(
    test_db, scanner, dropzone_dir, monkeypatch
):
    _drop(dropzone_dir, "Kvitton/a-trasig.pdf")
    _drop(dropzone_dir, "Kvitton/b-frisk.pdf", PDF_BYTES + b" frisk")

    original = DropzoneScanner._ingest_source

    def explode(self, path, filename, mime_type, content, route):
        if filename == "a-trasig.pdf":
            raise RuntimeError("boom")
        return original(self, path, filename, mime_type, content, route)

    monkeypatch.setattr(DropzoneScanner, "_ingest_source", explode)

    result = scanner.scan_once()

    assert (dropzone_dir / "Kvitton/a-trasig.pdf").exists()
    assert result.ingested == 1
    assert [source.original_filename for source in _sources()] == ["b-frisk.pdf"]
    assert result.errors and "boom" in result.errors[0]


# --- 14: reserved folders ----------------------------------------------


def test_ingested_and_problem_folders_are_never_rescanned(test_db, scanner, dropzone_dir):
    _drop(dropzone_dir, f"{INGESTED_DIR_NAME}/2026-08/gammalt.pdf")
    _drop(dropzone_dir, f"{PROBLEM_DIR_NAME}/avvisat.pdf", PDF_BYTES + b" avvisat")

    result = scanner.scan_once()

    assert result.ingested == 0
    assert _sources() == []
    assert (dropzone_dir / INGESTED_DIR_NAME / "2026-08/gammalt.pdf").exists()
    assert (dropzone_dir / PROBLEM_DIR_NAME / "avvisat.pdf").exists()


# --- bounded work ------------------------------------------------------


def test_scan_processes_at_most_the_configured_batch(test_db, dropzone_dir, storage_dirs):
    bounded = DropzoneScanner(quiet_seconds=0, max_files_per_scan=2)
    for index in range(5):
        _drop(dropzone_dir, f"Kvitton/kvitto-{index}.pdf", PDF_BYTES + str(index).encode())

    assert bounded.scan_once().ingested == 2
    assert len(_sources()) == 2
    assert bounded.scan_once().ingested == 2
    assert bounded.scan_once().ingested == 1
    assert len(_sources()) == 5


def test_failing_files_still_count_against_the_batch(
    test_db, dropzone_dir, storage_dirs, monkeypatch
):
    bounded = DropzoneScanner(quiet_seconds=0, max_files_per_scan=2)
    for index in range(4):
        _drop(dropzone_dir, f"Kvitton/kvitto-{index}.pdf", PDF_BYTES + str(index).encode())

    def explode(self, path, filename, mime_type, content, route):
        raise RuntimeError("boom")

    monkeypatch.setattr(DropzoneScanner, "_ingest_source", explode)

    result = bounded.scan_once()

    assert len(result.errors) == 2


def test_archive_reuses_an_existing_decomposed_folder(test_db, scanner, dropzone_dir):
    nfd_archive = dropzone_dir / unicodedata.normalize("NFD", INGESTED_DIR_NAME)
    nfd_archive.mkdir()
    _drop(dropzone_dir, "Kvitton/kvitto.pdf")

    scanner.scan_once()

    archived = sorted(p for p in nfd_archive.rglob("*") if p.is_file())
    assert [p.name for p in archived] == ["kvitto.pdf"]
    assert sorted(p.name for p in dropzone_dir.iterdir() if p.is_dir()) == [
        "Kvitton",
        nfd_archive.name,
    ]


# --- 15 & 16: status endpoint ------------------------------------------


@pytest.mark.asyncio
async def test_status_endpoint_reports_last_scan_and_counts(
    test_db, dropzone_dir, storage_dirs, monkeypatch
):
    monkeypatch.setattr(settings, "dropzone_enabled", True)
    from services import dropzone as dropzone_module

    scanner = DropzoneScanner(quiet_seconds=0)
    monkeypatch.setattr(dropzone_module, "_scanner", scanner)

    _drop(dropzone_dir, "Kvitton/kvitto.pdf")
    _drop(dropzone_dir, "Kvitton/anteckning.docx", b"nope")
    scanner.scan_once()
    _drop(dropzone_dir, "Kvitton/väntar.pdf", PDF_BYTES + b" waiting")

    status = await get_dropzone_status(actor="api")

    assert status["enabled"] is True
    assert status["dropzone_dir"] == str(dropzone_dir)
    assert status["last_scan_at"] is not None
    assert status["last_scan_duration_ms"] is not None
    assert status["ingested_total"] == 1
    assert status["problem_file_count"] == 1
    assert status["pending_file_count"] == 1
    assert status["last_error"] is None


@pytest.mark.asyncio
async def test_status_endpoint_lists_unknown_account_folders(
    test_db, dropzone_dir, storage_dirs, monkeypatch
):
    from services import dropzone as dropzone_module

    monkeypatch.setattr(dropzone_module, "_scanner", DropzoneScanner(quiet_seconds=0))
    _statement_account()
    (dropzone_dir / "Kontoutdrag" / "1930 Företagskonto").mkdir(parents=True)
    (dropzone_dir / "Kontoutdrag" / "1630 Skattekonto").mkdir(parents=True)

    status = await get_dropzone_status(actor="api")

    assert status["unknown_account_folders"] == ["Kontoutdrag/1630 Skattekonto"]


@pytest.mark.asyncio
async def test_status_endpoint_reports_disabled_by_default(
    test_db, dropzone_dir, storage_dirs, monkeypatch
):
    from services import dropzone as dropzone_module

    monkeypatch.setattr(settings, "dropzone_enabled", False)
    monkeypatch.setattr(dropzone_module, "_scanner", DropzoneScanner(quiet_seconds=0))

    status = await get_dropzone_status(actor="api")

    assert status["enabled"] is False
    assert status["last_scan_at"] is None


def test_disabled_dropzone_never_starts_the_thread(monkeypatch):
    from services import dropzone as dropzone_module

    monkeypatch.setattr(settings, "dropzone_enabled", False)
    started = []
    monkeypatch.setattr(
        dropzone_module._runner,
        "start",
        lambda: started.append(True) or True,
    )

    assert dropzone_module.start_background_scanner() is False
    assert started == []


def test_settings_default_to_disabled_pickup():
    from config import Settings

    defaults = Settings()
    assert defaults.dropzone_enabled is False
    assert defaults.dropzone_scan_interval_seconds == 60
    assert defaults.dropzone_quiet_seconds == 10
    assert defaults.dropzone_max_files_per_scan == 25


# --- single instance ---------------------------------------------------


def test_only_one_scanner_thread_takes_the_lock(dropzone_dir, monkeypatch):
    from services.dropzone import DropzoneRunner

    monkeypatch.setattr(settings, "dropzone_enabled", True)
    first = DropzoneRunner(DropzoneScanner(quiet_seconds=0))
    second = DropzoneRunner(DropzoneScanner(quiet_seconds=0))
    try:
        assert first.start() is True
        assert second.start() is False
    finally:
        first.stop()
        second.stop()

    # The lock is released, so a later scanner can take it.
    third = DropzoneRunner(DropzoneScanner(quiet_seconds=0))
    try:
        assert third.start() is True
    finally:
        third.stop()


def test_stale_lock_from_a_dead_process_is_reclaimed(dropzone_dir):
    from services.dropzone import LOCK_FILENAME, DropzoneRunner

    (dropzone_dir / LOCK_FILENAME).write_text("999999999", encoding="utf-8")
    runner = DropzoneRunner(DropzoneScanner(quiet_seconds=0))
    try:
        assert runner.start() is True
    finally:
        runner.stop()


def test_lock_file_is_never_ingested(test_db, scanner, dropzone_dir):
    from services.dropzone import LOCK_FILENAME

    (dropzone_dir / LOCK_FILENAME).write_text(str(os.getpid()), encoding="utf-8")

    scanner.scan_once()

    assert (dropzone_dir / LOCK_FILENAME).exists()
    assert _sources() == []


# --- mime detection ----------------------------------------------------


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("kvitto.pdf", "application/pdf"),
        ("kvitto.JPG", "image/jpeg"),
        ("kvitto.png", "image/png"),
        ("utdrag.csv", "text/csv"),
        ("bild.heic", "image/heic"),
    ],
)
def test_mime_type_detection(filename, expected):
    assert mime_type_for(filename) == expected


# --- nothing is ever deleted -------------------------------------------


def test_scanner_only_ever_moves_files(test_db, scanner, dropzone_dir):
    _drop(dropzone_dir, "Kvitton/bra.pdf")
    _drop(dropzone_dir, "Kvitton/dalig.docx", b"nope")
    _drop(dropzone_dir, "Kontoutdrag/9999/utdrag.csv", CSV_BYTES)

    scanner.scan_once()

    remaining = sorted(
        p.name
        for p in dropzone_dir.rglob("*")
        if p.is_file() and not p.name.endswith(".problem.txt")
    )
    assert remaining == ["bra.pdf", "dalig.docx", "utdrag.csv"]


def test_duplicate_bank_input_is_also_tidied_away(test_db, scanner, dropzone_dir):
    _statement_account()
    _drop(dropzone_dir, "Kontoutdrag/1930/utdrag.csv", CSV_BYTES)
    scanner.scan_once()
    _drop(dropzone_dir, "Kontoutdrag/1930/utdrag.csv", CSV_BYTES)

    result = scanner.scan_once()

    assert result.ingested == 1
    assert result.problems == 0
    assert len(BankInputRepository().list_by_status(status=None, limit=10, offset=0)) == 1
    assert len(_ingested_files(dropzone_dir)) == 2


# --- SIE4 whole-year imports -------------------------------------------


def _sie4(
    start: str = "20240101",
    end: str = "20241231",
    vouchers: str | None = None,
) -> str:
    """A minimal but valid SIE4 export for one fiscal year."""
    if vouchers is None:
        vouchers = (
            '#VER A 1 20240115 "Försäljning januari"\n'
            "{\n"
            '#TRANS 1930 {} 12500.00 20240115 "Inbetalning"\n'
            '#TRANS 3010 {} -10000.00 20240115 "Försäljning"\n'
            '#TRANS 2610 {} -2500.00 20240115 "Utgående moms"\n'
            "}\n"
        )
    return (
        "#FLAGGA 0\n"
        "#FORMAT PC8\n"
        "#SIETYP 4\n"
        '#GEN "Bokföringssystem" 20250101\n'
        '#FNAMN "Testbolaget AB"\n'
        f"#RAR 0 {start} {end}\n"
        '#KONTO 1930 "Företagskonto"\n'
        '#KONTO 3010 "Försäljning tjänster"\n'
        '#KONTO 2610 "Utgående moms 25%"\n'
        "\n" + vouchers
    )


def _sie4_bytes(**kwargs) -> bytes:
    """Encode as CP437, which is what ``#FORMAT PC8`` actually means."""
    return _sie4(**kwargs).encode("cp437")


def _vouchers(fiscal_year_id: str | None = None) -> list:
    from repositories.voucher_repo import VoucherRepository

    found, _ = VoucherRepository.list_all(fiscal_year_id=fiscal_year_id, limit=100)
    return found


def _problem_note_text(root: Path) -> str:
    notes = [p for p in _problem_files(root) if p.name.endswith(".problem.txt")]
    assert len(notes) == 1, f"expected one problem note, got {notes}"
    return notes[0].read_text(encoding="utf-8")


def test_sie4_file_is_imported_and_archived(test_db, scanner, dropzone_dir):
    _drop(dropzone_dir, "SIE4-import/bokforing-2024.se", _sie4_bytes())

    result = scanner.scan_once()

    assert result.ingested == 1
    assert result.problems == 0
    vouchers = _vouchers()
    assert len(vouchers) == 1
    assert vouchers[0].description == "Försäljning januari"
    # Imported as a ledger entry, not queued as a document for the agent.
    assert _sources() == []
    assert [p.name for p in _ingested_files(dropzone_dir)] == ["bokforing-2024.se"]


def test_sie4_import_creates_the_fiscal_year_and_accounts(
    test_db, scanner, dropzone_dir
):
    _drop(dropzone_dir, "SIE4-import/2024.se", _sie4_bytes())

    scanner.scan_once()

    from repositories.period_repo import PeriodRepository

    years = PeriodRepository.list_fiscal_years()
    assert len(years) == 1
    assert years[0].start_date.isoformat() == "2024-01-01"
    assert years[0].end_date.isoformat() == "2024-12-31"
    assert AccountRepository.exists("3010")


def test_cp437_import_keeps_swedish_letters(test_db, scanner, dropzone_dir):
    _drop(dropzone_dir, "SIE4-import/2024.se", _sie4_bytes())

    scanner.scan_once()

    assert _vouchers()[0].description == "Försäljning januari"


def test_sie4_is_not_imported_into_a_year_that_already_has_vouchers(
    test_db, scanner, dropzone_dir
):
    _drop(dropzone_dir, "SIE4-import/2024.se", _sie4_bytes())
    scanner.scan_once()
    assert len(_vouchers()) == 1

    # The same year, dropped again — the guard, not the UNIQUE constraint,
    # is what has to stop this.
    _drop(dropzone_dir, "SIE4-import/2024-igen.se", _sie4_bytes())
    result = scanner.scan_once()

    assert result.ingested == 0
    assert result.problems == 1
    assert len(_vouchers()) == 1, "no second import into a booked year"
    note = _problem_note_text(dropzone_dir)
    assert "innehåller redan" in note
    assert "2024-01-01" in note and "2024-12-31" in note
    assert "sie4_fiscal_year_not_empty" in note


def test_a_different_year_still_imports_alongside_an_existing_one(
    test_db, scanner, dropzone_dir
):
    _drop(dropzone_dir, "SIE4-import/2024.se", _sie4_bytes())
    scanner.scan_once()

    _drop(
        dropzone_dir,
        "SIE4-import/2025.se",
        _sie4(
            start="20250101",
            end="20251231",
            vouchers=(
                '#VER A 1 20250115 "Försäljning 2025"\n'
                "{\n"
                '#TRANS 1930 {} 6250.00 20250115 "Inbetalning"\n'
                '#TRANS 3010 {} -5000.00 20250115 "Försäljning"\n'
                '#TRANS 2610 {} -1250.00 20250115 "Utgående moms"\n'
                "}\n"
            ),
        ).encode("cp437"),
    )
    result = scanner.scan_once()

    assert result.ingested == 1
    assert result.problems == 0
    assert len(_vouchers()) == 2


def test_non_sie4_file_in_the_import_folder_is_rejected_not_ingested(
    test_db, scanner, dropzone_dir
):
    _drop(dropzone_dir, "SIE4-import/kvitto.pdf")

    result = scanner.scan_once()

    assert result.problems == 1
    assert _sources() == [], "a PDF here must not become an untyped source"
    note = _problem_note_text(dropzone_dir)
    assert ".pdf" in note
    assert "Kvitton/" in note


def test_sie4_without_fiscal_year_is_rejected(test_db, scanner, dropzone_dir):
    content = _sie4().replace("#RAR 0 20240101 20241231\n", "")
    _drop(dropzone_dir, "SIE4-import/trasig.se", content.encode("cp437"))

    result = scanner.scan_once()

    assert result.problems == 1
    assert _vouchers() == []
    assert "#RAR 0" in _problem_note_text(dropzone_dir)


def test_partial_sie4_import_says_what_was_already_written(
    test_db, scanner, dropzone_dir
):
    # 4010 is referenced by a voucher but never declared with #KONTO, so that
    # voucher cannot be created while the first one can.
    vouchers = (
        '#VER A 1 20240115 "Försäljning januari"\n'
        "{\n"
        '#TRANS 1930 {} 12500.00 20240115 "Inbetalning"\n'
        '#TRANS 3010 {} -10000.00 20240115 "Försäljning"\n'
        '#TRANS 2610 {} -2500.00 20240115 "Utgående moms"\n'
        "}\n"
        '#VER A 2 20240210 "Okänt konto"\n'
        "{\n"
        '#TRANS 4010 {} 1000.00 20240210 "Kostnad"\n'
        '#TRANS 1930 {} -1000.00 20240210 "Betalning"\n'
        "}\n"
    )
    _drop(dropzone_dir, "SIE4-import/2024.se", _sie4(vouchers=vouchers).encode("cp437"))

    result = scanner.scan_once()

    assert result.problems == 1
    note = _problem_note_text(dropzone_dir)
    # The honest part: some vouchers are already posted and immutable.
    assert "sie4_import_incomplete" in note
    assert "kan inte tas bort" in note
    assert "lägg inte tillbaka filen" in note.lower()


def test_txt_in_the_import_folder_is_still_a_sidecar(test_db, scanner, dropzone_dir):
    _write(dropzone_dir, "SIE4-import/_meddelande.txt", "Årsexporter läggs här.")

    result = scanner.scan_once()

    assert result.ingested == 0
    assert result.problems == 0
    assert (dropzone_dir / "SIE4-import/_meddelande.txt").exists()


def test_import_folder_name_is_matched_case_insensitively(
    test_db, scanner, dropzone_dir
):
    _drop(dropzone_dir, "sie4-import/2024.se", _sie4_bytes())

    result = scanner.scan_once()

    assert result.ingested == 1
    assert len(_vouchers()) == 1
