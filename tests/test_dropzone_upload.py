"""The dropzone from the browser (`services/dropzone_upload.py`).

An upload is written into the dropzone folder and read in by the scanner,
exactly like a file copied in over SMB.
"""

import hashlib

import pytest
from fastapi.testclient import TestClient

from config import settings
from domain.types import IntakeSourceType
from repositories.account_repo import AccountRepository
from repositories.intake_repo import IntakeRepository
from services import dropzone as dropzone_module
from services.dropzone import INGESTED_DIR_NAME, PROBLEM_DIR_NAME, DropzoneScanner
from services.dropzone_upload import (
    DropzoneUploadError,
    drop_file,
    drop_targets,
    dropzone_overview,
)

PDF = b"%PDF-1.4 webb-kvitto"


@pytest.fixture
def root(tmp_path, monkeypatch):
    root = tmp_path / "dropzone"
    root.mkdir()
    monkeypatch.setattr(settings, "dropzone_dir", str(root))
    monkeypatch.setattr(settings, "dropzone_enabled", True)
    monkeypatch.setattr(settings, "intake_dir", str(tmp_path / "intake"))
    monkeypatch.setattr(settings, "bank_input_dir", str(tmp_path / "bank-inputs"))
    scanner = DropzoneScanner(quiet_seconds=0)
    monkeypatch.setattr(dropzone_module, "_scanner", scanner)
    return root


def _drop(folder: str, name: str = "kvitto.pdf", content: bytes = PDF):
    return drop_file(folder=folder, filename=name, content=content, actor="t")


def test_a_dropped_file_is_read_in_by_the_scanner(test_db, root):
    result = _drop("Kvitton")

    assert result["filename"] == "kvitto.pdf"
    assert (root / "Kvitton" / "kvitto.pdf").read_bytes() == PDF
    assert not list(root.rglob("*.part"))

    dropzone_module.get_scanner().scan_once()

    sources = IntakeRepository().list_by_status(status=None, limit=10)
    assert len(sources) == 1
    assert sources[0].source_type == IntakeSourceType.RECEIPT
    archived = sorted(
        p.name for p in (root / INGESTED_DIR_NAME).rglob("*") if p.is_file()
    )
    assert archived == ["kvitto.pdf"]


def test_same_name_never_overwrites(test_db, root):
    _drop("Kvitton")
    second = _drop("Kvitton", content=PDF + b"2")

    assert second["filename"] == "kvitto (2).pdf"
    assert (root / "Kvitton" / "kvitto.pdf").read_bytes() == PDF


def test_a_new_file_does_not_inherit_an_existing_sidecar(test_db, root):
    (root / "Kvitton").mkdir()
    (root / "Kvitton" / "kvitto.txt").write_text("annan fils kommentar")

    assert _drop("Kvitton")["filename"] == "kvitto (2).pdf"


@pytest.mark.parametrize(
    "folder",
    ["_Problem", "_Inläst", "../utanför", "Kontoutdrag/1930 Företagskonto", "/etc"],
)
def test_only_listed_folders_can_be_written(test_db, root, folder):
    with pytest.raises(DropzoneUploadError) as err:
        _drop(folder)
    assert err.value.code == "unknown_dropzone_folder"
    assert not (root / PROBLEM_DIR_NAME).exists()


@pytest.mark.parametrize("name", ["../../x.pdf", "a/b/kvitto.pdf"])
def test_a_path_in_the_filename_is_reduced_to_its_name(test_db, root, name):
    result = _drop("Kvitton", name=name)
    assert (root / "Kvitton" / result["filename"]).exists()
    assert "/" not in result["filename"]


@pytest.mark.parametrize(
    "name,code",
    [
        ("notis.txt", "sidecar_filename"),
        (".dold.pdf", "invalid_filename"),
        ("", "invalid_filename"),
    ],
)
def test_unusable_filenames_are_refused(test_db, root, name, code):
    with pytest.raises(DropzoneUploadError) as err:
        _drop("Kvitton", name=name)
    assert err.value.code == code


