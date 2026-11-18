"""Compare real saved executions and restore exact comparison snapshots independently."""

from datetime import datetime, timezone
import json
import shutil
from uuid import uuid4

from paper_import import ROOT, write_json
from w02_postgres import database
from platform_core.evidence.storage import Ledger, sha
from platform_core.paper_ingestion.pdf import Poppler
from platform_core.paper_ingestion.service import PaperImporter
from platform_core.feedback.service import FeedbackWorkspace
from platform_core.comparison.service import ComparisonWorkspace
from derive import module
from w05c_cases import exercise


def check():
    """Use real saved parent and child evidence without submitting new proofs in an isolated test catalog.

    @return Machine-readable report path.
    """
    # @var base, pointer, source Successful W05-b execution with real proof artifacts.
    base = ROOT/"artifacts/w05b/checks"
    pointer = json.loads((base/"latest.json").read_bytes())
    source = base/pointer["run"]
    # @var baseline Verified original report bytes identify the parent execution fixture.
    baseline = (source/"report.json").read_bytes()
    if sha(baseline) != pointer["sha256"] or json.loads(baseline)["status"] != "passed":
        raise AssertionError("W05-c requires successful W05-b acceptance")
    # @var stamp, directory Unique test identity and catalog; each test catalog and mathematical confirmation is isolated from user work.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")+uuid4().hex[:8]
    directory = ROOT/"artifacts/w05c/checks"/stamp
    directory.mkdir(parents=True)
    shutil.copytree(source/"objects",directory/"objects")
    # @var report Individual observed checks and immutable baseline references.
    report = {"status":"running","fixture_review":True,"checks":{},"base_report":pointer,
              "base_dump_sha256":sha((source/"history.dump").read_bytes())}
    print("W05-c acceptance:",directory,flush=True)
    try:
        # @var dsn, pg Isolated database connection and its native backup/restore command runner.
        with database() as (dsn,pg):
            pg("pg_restore","--exit-on-error","--no-owner","--dbname",dsn,source/"history.dump")
            # @var ledger Shared append-only store whose connection is closed after the test phase.
            ledger = Ledger(dsn,directory/"objects")
            try:
                # @var feedback, workspace Installed proposal and comparison Interfaces under test.
                feedback = FeedbackWorkspace(module(PaperImporter(ledger,Poppler())))
                feedback.install()
                workspace = ComparisonWorkspace(feedback.derivations)
                workspace.install()

                def checkpoint():
                    """Durably export fixture history before acknowledging a Web mutation."""
                    pg("pg_dump","--format=custom","--no-owner","--file",directory/"history.dump",dsn)

                # @var saved Original expected snapshots for the independent restoration comparison.
                saved = exercise(workspace,json.loads(baseline),checkpoint,report)
                write_json(directory/"split-comparison.json",saved[report["split_comparison"]])
                write_json(directory/"reverse-comparison.json",saved[report["reverse_comparison"]])
            finally:
                ledger.close()
        # @var dsn, pg Isolated database connection and its native backup/restore command runner.
        with database() as (dsn,pg):
            pg("pg_restore","--exit-on-error","--no-owner","--dbname",dsn,directory/"history.dump")
            # @var ledger Shared append-only store whose connection is closed after the test phase.
            ledger = Ledger(dsn,directory/"objects")
            try:
                workspace = ComparisonWorkspace(module(PaperImporter(ledger,Poppler())))
                # @var restored Original comparisons survive new route heads and a separate database process.
                restored = {identity:workspace.read(identity) for identity in saved}
                if restored != saved:
                    raise AssertionError("Comparison versions or evidence changed after restoration")
                report["checks"]["independent_database_restore"] = "passed"
            finally:
                ledger.close()
        report["status"] = "passed"
    # @var error Actual test failure retained in the report before propagating to the launcher.
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
