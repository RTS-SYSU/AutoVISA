"""Run W02 acceptance or inspect one goal from the last completed PostgreSQL dump."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

#: Source checkout used to resolve imports and the reviewed toolchain configuration.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests/acceptance"))

from platform_core.evidence.rocq import Rocq
from platform_core.evidence.service import Evidence
from platform_core.evidence.storage import Ledger, Objects, sha
from w02_cases import exercise
from w02_postgres import database

#: Parent of run directories and the pointer to the most recent successful run.
BASE = ROOT / "artifacts/w02"


def write_json(path, obj):
    """Publish a complete JSON file by replacing its destination atomically.

    @param path Destination path whose parent directory already exists.
    @param obj JSON-serializable report, history or latest-run pointer.
    @raise OSError If the temporary file cannot be written or published.
    """
    # tmp is a unique sibling of the destination so publication stays on the same filesystem.
    tmp = path.with_name("." + uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, path)


def restore(run, dsn, pg, report):
    """Restore a saved run into a prepared database after checking its dump digest.

    @param run Directory containing the run's history.dump.
    @param dsn Connection string for the empty destination database.
    @param pg Callable that runs a utility from the selected PostgreSQL installation.
    @param report Decoded run report containing the expected dump_sha256 value.
    @raise ValueError If the dump bytes differ from the recorded digest.
    @raise RuntimeError If pg_restore reports a failure.
    """
    # dump is the archive whose exact bytes must match the report before pg_restore starts.
    dump = run / "history.dump"
    if sha(dump.read_bytes()) != report["dump_sha256"]:
        raise ValueError("Database dump digest mismatch")
    pg("pg_restore", "--exit-on-error", "--no-owner", "--dbname", dsn, dump)


def main():
    """Run acceptance or print one restored goal history, as selected by the CLI.

    @raise ValueError If the published report or dump fails digest verification.
    @raise AssertionError If an acceptance case or cross-restart check fails.
    @raise Rejected If the checker environment or requested goal cannot be resolved.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show", metavar="GOAL", help="Restore the latest dump and query a goal by name")
    # args.show is the logical goal name in query mode and None in acceptance mode.
    args = parser.parse_args()
    if args.show:
        # pointer pins both the run directory and the expected digest of its report.
        pointer = json.loads((BASE / "latest.json").read_bytes())
        run = BASE / pointer["run"]
        raw = (run / "report.json").read_bytes()
        if sha(raw) != pointer["report_sha256"]:
            raise ValueError("Acceptance report digest mismatch")
        report = json.loads(raw)
        with database() as (dsn, pg), TemporaryDirectory() as work:
            restore(run, dsn, pg, report)
            db = Ledger(dsn, run / "objects")
            try:
                # A query can rebuild the environment without adding objects to the saved run.
                service = Evidence(db, Rocq(ROOT, work, Objects(Path(work) / "scratch-objects")))
                print(json.dumps(service.history(args.show), ensure_ascii=False, indent=2))
            finally:
                db.close()
        return

    # stamp combines UTC time with a random suffix so concurrent runs get separate output directories.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
    run = BASE / stamp
    run.mkdir(parents=True)
    # report accumulates check outcomes and goal transitions, including diagnostics on failure.
    report = {"run": stamp, "status": "running", "checks": {}, "timeline": [], "backend": "PostgreSQL"}
    print("Starting W02 acceptance:", run, flush=True)
    try:
        with database() as (dsn, pg), TemporaryDirectory() as work:
            db = Ledger(dsn, run / "objects")
            try:
                db.install()
                # checker uses a fresh model build; db links attempts to objects under this run directory.
                checker = Rocq(ROOT, work, db.objects)
                report["profile"] = checker.profile_id
                report["postgres_version"] = pg("postgres", "--version").decode().strip()
                service = Evidence(db, checker)
                exercise(service, dsn, run / "objects", report)
                pg("pg_dump", "--format=custom", "--no-owner", "--file", run / "history.dump", dsn)
            finally:
                db.close()
        report["dump_sha256"] = sha((run / "history.dump").read_bytes())
        # Restore into a second server and rebuild the checker in a new directory.
        # This catches receipts that secretly depended on files in the original worker.
        with database() as (dsn, pg), TemporaryDirectory() as work:
            restore(run, dsn, pg, report)
            db = Ledger(dsn, run / "objects")
            try:
                service = Evidence(db, Rocq(ROOT, work, db.objects))
                # restored is the goal's current state; receipt and manifest describe its earlier complete proof.
                restored = service.history("joint-demo")
                receipt = db.attempt(report["ids"]["joint_application"])
                manifest = db.manifest(receipt, verify=True)
                if restored["state"] != "open" or receipt["code"] != "complete" or not manifest["libraries"]:
                    raise AssertionError("Restored history lost evidence or revision state")
                report["checks"]["independent_database_restore"] = "passed"
                # The restore route contains a target revision followed by a rule attempt and a premise attempt.
                scoped_goal, rule, premise = report["restore_route"]
                replay = service.compose(scoped_goal, rule, [premise])
                # replay identifies the new attempt created after restart; replayed includes its actual checker result.
                replayed = db.attempt(replay)
                if replayed["code"] != "complete" or service.history("scoped-demo")["state"] != "checked":
                    raise AssertionError(f"Restored proof could not be composed: {replayed['detail']}")
                report["checks"]["fresh_kernel_reuses_scoped_receipts"] = {
                    "status": "passed", "attempt": replay, "result": replayed["code"]}
                # Save the new attempt too: every receipt cited by the report must remain queryable.
                pg("pg_dump", "--format=custom", "--no-owner", "--file", run / "history.dump", dsn)
                report["dump_sha256"] = sha((run / "history.dump").read_bytes())
                report["counts"] = db.rows("SELECT count(*) AS attempts, count(*) FILTER "
                       "(WHERE code='conditional') AS conditional, count(*) FILTER (WHERE code='complete') "
                       "AS complete FROM outcomes")[0]
                write_json(run / "joint-history.json", restored)
                # This independent query keeps the paper's main target separate from the proved fixtures.
                main_goal = service.history("case11-fig3-acceptance-soundness-int-v1")
                if main_goal["issues"] or main_goal["state"] != "open" or main_goal["attempts"]:
                    raise AssertionError("The open case11 target should remain untouched")
                report["main_goal"] = {"revision": main_goal["current"], "state": main_goal["state"]}
            finally:
                db.close()
        report["status"] = "passed"
    except Exception as exc:
        report["status"], report["error"] = "failed", f"{type(exc).__name__}: {exc}"
        raise
    finally:
        write_json(run / "report.json", report)
    # Failed or interrupted runs must never replace the last usable history pointer.
    write_json(BASE / "latest.json", {"run": stamp, "report_sha256": sha((run / "report.json").read_bytes())})
    print(f"PASS: {len(report['checks'])} checks; {report['counts']}; case11: open.", flush=True)


if __name__ == "__main__":
    main()