def test_sie4_folder_takes_only_sie_files(test_db, root):
    with pytest.raises(DropzoneUploadError) as err:
        _drop("SIE4-import", name="kvitto.pdf")
    assert err.value.code == "not_sie4"


CSV = b"Datum;Text;Belopp\n2026-10-01;Kaffe;-45,00\n"


def test_a_statement_named_after_its_account_is_accepted(test_db, root):
    if not AccountRepository.exists("1930"):
        AccountRepository.create("1930", "Företagskonto", "asset")

    result = _drop("Kontoutdrag", name="1930 oktober.csv", content=CSV)

    assert (root / "Kontoutdrag" / result["filename"]).exists()


@pytest.mark.parametrize(
    "name,code",
    [
        ("oktober.csv", "statement_account_unknown"),
        ("9999 oktober.csv", "statement_account_missing"),
        ("1930 oktober.pdf", "not_csv_statement"),
    ],
)
def test_a_statement_the_scanner_would_refuse_is_refused_at_once(
    test_db, root, name, code
):
    if not AccountRepository.exists("1930"):
        AccountRepository.create("1930", "Företagskonto", "asset")

    with pytest.raises(DropzoneUploadError) as err:
        _drop("Kontoutdrag", name=name, content=CSV)

    assert err.value.code == code
    assert not (root / "Kontoutdrag").exists() or not list(
        (root / "Kontoutdrag").iterdir()
    )


def test_disabled_dropzone_refuses_the_upload(test_db, root, monkeypatch):
    monkeypatch.setattr(settings, "dropzone_enabled", False)
    with pytest.raises(DropzoneUploadError) as err:
        _drop("Kvitton")
    assert err.value.status == 409


def test_targets_mirror_the_share(test_db, root):
    (root / "Kontoutdrag" / "1930 Företagskonto").mkdir(parents=True)
    (root / "Representation").mkdir()
    (root / PROBLEM_DIR_NAME).mkdir()
    (root / ".stfolder").mkdir()

    targets = [(t.folder, t.kind) for t in drop_targets()]

    assert targets == [
        ("Kvitton", "voucher_source"),
        ("Leverantörsfakturor", "voucher_source"),
        ("Kundfakturor", "voucher_source"),
        ("Utlägg", "voucher_source"),
        ("Övrigt", "voucher_source"),
        ("Representation", "voucher_source"),
        ("Kontoutdrag", "bank_input"),
        ("SIE4-import", "sie4_import"),
    ]


def test_overview_lists_pending_and_problems_with_their_reason(test_db, root):
    _drop("Kvitton")
    problem = root / PROBLEM_DIR_NAME
    problem.mkdir()
    (problem / "trasig.pdf").write_bytes(PDF)
    (problem / "trasig.pdf.problem.txt").write_text(
        "Filen kunde inte läsas.\n\nFil: trasig.pdf\nFelkod: x\n"
    )

    overview = dropzone_overview()

    assert [(p["folder"], p["filename"]) for p in overview["pending"]] == [
        ("Kvitton", "kvitto.pdf")
    ]
    assert overview["targets"][0]["pending_count"] == 1
    assert [(p["filename"], p["reason"]) for p in overview["problems"]] == [
        ("trasig.pdf", "Filen kunde inte läsas.")
    ]


def test_endpoints(test_db, root, auth_headers):
    from api.main import app

    client = TestClient(app)
    response = client.post(
        "/api/v1/intake/dropzone/files",
        headers=auth_headers,
        data={"folder": "Leverantörsfakturor"},
        files=[
            ("files", ("faktura.pdf", PDF, "application/pdf")),
            ("files", ("faktura2.pdf", PDF + b"2", "application/pdf")),
            ("files", ("notis.txt", b"x", "text/plain")),
        ],
    )
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert [(r["ok"], r.get("filename"), r.get("code")) for r in results] == [
        (True, "faktura.pdf", None),
        (True, "faktura2.pdf", None),
        (False, None, "sidecar_filename"),
    ]
    assert (root / "Leverantörsfakturor" / "faktura.pdf").exists()
    assert (root / "Leverantörsfakturor" / "faktura2.pdf").exists()
    assert not (root / "Leverantörsfakturor" / "notis.txt").exists()

    refused = client.post(
        "/api/v1/intake/dropzone/files",
        headers=auth_headers,
        data={"folder": "_Problem"},
        files=[("files", ("faktura.pdf", PDF, "application/pdf"))],
    )
    assert refused.status_code == 404
    assert refused.json()["detail"]["code"] == "unknown_dropzone_folder"

    overview = client.get("/api/v1/intake/dropzone", headers=auth_headers)
    assert overview.status_code == 200
    assert [p["filename"] for p in overview.json()["pending"]] == [
        "faktura.pdf",
        "faktura2.pdf",
    ]

    assert client.get("/api/v1/intake/dropzone").status_code == 401


