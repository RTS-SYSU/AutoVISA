"""Run isolated W05-a acceptance using actual W04 evidence and independent database restoration."""

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
from derive import module
from w05a_cases import exercise


def check():
    """Test proposals without repeating unrelated W04 proof construction.

    @return Saved machine-readable report path.
    @raise AssertionError If a behavior or restored artifact differs from its expected value.
    """
    # @var source, pointer Successful W04 artifacts provide real checked input, not mocked proof outcomes.
    base = ROOT/"artifacts/w04/checks"
    pointer = json.loads((base/"latest.json").read_bytes())
    source = base/pointer["run"]
    baseline = (source/"report.json").read_bytes()
    if sha(baseline) != pointer["sha256"] or json.loads(baseline)["status"] != "passed":
        raise AssertionError("W05-a requires successful W04 acceptance")
    # @var directory Unique isolated output; the user's normal catalog is never opened.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")+uuid4().hex[:8]
    directory = ROOT/"artifacts/w05a/checks"/stamp
    directory.mkdir(parents=True)
    shutil.copytree(source/"objects",directory/"objects")
    report = {"status":"running","fixture_review":True,"checks":{},"base_report":pointer,
              "base_dump_sha256":sha((source/"history.dump").read_bytes()),"run":json.loads(baseline)["run"]}
    print("W05-a acceptance:",directory,flush=True)
    try:
        with database() as (dsn,pg):
            pg("pg_restore","--exit-on-error","--no-owner","--dbname",dsn,source/"history.dump")
            ledger = Ledger(dsn,directory/"objects")
            try:
                workspace = FeedbackWorkspace(module(PaperImporter(ledger,Poppler())))
                workspace.install()

                def checkpoint():
                    """Export a complete test catalog before the Web adapter acknowledges a command."""
                    pg("pg_dump","--format=custom","--no-owner","--file",directory/"history.dump",dsn)

                saved = exercise(workspace,report["run"],checkpoint,report)
                write_json(directory/"proposal.json",saved["proposal"])
            finally:
                ledger.close()
        with database() as (dsn,pg):
            pg("pg_restore","--exit-on-error","--no-owner","--dbname",dsn,directory/"history.dump")
            ledger = Ledger(dsn,directory/"objects")
            try:
                workspace = FeedbackWorkspace(module(PaperImporter(ledger,Poppler())))
                workspace.install()
                reopened = {"history":workspace.history(report["run"]),"proposal":workspace.read(report["example_proposal"]),
                            "run":workspace.derivations.read(report["run"])}
                if reopened != saved:
                    raise AssertionError("Feedback, impact or original execution changed after restoration")
                report["checks"]["independent_database_restore"] = "passed"
            finally:
                ledger.close()
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed",error=f"{type(error).__name__}: {error}")
        raise
    finally:
        write_json(directory/"report.json",report)
    write_json(directory.parent/"latest.json",{"run":stamp,"sha256":sha((directory/"report.json").read_bytes())})
    print(json.dumps({"status":"passed","checks":len(report["checks"]),"report":str(directory/"report.json")}),flush=True)
    return directory/"report.json"


if __name__ == "__main__":
    check()
