"""Import a digital PDF, review a saved source, or run W03 acceptance."""

import argparse
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

#: Project root for imports, the reviewed paper and persistent CLI artifacts.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests/acceptance"))

from platform_core.evidence.storage import Ledger, sha
from platform_core.evidence.terms import Rejected
from platform_core.paper_ingestion.models import ImportFailure, SourceAnchor
from platform_core.paper_ingestion.pdf import Poppler
from platform_core.paper_ingestion.service import PaperImporter
from w02_postgres import database
from platform_core.semantics.models import SemanticFailure
from platform_core.semantics.service import SemanticExtractor, review_markdown

#: Local catalog and isolated test runs live under this ignored artifact directory.
BASE = ROOT / "artifacts/w03"


def write_json(path, value):
    """Atomically publish a UTF-8 JSON document.

    @param path Destination whose parent directory already exists.
    @param value JSON-serializable report, extraction or catalog pointer.
    """
    temporary = path.with_name("." + uuid4().hex + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2).encode() + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


@contextmanager
def catalog():
    """Restore the local catalog and serialize CLI operations across processes.

    @yield Tuple of importer, PostgreSQL utility runner and private connection string.
    @raise ImportFailure If the saved database dump does not match its recorded digest.
    """
    BASE.mkdir(parents=True, exist_ok=True)
    # The lock covers restore through publication; two CLIs cannot overwrite each other's imports.
    with (BASE / "catalog.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with database() as (dsn, pg):
            pointer = BASE / "catalog.json"
            if pointer.exists():
                saved = json.loads(pointer.read_bytes())
                archive = BASE / saved["dump"]
                if not archive.resolve().is_relative_to(BASE.resolve()) or sha(archive.read_bytes()) != saved["sha256"]:
                    raise ImportFailure("catalog_mismatch", "Saved database digest does not match")
                pg("pg_restore", "--exit-on-error", "--no-owner", "--dbname", dsn, archive)
            ledger = Ledger(dsn, BASE / "objects")
            try:
                ledger.install()
                importer = PaperImporter(ledger, Poppler())
                importer.install()
                yield importer, pg, dsn
            finally:
                ledger.close()


def check():
    """Run isolated acceptance and restore its source reference in a second database.

    @return Path to the completed machine-readable report.
    @raise AssertionError If an import, integrity, geometry or restore check fails.
    """
    from w03_import_cases import exercise
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
    directory = BASE / "checks" / stamp
    directory.mkdir(parents=True)
    report = {"status": "running"}
    try:
        with database() as (dsn, pg):
            ledger = Ledger(dsn, directory / "objects")
            try:
                ledger.install()
                importer = PaperImporter(ledger, Poppler())
                importer.install()
                report.update(exercise(importer, ROOT / "examples/papers/case_11/source.pdf", directory, dsn, report))
                pg("pg_dump", "--format=custom", "--no-owner", "--file", directory / "history.dump", dsn)
                write_json(directory / "extraction.json", importer.open(report["extraction_id"]).to_dict())
            finally:
                ledger.close()
        # Cross-process restoration verifies that references rely on stored data rather than in-memory state.
        with database() as (dsn, pg):
            pg("pg_restore", "--exit-on-error", "--no-owner", "--dbname", dsn, directory / "history.dump")
            ledger = Ledger(dsn, directory / "objects")
            try:
                importer = PaperImporter(ledger, Poppler())
                located = importer.resolve(SourceAnchor(**report["anchor"]))
                if located.anchor.quote != "Schedulability Algorithm":
                    raise AssertionError("Saved reference changed after restore")
                report["checks"]["database_restore_and_reference"] = "passed"
            finally:
                ledger.close()
        report["status"] = "passed"
    except Exception as error:
        report["status"], report["error"] = "failed", f"{type(error).__name__}: {error}"
        raise
    finally:
        write_json(directory / "report.json", report)
    write_json(BASE / "checks/latest.json", {"run": stamp, "sha256": sha((directory / "report.json").read_bytes())})
    print(json.dumps({"status": "passed", "checks": len(report["checks"]), "report": str(directory / "report.json")}))
    return directory / "report.json"


def main():
    """Route the CLI to acceptance, import or source review.

    @raise ImportFailure If the selected PDF, page or quote cannot be processed.
    @raise SemanticFailure If the semantic source or review draft is inconsistent.
    """
    # parser and mode distinguish import, historical review and isolated acceptance operations.
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--check-semantics", action="store_true")
    mode.add_argument("--semantic-snapshot", help="Saved semantic snapshot to reopen")
    parser.add_argument("--semantics", action="store_true", help="Extract case_11 semantic candidates")
    mode.add_argument("--show", help="Extraction ID already saved in the local catalog")
    mode.add_argument("--pdf", type=Path, help="Digital PDF to import")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--find", help="Exact text on the selected page to locate and crop")
    # args contains explicit CLI choices; extraction and semantic identities remain separate.
    args = parser.parse_args()
    if args.check:
        check()
        return
    if args.check_semantics:
        from check_w03_semantics import check_semantics
        check_semantics()
        return
    with catalog() as (importer, pg, dsn):
        # semantic_id names a review draft, while extraction_id continues to name its PDF layout.
        semantic_id, semantic = None, None
        if args.semantic_snapshot or args.semantics:
            # extractor reuses the catalog transaction and immutable source object store.
            extractor = SemanticExtractor(importer, ROOT)
            extractor.install()
        if args.semantic_snapshot:
            semantic_id = args.semantic_snapshot
            semantic = extractor.open(semantic_id)
            extraction_id = semantic.extraction_id
        else:
            extraction_id = args.show or importer.import_pdf(args.pdf or ROOT / "examples/papers/case_11/source.pdf")
            if args.semantics:
                semantic_id = extractor.extract(extraction_id)
                semantic = extractor.open(semantic_id)
        extraction = importer.open(extraction_id)
        if not 1 <= args.page <= len(extraction.pages):
            raise ImportFailure("invalid_page", str(args.page))
        # Each review gets its own outputs, preserving earlier previews and saved selection references.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
        output = BASE / "imports" / stamp
        output.mkdir(parents=True)
        anchor = None
        if args.find:
            text = extraction.pages[args.page - 1].text
            start = text.find(args.find)
            if start < 0:
                raise ImportFailure("quote_not_found", args.find)
            located = importer.locate(extraction_id, args.page, start, start + len(args.find))
            anchor = located.anchor
            write_json(output / "source-reference.json", asdict(located))
        write_json(output / "extraction.json", extraction.to_dict())
        if semantic is not None:
            write_json(output / "semantics.json", semantic.to_dict())
            (output / "semantics.md").write_text(review_markdown(semantic), encoding="utf-8")
        (output / "preview.png").write_bytes(importer.render(extraction_id, args.page, anchor))
        pg("pg_dump", "--format=custom", "--no-owner", "--file", output / "history.dump", dsn)
        write_json(BASE / "catalog.json", {"dump": str((output / "history.dump").relative_to(BASE)),
                                         "sha256": sha((output / "history.dump").read_bytes())})
        print(json.dumps({"extraction_id": extraction_id, "semantic_id": semantic_id,
                          "semantic_items": len(semantic.items) if semantic else 0,
                          "semantic_status": ("partial" if semantic.issues else "needs_review") if semantic else None,
                          "semantic_issues": list(semantic.issues) if semantic else [], "pages": len(extraction.pages),
                          "issues": [asdict(issue) for issue in extraction.issues], "output": str(output)},
                         ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ImportFailure, Rejected, SemanticFailure) as error:
        print(json.dumps({"code": error.code, "message": str(error)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
