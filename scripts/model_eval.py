#!/usr/bin/env python3
"""Compare LLM models on the intake pass, on a frozen copy of the books.

Every case is one real underlag with a known booking. For each model and
case, a fresh copy of the frozen database has that case's voucher removed
and its underlag set back to pending; the document pass (`run_session`, the
same code as production) then books it, and the result is compared with the
expected rows. The live books are only ever read, never written.

    # 1. Freeze a snapshot (once; re-use it so results stay comparable)
    venv/bin/python scripts/model_eval.py freeze --name 2026-10-01 \\
        --manual /srv/appdata/bok/model-eval/manual-cases.json

    # 2. Review the answer key: <snapshot>/cases.json. The expected rows are
    #    the bookings in the books -- mostly the agent's own -- so check them,
    #    fix any that are wrong, and set "verified": true.

    # 3. Run models (resumable: finished model/case pairs are skipped)
    venv/bin/python scripts/model_eval.py run --snapshot 2026-10-01 \\
        --models opencode-go/glm-5.3,opencode-go/minimax-m3 --jobs 4

    # 4. Report (also written to <snapshot>/report.md)
    venv/bin/python scripts/model_eval.py report --snapshot 2026-10-01

A new model needs a row in `services/llm/_MODELS` (protocol and price);
then run step 3 with its id against the same snapshot. `--cases` limits a
run to some case ids, e.g. for a cheap smoke test.

Snapshots live in --root (default /srv/appdata/bok/model-eval), outside the
repo: they hold the company's books and underlag and must never be
committed.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = Path("/srv/appdata/bok/model-eval")
DEFAULT_LIVE_DB = Path("/srv/appdata/bok/data/bokfoering.db")
DEFAULT_LIVE_DATA = Path("/srv/appdata/bok/data")
DEFAULT_ENV = Path("/srv/appdata/bok/bok.env")
#: The path prefix the container stores intake files under.
CONTAINER_DATA = "/app/data"

#: Documented cache-read prices (öre per million tokens, ~10 SEK/USD as in
#: `_MODELS`) for chat-protocol models. bok's chat adapter reports no cached
#: tokens, so bok's own cost counts them as plain input; the gateway bills
#: them at this rate. Only used for the report's "gateway estimate"; a model
#: missing here is estimated at its input price (an overestimate).
GATEWAY_CHAT_CACHE_READ_ORE = {
    "opencode-go/glm-5.3": 260,
    "opencode-go/glm-5.3-flash": 30,
    "opencode-go/deepseek-v4-pro": 22,
    "opencode-go/deepseek-v4.1-flash": 3,
    "opencode-go/kimi-k3": 300,
    "opencode-go/mimo-v2.6-flash": 3,
    "opencode-go/mimo-v2.6-pro": 4,
    "opencode-go/hy3": 35,
    "opencode-go/longcat-2.0": 6,
}


# ---------------------------------------------------------------------------
# freeze
# ---------------------------------------------------------------------------


def _ro(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _expected_rows(conn: sqlite3.Connection, voucher_id: str) -> list[dict]:
    return [
        {"account": r["account_code"], "debit": r["debit"], "credit": r["credit"]}
        for r in conn.execute(
            "SELECT account_code, debit, credit FROM voucher_rows "
            "WHERE voucher_id = ? ORDER BY id",
            (voucher_id,),
        )
    ]


def _group_key(filename: str) -> str:
    """'Lön till tjänsteman maj 52000kr.pdf' -> 'lön till': the first two
    words, letters only -- enough to keep eight salary slips from crowding
    out the one-off suppliers."""
    words = re.findall(r"[^\W\d_]+", filename.lower())
    return " ".join(words[:2])


def cmd_freeze(args: argparse.Namespace) -> None:
    snap = args.root / args.name
    if snap.exists():
        sys.exit(f"{snap} exists -- freeze into a new name")
    (snap / "intake").mkdir(parents=True)
    os.chmod(args.root, 0o700)

    # A consistent copy even while the API writes (WAL): SQLite's backup API.
    src = _ro(args.live_db)
    dst = sqlite3.connect(snap / "bokfoering.db")
    src.backup(dst)
    dst.close()

    conn = _ro(snap / "bokfoering.db")
    rows = conn.execute("""
        SELECT s.id AS source_id, s.original_filename, s.stored_path,
               v.id AS voucher_id, v.series, v.number, v.date, v.description,
               v.created_by
        FROM voucher_intake_sources l
        JOIN vouchers v ON v.id = l.voucher_id
        JOIN intake_sources s ON s.id = l.intake_source_id
        JOIN periods p ON p.id = v.period_id
        WHERE v.status = 'posted' AND p.locked = 0
          AND NOT EXISTS (SELECT 1 FROM voucher_intake_unlinks u
                          WHERE u.link_id = l.id)
          AND NOT EXISTS (SELECT 1 FROM vouchers c WHERE c.correction_of = v.id)
          AND NOT EXISTS (SELECT 1 FROM correction_notes n
                          WHERE n.voucher_id = v.id)
        ORDER BY v.date DESC
        """).fetchall()

    per_group: dict[str, int] = defaultdict(int)
    cases: list[dict] = []
    for r in rows:
        key = _group_key(r["original_filename"])
        if per_group[key] >= args.per_group:
            continue
        per_group[key] += 1
        cases.append(
            {
                "id": f"{r['series']}-{r['number']}",
                "source_id": r["source_id"],
                "filename": r["original_filename"],
                "remove_voucher_id": r["voucher_id"],
                "expected": {
                    "date": r["date"],
                    "rows": _expected_rows(conn, r["voucher_id"]),
                },
                "note": f"{r['description']} (booked by {r['created_by']})",
                "verified": False,
            }
        )

    if args.manual:
        # Hand-written cases: an underlag with no booking in the books yet,
        # and the rows it should get. Same shape, minus remove_voucher_id.
        for case in json.loads(Path(args.manual).read_text()):
            case.setdefault("remove_voucher_id", None)
            case.setdefault("verified", True)
            source = conn.execute(
                "SELECT original_filename FROM intake_sources WHERE id = ?",
                (case["source_id"],),
            ).fetchone()
            if source is None:
                sys.exit(f"manual case {case['id']}: no source {case['source_id']}")
            case.setdefault("filename", source["original_filename"])
            cases.append(case)

    for case in cases:
        stored = conn.execute(
            "SELECT stored_path FROM intake_sources WHERE id = ?",
            (case["source_id"],),
        ).fetchone()["stored_path"]
        relative = Path(stored).relative_to(f"{CONTAINER_DATA}/intake")
        target = snap / "intake" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.live_data / "intake" / relative, target)

    instructions = conn.execute(
        "SELECT max(version) FROM agent_instruction_versions"
    ).fetchone()[0]
    conn.close()

    (snap / "cases.json").write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n"
    )
    commit = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    meta = {
        "name": args.name,
        "frozen_at": datetime.now().isoformat(timespec="seconds"),
        "today": date.today().isoformat(),
        "repo_commit": commit,
        "instructions_version": instructions,
        "cases": len(cases),
    }
    (snap / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"froze {len(cases)} cases into {snap}")
    print(f"review the answer key: {snap / 'cases.json'}")


# ---------------------------------------------------------------------------
# run -- the orchestrator spawns one `_worker` subprocess per model and case
# ---------------------------------------------------------------------------


def _result_path(snap: Path, model: str, case_id: str) -> Path:
    return snap / "results" / model.replace("/", "__") / f"{case_id}.json"


def cmd_run(args: argparse.Namespace) -> None:
    snap = args.root / args.snapshot
    cases = json.loads((snap / "cases.json").read_text())
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    models = args.models.split(",")

    jobs = []
    for model in models:
        for case in cases:
            path = _result_path(snap, model, case["id"])
            if path.exists() and not args.force:
                result = json.loads(path.read_text())
                if result.get("verdict") != "error" or not args.retry_errors:
                    continue
            jobs.append((model, case["id"]))
    print(f"{len(jobs)} runs ({len(models)} models x {len(cases)} cases, rest done)")

    def run_one(job: tuple[str, str]) -> str:
        model, case_id = job
        cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--root",
            str(args.root),
            "_worker",
            "--snapshot",
            args.snapshot,
            "--model",
            model,
            "--case",
            case_id,
            "--env",
            str(args.env),
        ]
        path = _result_path(snap, model, case_id)
        # A rerun replaces the old result; a stale error must not survive it.
        path.unlink(missing_ok=True)
        try:
            proc = subprocess.run(
                cmd, cwd=REPO, capture_output=True, text=True, timeout=args.timeout
            )
            failure = (proc.stderr or proc.stdout)[-2000:]
        except subprocess.TimeoutExpired:
            failure = f"timeout: no result within {args.timeout} s"
        if not path.exists():
            # The worker died or timed out before writing: record why.
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "model": model,
                        "case": case_id,
                        "verdict": "error",
                        "error": failure,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        verdict = json.loads(path.read_text()).get("verdict")
        return f"{model:34} {case_id:8} {verdict}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_one, job) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            print(future.result(), flush=True)
    cmd_report(args)


def _prepare_case_db(db_path: Path, snap: Path, case: dict) -> None:
    """In the scratch copy only: take the case's voucher out and set its
    underlag back to pending, as if it had just arrived. The append-only
    triggers are dropped first -- this copy is a test fixture, never books."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    for (name,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'trigger'"
    ).fetchall():
        conn.execute(f'DROP TRIGGER "{name}"')
    voucher_id = case.get("remove_voucher_id")
    if voucher_id:
        columns = conn.execute("""
            SELECT m.name, p.name FROM sqlite_master m, pragma_table_info(m.name) p
            WHERE m.type = 'table' AND p.name LIKE '%voucher_id'
            """).fetchall()
        for table, column in columns:
            if column == "voucher_id":
                # A row that belongs to the voucher (its rows, links, ...).
                conn.execute(
                    f'DELETE FROM "{table}" WHERE "{column}" = ?', (voucher_id,)
                )
            else:
                # A reference from something that outlives it, e.g. a bank
                # transaction's matched_voucher_id: cleared, not deleted.
                conn.execute(
                    f'UPDATE "{table}" SET "{column}" = NULL WHERE "{column}" = ?',
                    (voucher_id,),
                )
        conn.execute("DELETE FROM vouchers WHERE id = ?", (voucher_id,))
    source_id = case["source_id"]
    # What earlier passes learned about this underlag stays out of the test.
    for table in ("intake_interpretations", "intake_processing_attempts"):
        conn.execute(f"DELETE FROM {table} WHERE intake_source_id = ?", (source_id,))
    stored = conn.execute(
        "SELECT stored_path FROM intake_sources WHERE id = ?", (source_id,)
    ).fetchone()[0]
    relative = Path(stored).relative_to(f"{CONTAINER_DATA}/intake")
    conn.execute(
        "UPDATE intake_sources SET status = 'pending', stored_path = ? WHERE id = ?",
        (str(snap / "intake" / relative), source_id),
    )
    conn.commit()
    conn.close()


