"""Exercise independent MSA input against real PostgreSQL and durable artifacts."""

from datetime import datetime, timezone
from uuid import uuid4
import json

from paper_import import ROOT, write_json
from w02_postgres import database
from platform_core.evidence.storage import Ledger, sha


def check():
    """Run the current vertical slice and retain failures as well as successes.

    @return Path to this run's report.
    """
    # @var stamp, directory Isolated acceptance identity and output directory.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")+uuid4().hex[:8]
    directory = ROOT/"artifacts/msa/checks"/stamp
    directory.mkdir(parents=True)
    # @var report Result retained even when an expected red test fails.
    report = {"status":"running","checks":{}}
    print("MSA acceptance:",directory,flush=True)
    try:
        from platform_core.msa.service import MsaWorkspace
        from msa_cases import exercise
        # @var dsn, pg Private database and its backup command runner.
        with database() as (dsn,pg):
            # @var ledger, workspace Actual persistence and the public workflow Interface.
            ledger = Ledger(dsn,directory/"objects")
            try:
                workspace = MsaWorkspace(ledger,ROOT)
                workspace.install()
                report["project"] = exercise(workspace,report)
            finally:
                pg("pg_dump","--format=custom","--no-owner","--file",directory/"history.dump",dsn)
                ledger.close()
        # @var restored A separate database must reopen exact saved evidence without recompiling it.
        with database() as (dsn,pg):
            pg("pg_restore","--exit-on-error","--no-owner","--dbname",dsn,directory/"history.dump")
            restored = Ledger(dsn,directory/"objects")
            try:
                workspace = MsaWorkspace(restored,ROOT)
                assert workspace.result(report["proof"])["status"]=="proved"
                assert workspace.result(report["prosa"]["proof"])["status"]=="proved"
                assert workspace.result(report["failed_proof"])["status"]=="open"
                assert workspace.frozen(report["freeze"])["semantic_review"]=="confirmed"
                report["checks"]["database_restore_preserves_proofs_failures_and_versions"]="passed"
            finally:
                restored.close()
        report["status"] = "passed"
    # @var error Actual failure, including the initial missing implementation.
    except Exception as error:
        report.update(status="failed",error=f"{type(error).__name__}: {error}")
        raise
    finally:
        write_json(directory/"report.json",report)
    write_json(directory.parent/"latest.json",{"run":stamp,"sha256":sha((directory/"report.json").read_bytes())})
    print(json.dumps({"status":report["status"],"checks":len(report["checks"]),"report":str(directory/"report.json")}),flush=True)
    return directory/"report.json"


if __name__ == "__main__":
    check()
