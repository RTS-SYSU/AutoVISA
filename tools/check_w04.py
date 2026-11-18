"""Run W04 acceptance and reopen its exact graphs in an independently restored database."""

from datetime import datetime, timezone
import json
from uuid import uuid4

from paper_import import ROOT, write_json
from w02_postgres import database
from platform_core.evidence.storage import Ledger, sha
from platform_core.paper_ingestion.pdf import Poppler
from platform_core.paper_ingestion.service import PaperImporter
from derive import module
from w04_cases import fixture, exercise


def check():
    """Execute isolated real-toolchain acceptance.

    @return Saved machine-readable report path.
    """
    # @var stamp, directory Unique run directory; all confirmations here are marked test fixtures.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")+uuid4().hex[:8]
    directory = ROOT/"artifacts/w04/checks"/stamp
    directory.mkdir(parents=True)
    report = {"status":"running","fixture_review":True,"checks":{}}
    print("W04 acceptance:",directory,flush=True)
    try:
        with database() as (dsn,pg):
            ledger = Ledger(dsn,directory/"objects")
            try:
                ledger.install()
                importer = PaperImporter(ledger,Poppler())
                importer.install()
                workspace = module(importer)
                freeze = fixture(workspace.mapping.workspace,ROOT,["fig3_acceptance_soundness","fig3_exactness"])
                mapped = workspace.mapping.compile(freeze)
                write_json(directory/"mapping.json",mapped)
                report["mapping"] = mapped["id"]
                print("Mapping:",mapped["status"],flush=True)
                run = exercise(workspace,mapped["id"],report,directory)
                report["saved"] = workspace.read(run)
                pg("pg_dump","--format=custom","--no-owner","--file",directory/"history.dump",dsn)
            finally:
                ledger.close()
        with database() as (dsn,pg):
            pg("pg_restore","--exit-on-error","--no-owner","--dbname",dsn,directory/"history.dump")
            ledger = Ledger(dsn,directory/"objects")
            try:
                workspace = module(PaperImporter(ledger,Poppler()))
                if workspace.read(run) != report.pop("saved"):
                    raise AssertionError("Independent restoration changed the run")
                report["checks"]["independent_database_restore"] = "passed"
            finally:
                ledger.close()
        report["status"] = "passed"
    except Exception as error:
        report["status"],report["error"] = "failed",f"{type(error).__name__}: {error}"
        raise
    finally:
        report.pop("saved",None)
        write_json(directory/"report.json",report)
    write_json(directory.parent/"latest.json",{"run":stamp,"sha256":sha((directory/"report.json").read_bytes())})
    print(json.dumps({"status":report["status"],"checks":len(report["checks"]),"report":str(directory/"report.json")}),flush=True)
    return directory/"report.json"
