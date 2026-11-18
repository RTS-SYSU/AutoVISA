"""Run isolated W03 semantic acceptance and verify restoration in a fresh database."""

from datetime import datetime, timezone
import json
from uuid import uuid4

from platform_core.evidence.storage import Ledger, sha
from platform_core.paper_ingestion.pdf import Poppler
from platform_core.paper_ingestion.service import PaperImporter
from platform_core.semantics.service import SemanticExtractor
from paper_import import ROOT, BASE, write_json
from w02_postgres import database
from w03_semantic_cases import exercise


def check_semantics():
    """Run real-source extraction checks and independently restore all saved references.

    @return Path to the completed JSON report.
    @raise AssertionError If extraction, integrity or restoration violates the contract.
    """
    # Each run owns its PostgreSQL database, objects and report; failed evidence is retained.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
    directory = BASE / "semantic-checks" / stamp
    directory.mkdir(parents=True)
    report = {"status": "running"}
    try:
        with database() as (dsn, pg):
            # ledger owns the temporary connection; importer and extractor share its object store.
            ledger = Ledger(dsn, directory / "objects")
            try:
                ledger.install()
                importer = PaperImporter(ledger, Poppler())
                importer.install()
                extractor = SemanticExtractor(importer, ROOT)
                extractor.install()
                exercise(extractor, ROOT / "examples/papers/case_11/source.pdf", directory, dsn, ROOT, report)
                write_json(directory / "semantics.json", extractor.open(report["semantic_id"]).to_dict())
                pg("pg_dump", "--format=custom", "--no-owner", "--file", directory / "history.dump", dsn)
            finally:
                ledger.close()
        # Restore after the producing database has stopped, then check all source identities again.
        with database() as (dsn, pg):
            pg("pg_restore", "--exit-on-error", "--no-owner", "--dbname", dsn, directory / "history.dump")
            ledger = Ledger(dsn, directory / "objects")
            try:
                importer = PaperImporter(ledger, Poppler())
                restored = SemanticExtractor(importer, ROOT).open(report["semantic_id"])
                # JSON converts tuples to lists, so compare canonical JSON-compatible containers.
                if json.loads(json.dumps(restored.to_dict())) != json.loads((directory / "semantics.json").read_bytes()):
                    raise AssertionError("Semantic content changed after database restore")
                for item in restored.items:
                    for evidence in item.sources:
                        for anchor in evidence.anchors:
                            if importer.resolve(anchor).anchor != anchor:
                                raise AssertionError("Source reference changed after database restore")
                report["checks"]["fresh_database_restoration"] = "passed"
            finally:
                ledger.close()
        report["status"] = "passed"
    except Exception as error:
        report["status"], report["error"] = "failed", f"{type(error).__name__}: {error}"
        raise
    finally:
        write_json(directory / "report.json", report)
    write_json(BASE / "semantic-checks/latest.json", {"run": stamp, "sha256": sha((directory / "report.json").read_bytes())})
    print(json.dumps({"status": "passed", "checks": len(report["checks"]),
                      "report": str(directory / "report.json")}))
    return directory / "report.json"
