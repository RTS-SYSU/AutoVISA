"""Run real HTTP acceptance and independently restore the frozen semantic context."""

from datetime import datetime, timezone
import json
from uuid import uuid4

from paper_import import ROOT, BASE, write_json
from w02_postgres import database
from platform_core.evidence.storage import Ledger, sha
from platform_core.paper_ingestion.pdf import Poppler
from platform_core.paper_ingestion.service import PaperImporter
from platform_core.semantics.service import SemanticExtractor
from platform_core.review.service import ReviewWorkspace
from w03_web_cases import exercise


def check_web():
    """Check review behavior through HTTP and a fresh restored database.

    @return Path to the persisted machine-readable report.
    @raise AssertionError If an acceptance check fails.
    """
    # All confirmations, dumps and reports belong only to this acceptance run.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
    directory = BASE / "web-checks" / stamp
    directory.mkdir(parents=True)
    report = {"status":"running","fixture_review":True}
    try:
        with database() as (dsn, pg):
            ledger = Ledger(dsn, directory / "objects")
            try:
                ledger.install()
                importer = PaperImporter(ledger, Poppler())
                importer.install()
                semantics = SemanticExtractor(importer, ROOT)
                semantics.install()
                workspace = ReviewWorkspace(semantics)
                workspace.install()

                def checkpoint():
                    """Save the current isolated database as its restoration fixture."""
                    pg("pg_dump", "--format=custom", "--no-owner", "--file", directory / "history.dump", dsn)

                exercise(workspace, ROOT, directory, checkpoint, report)
                write_json(directory / "frozen-context.json", report["frozen"])
            finally:
                ledger.close()
        with database() as (dsn, pg):
            pg("pg_restore", "--exit-on-error", "--no-owner", "--dbname", dsn, directory / "history.dump")
            ledger = Ledger(dsn, directory / "objects")
            try:
                workspace = ReviewWorkspace(SemanticExtractor(PaperImporter(ledger, Poppler()), ROOT))
                if workspace.frozen(report["frozen_id"]) != report["frozen"]:
                    raise AssertionError("Frozen context changed after restoration")
                if workspace.read(report["project"])["revision"] != report["latest_revision"]:
                    raise AssertionError("Latest revision changed after restoration")
                report["checks"]["independent_database_restore"] = "passed"
            finally:
                ledger.close()
        report["status"] = "passed"
    except Exception as error:
        report["status"], report["error"] = "failed", f"{type(error).__name__}: {error}"
        raise
    finally:
        write_json(directory / "report.json", report)
    write_json(BASE / "web-checks/latest.json", {"run":stamp,"sha256":sha((directory / "report.json").read_bytes())})
    print(json.dumps({"status":"passed","checks":len(report["checks"]),"report":str(directory / "report.json")}))
    return directory / "report.json"
