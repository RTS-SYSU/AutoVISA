"""Run real service-bound proofs and independently restore the retained partial result."""

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
from platform_core.continuation.service import ContinuationWorkspace
from platform_core.comparison.service import ComparisonWorkspace
from derive import module
from w06_cases import exercise


def check():
    """Extend a copy of successful W05-b evidence while preserving every source catalog.

    @return Path to the machine-readable report, also retained on failure.
    """
    # @var base, pointer, source Immutable parent fixture selected by the last successful report.
    base = ROOT/"artifacts/w05b/checks"
    pointer = json.loads((base/"latest.json").read_bytes())
    source = base/pointer["run"]
    # @var baseline Report bytes checked before trusting any fixture identity.
    baseline = (source/"report.json").read_bytes()
    if sha(baseline) != pointer["sha256"] or json.loads(baseline)["status"] != "passed":
        raise AssertionError("W06 requires successful W05-b split evidence")
    # @var user_catalog, original_catalog Formal user's durable pointer must remain unchanged.
    user_catalog = ROOT/"artifacts/w03/catalog.json"
    original_catalog = user_catalog.read_bytes() if user_catalog.exists() else None
    # @var stamp, directory Fresh fixture output, never the original parent or the user's working catalog.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")+uuid4().hex[:8]
    directory = ROOT/"artifacts/w06/checks"/stamp
    directory.mkdir(parents=True)
    shutil.copytree(source/"objects",directory/"objects")
    # @var report Progress observations and exact parent dump identity.
    report = {"status":"running","fixture_review":True,"checks":{},"base_report":pointer,
              "base_dump_sha256":sha((source/"history.dump").read_bytes())}
    print("W06 acceptance:",directory,flush=True)
    try:
        # @var dsn, pg Private test database and native dump/restore command runner.
        with database() as (dsn,pg):
            pg("pg_restore","--exit-on-error","--no-owner","--dbname",dsn,source/"history.dump")
            # @var ledger, workspace Production Interfaces using copied content-addressed artifacts.
            ledger = Ledger(dsn,directory/"objects")
            try:
                workspace = ContinuationWorkspace(FeedbackWorkspace(module(PaperImporter(ledger,Poppler()))))
                workspace.feedback.install()
                workspace.install()
                saved = exercise(workspace,json.loads(baseline)["child"],directory,report)
            finally:
                # Even a failing test retains all completed real attempts and diagnostics.
                pg("pg_dump","--format=custom","--no-owner","--file",directory/"history.dump",dsn)
                ledger.close()
        # @var dsn, pg Separate database process verifies independently restored history.
        with database() as (dsn,pg):
            pg("pg_restore","--exit-on-error","--no-owner","--dbname",dsn,directory/"history.dump")
            # @var ledger, derivations, restored Historical reads do not call today's proof checker.
            ledger = Ledger(dsn,directory/"objects")
            try:
                derivations = module(PaperImporter(ledger,Poppler()))
                restored = {key:derivations.read(saved[key]["id"]) for key in ("parent","child","budget_child")}
                restored["comparison"] = ComparisonWorkspace(derivations).read(saved["comparison"]["id"])
                restored["proposal"] = FeedbackWorkspace(derivations).read(saved["proposal"]["id"])
                if restored != saved:
                    raise AssertionError("W06 proof, gap, proposal or comparison history changed after restore")
                report["checks"]["independent_database_restore"] = "passed"
            finally:
                ledger.close()
        if (user_catalog.read_bytes() if user_catalog.exists() else None) != original_catalog:
            raise AssertionError("The formal user catalog changed")
        report["checks"]["formal_user_catalog_preserved"] = "passed"
        report.update(status="passed",main_target="unproved")
    # @var error Actual failure is retained before propagating to the command-line caller.
    except Exception as error:
        report.update(status="failed",error=f"{type(error).__name__}: {error}")
        raise
    finally:
        write_json(directory/"report.json",report)
    write_json(directory.parent/"latest.json",{"run":stamp,"sha256":sha((directory/"report.json").read_bytes())})
    print(json.dumps({"status":report["status"],"checks":len(report["checks"]),
                      "report":str(directory/"report.json"),"main_target":"unproved"}),flush=True)
    return directory/"report.json"


if __name__ == "__main__":
    check()