def _load_env(path: Path) -> None:
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _net_by_account(rows: list[dict]) -> dict[str, int]:
    net: dict[str, int] = defaultdict(int)
    for row in rows:
        net[str(row["account"])] += int(row["debit"]) - int(row["credit"])
    return {account: amount for account, amount in net.items() if amount}


def _score(expected: dict, booked: Optional[dict]) -> str:
    if booked is None:
        return "no_booking"
    want, got = _net_by_account(expected["rows"]), _net_by_account(booked["rows"])
    # A receipt in foreign currency fixes no SEK amount: the conversion
    # differs between the card statement and any rate a model uses. Such a
    # case sets "amount_tolerance" (a fraction, e.g. 0.05) and each account's
    # amount may differ by that much; the accounts must still match.
    tolerance = float(expected.get("amount_tolerance") or 0)
    same_amounts = set(want) == set(got) and all(
        abs(got[account] - amount) <= abs(amount) * tolerance
        for account, amount in want.items()
    )
    if same_amounts:
        if expected.get("date") and expected["date"] != booked["date"]:
            return "right_rows_wrong_date"
        return "correct"
    if set(want) == set(got):
        return "right_accounts_wrong_amounts"
    return "wrong"


def cmd_worker(args: argparse.Namespace) -> None:
    snap = args.root / args.snapshot
    meta = json.loads((snap / "meta.json").read_text())
    case = next(
        c for c in json.loads((snap / "cases.json").read_text()) if c["id"] == args.case
    )
    out = _result_path(snap, args.model, args.case)
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="bok-eval-") as tmp:
        db_path = Path(tmp) / "bokfoering.db"
        shutil.copy2(snap / "bokfoering.db", db_path)
        _prepare_case_db(db_path, snap, case)

        _load_env(args.env)
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["INTAKE_DIR"] = str(snap / "intake")
        sys.path.insert(0, str(REPO))

        # Imported only now, after the environment points at the scratch copy.
        from repositories.period_repo import PeriodRepository
        from services.agent_runtime import build_llm_client, compute_cost_ore
        from services.agent_session import run_session
        from services.agent_tools import derive_posting_idempotency_key
        from services.intake import IntakeService
        from services.llm import get_model_info

        # The original posting's idempotency record would answer every new
        # attempt with idempotency_key_reuse: the key is per underlag.
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "DELETE FROM idempotency_keys WHERE key = ? OR entity_id = ?",
                (
                    derive_posting_idempotency_key(case["source_id"]),
                    case.get("remove_voucher_id") or "",
                ),
            )
        before = {
            row[0]
            for row in sqlite3.connect(db_path).execute("SELECT id FROM vouchers")
        }
        client = build_llm_client(
            args.model, session_id=f"bok-eval-{args.snapshot}-{args.model}-{case['id']}"
        )
        gateway = {"cached": 0, "reasoning": 0}
        raw = getattr(client, "_client", None)
        if get_model_info(args.model).protocol == "chat" and raw is not None:
            # bok's chat adapter drops cached/reasoning token counts on
            # purpose; the report wants them, so read them off the raw reply.
            create = raw.chat.completions.create

            def counting_create(**kwargs: Any) -> Any:
                response = create(**kwargs)
                usage = getattr(response, "usage", None)
                prompt = getattr(usage, "prompt_tokens_details", None)
                completion = getattr(usage, "completion_tokens_details", None)
                gateway["cached"] += getattr(prompt, "cached_tokens", 0) or 0
                gateway["reasoning"] += getattr(completion, "reasoning_tokens", 0) or 0
                return response

            raw.chat.completions.create = counting_create

        intake = IntakeService()
        source = intake.get_source(case["source_id"])
        started = time.monotonic()
        result: dict[str, Any] = {"model": args.model, "case": case["id"]}
        try:
            outcome = run_session(
                client=client,
                source=source,
                file_bytes=intake.resolve_source_file(source).read_bytes(),
                open_periods=[
                    p for p in PeriodRepository.list_all_periods() if not p.locked
                ],
                today=date.fromisoformat(meta["today"]),
                model=args.model,
                actor="agent",
            )
        except Exception as exc:  # noqa: BLE001 -- recorded, not raised
            result.update(verdict="error", error=f"{type(exc).__name__}: {exc}")
            result["seconds"] = round(time.monotonic() - started, 1)
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            return

        seconds = round(time.monotonic() - started, 1)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        new = [
            v
            for v in conn.execute(
                "SELECT id, date, status, description FROM vouchers"
            ).fetchall()
            if v["id"] not in before
        ]
        # The posted voucher if there is one, else a draft proposal.
        new.sort(key=lambda v: v["status"] != "posted")
        booked = None
        if new:
            v = new[0]
            booked = {
                "status": v["status"],
                "date": v["date"],
                "description": v["description"],
                "rows": _expected_rows(conn, v["id"]),
            }
        conn.close()

        usage = outcome.usage
        price = get_model_info(args.model).price
        cache_ore = GATEWAY_CHAT_CACHE_READ_ORE.get(
            args.model, price.cache_read_ore_per_million_tokens
        )
        uncached = usage.input_tokens - gateway["cached"]
        result.update(
            verdict=_score(case["expected"], booked),
            outcome=outcome.kind,
            reason=outcome.reason,
            booked=booked,
            turns=len(outcome.turns),
            tools=[
                call.tool_call.name
                for turn in outcome.turns
                for call in turn.executed_tool_calls
            ],
            seconds=seconds,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_input_tokens + gateway["cached"],
            reasoning_tokens=gateway["reasoning"],
            cost_ore_bok=compute_cost_ore(args.model, usage),
            cost_ore_gateway_estimate=(
                uncached * price.input_ore_per_million_tokens
                + gateway["cached"] * cache_ore
                + usage.cache_read_input_tokens
                * price.cache_read_ore_per_million_tokens
                + usage.output_tokens * price.output_ore_per_million_tokens
            )
            // 1_000_000,
        )
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str))


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