# --- what became of a read-in file ----------------------------------------


def _read_in(root, name: str = "kvitto.pdf", content: bytes = PDF):
    _drop("Kvitton", name=name, content=content)
    dropzone_module.get_scanner().scan_once()
    (entry,) = [e for e in dropzone_overview()["ingested"] if e["filename"] == name]
    return entry


def test_a_read_in_underlag_waiting_for_the_agent_says_so(test_db, root):
    outcome = _read_in(root)["outcome"]

    source = IntakeRepository.get_by_sha256(hashlib.sha256(PDF).hexdigest())
    assert outcome == {
        "kind": "underlag",
        "source_id": source.id,
        "status": "pending",
        "vouchers": [],
        "decision": None,
        "warning": None,
    }


def test_a_read_in_underlag_points_at_the_fiscal_year_card(test_db, root):
    from datetime import date

    from services.agent_tools import execute_tool
    from services.fiscal_years import FiscalYearService
    from services.llm import LLMCapabilities

    FiscalYearService().create(date(2025, 1, 1), date(2025, 12, 31), actor="test")
    _read_in(root)
    source = IntakeRepository().list_by_status(status=None, limit=1)[0]
    execute_tool(
        "foresla_rakenskapsar",
        {"document_date": "2026-01-01", "source_ids": [source.id]},
        actor="agent",
        capabilities=LLMCapabilities(
            cache_breakpoint=True,
            pdf_document_blocks=True,
            refusal_stop_reason=True,
            streaming=False,
        ),
    )

    outcome = dropzone_overview()["ingested"][0]["outcome"]

    assert outcome["vouchers"] == []
    assert outcome["decision"]["view_key"] == "bocker.verifikationer"
    assert outcome["decision"]["title"].startswith("Skapa räkenskapsår 2026-01-01")
    assert "Väntar på räkenskapsår" in outcome["warning"]


def test_a_file_not_in_the_books_has_no_outcome(test_db, root):
    month = root / INGESTED_DIR_NAME / "2026-11"
    month.mkdir(parents=True)
    (month / "gammal.pdf").write_bytes(b"%PDF-1.4 ur en annan databas")

    assert dropzone_overview()["ingested"][0]["outcome"] is None


def test_overview_says_why_a_pending_file_was_not_read_in(test_db, root, monkeypatch):
    _drop("Kvitton")
    scanner = dropzone_module.get_scanner()

    def trasig(*_args, **_kwargs):
        raise OSError("Read-only file system")

    monkeypatch.setattr(scanner, "_ingest_source", trasig)
    scanner.scan_once()

    [entry] = dropzone_overview()["pending"]
    assert entry["error"] == "OSError: Read-only file system"

    (root / "Kvitton" / "kvitto.pdf").unlink()
    scanner.scan_once()
    assert scanner.file_error(root / "Kvitton" / "kvitto.pdf") is None


def test_problem_without_a_source_in_the_books_is_unresolved():
    from services.dropzone_upload import _problem_resolved

    assert _problem_resolved(None) is False
    base = {"kind": "underlag", "status": "failed", "vouchers": []}
    assert _problem_resolved(base) is False
    assert _problem_resolved({**base, "status": "skipped"}) is True
    assert _problem_resolved({**base, "vouchers": [{"id": "v"}]}) is True