_SYMBOL = {
    "correct": "✓",
    "right_rows_wrong_date": "≈d",
    "right_accounts_wrong_amounts": "≈a",
    "wrong": "✗",
    "no_booking": "–",
    "error": "E",
}


def cmd_report(args: argparse.Namespace) -> None:
    snap = args.root / args.snapshot
    meta = json.loads((snap / "meta.json").read_text())
    cases = json.loads((snap / "cases.json").read_text())
    expected = {case["id"]: case["expected"] for case in cases}
    results: dict[str, dict[str, dict]] = defaultdict(dict)
    for path in sorted((snap / "results").glob("*/*.json")):
        result = json.loads(path.read_text())
        if result["case"] not in expected:
            continue  # a case since removed from cases.json
        if result["verdict"] != "error":
            # Scored against the answer key as it is now, so a corrected
            # cases.json takes effect without running any model again.
            result["verdict"] = _score(expected[result["case"]], result.get("booked"))
        results[result["model"]][result["case"]] = result
    if not results:
        print("no results yet")
        return

    def mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    lines = [
        f"# Model evaluation: snapshot {meta['name']}",
        "",
        f"Frozen {meta['frozen_at']} at commit {meta['repo_commit']}, bookkeeping "
        f"instructions v{meta['instructions_version']}, {len(cases)} cases "
        f"({sum(c.get('verified', False) for c in cases)} with a verified answer "
        "key). Unverified expected rows are the books' own bookings, mostly "
        "made by the agent (GLM-5.3) -- a bias in its favour.",
        "",
        "**correct** = same net amount per account and same date. **wrong** = "
        "booked with other accounts (the harmful kind). **none** = abstained or "
        "proposed nothing (safe, but work left for a human). Costs in öre per "
        "case: *bok* is what bok's daily budget counts, *gw est.* what the "
        "gateway bills (cached tokens at their cache price).",
        "",
        "| model | runs | correct | ≈date | ≈amounts | wrong | none | errors "
        "| s/case | in tok | out tok | reasoning | öre bok | öre gw est. |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    ranked = sorted(
        results.items(),
        key=lambda kv: (
            -sum(r["verdict"] == "correct" for r in kv[1].values()),
            sum(r["verdict"] == "wrong" for r in kv[1].values()),
        ),
    )
    for model, by_case in ranked:
        done = [r for r in by_case.values() if r["verdict"] != "error"]
        count = lambda verdict: sum(  # noqa: E731
            r["verdict"] == verdict for r in by_case.values()
        )
        lines.append(
            f"| {model} | {len(by_case)} | {count('correct')} | "
            f"{count('right_rows_wrong_date')} | "
            f"{count('right_accounts_wrong_amounts')} | {count('wrong')} | "
            f"{count('no_booking')} | {count('error')} | "
            f"{mean([r['seconds'] for r in done]):.0f} | "
            f"{mean([r['input_tokens'] for r in done]):,.0f} | "
            f"{mean([r['output_tokens'] for r in done]):,.0f} | "
            f"{mean([r['reasoning_tokens'] for r in done]):,.0f} | "
            f"{mean([r['cost_ore_bok'] for r in done]):.0f} | "
            f"{mean([r['cost_ore_gateway_estimate'] for r in done]):.0f} |"
        )

    models = [model for model, _ in ranked]
    lines += [
        "",
        "## Per case",
        "",
        "✓ correct · ≈d right rows, wrong date · ≈a right accounts, wrong amounts "
        "· ✗ wrong · – no booking · E error",
        "",
        "| case | underlag | " + " | ".join(m.split("/")[-1] for m in models) + " |",
        "|---|---|" + "---|" * len(models),
    ]
    for case in cases:
        marks = [
            _SYMBOL.get(results[m].get(case["id"], {}).get("verdict", ""), " ")
            for m in models
        ]
        verified = "" if case.get("verified") else " *"
        lines.append(
            f"| {case['id']}{verified} | {case['filename'][:40]} | "
            + " | ".join(marks)
            + " |"
        )
    lines += ["", "\\* answer key not verified", ""]

    report = "\n".join(lines)
    (snap / "report.md").write_text(report)
    print(report)


# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    freeze = sub.add_parser("freeze", help="snapshot the books and pick cases")
    freeze.add_argument("--name", default=date.today().isoformat())
    freeze.add_argument("--live-db", type=Path, default=DEFAULT_LIVE_DB)
    freeze.add_argument("--live-data", type=Path, default=DEFAULT_LIVE_DATA)
    freeze.add_argument(
        "--per-group",
        type=int,
        default=2,
        help="max cases per kind of underlag (first two words of the filename)",
    )
    freeze.add_argument("--manual", help="JSON file with hand-written cases")
    freeze.set_defaults(func=cmd_freeze)

    run = sub.add_parser("run", help="run models against a snapshot")
    run.add_argument("--snapshot", required=True)
    run.add_argument("--models", required=True, help="comma-separated model ids")
    run.add_argument("--cases", help="comma-separated case ids (default: all)")
    run.add_argument("--jobs", type=int, default=4)
    run.add_argument("--timeout", type=int, default=1800, help="seconds per case")
    run.add_argument("--force", action="store_true", help="rerun finished pairs")
    run.add_argument("--retry-errors", action="store_true")
    run.add_argument("--env", type=Path, default=DEFAULT_ENV)
    run.set_defaults(func=cmd_run)

    report = sub.add_parser("report", help="summarize the results")
    report.add_argument("--snapshot", required=True)
    report.set_defaults(func=cmd_report)

    worker = sub.add_parser("_worker", help=argparse.SUPPRESS)
    worker.add_argument("--snapshot", required=True)
    worker.add_argument("--model", required=True)
    worker.add_argument("--case", required=True)
    worker.add_argument("--env", type=Path, default=DEFAULT_ENV)
    worker.set_defaults(func=cmd_worker)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
