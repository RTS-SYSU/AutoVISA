"""Launch the loopback workbench with durable local catalog checkpoints."""

from datetime import datetime, timezone
import argparse
import os
import json
import shutil
from uuid import uuid4

from paper_import import ROOT, BASE, catalog, write_json
import paper_import
from platform_core.evidence.storage import sha
from platform_core.semantics.service import SemanticExtractor
from platform_core.review.service import ReviewWorkspace
from platform_core.review.http import WorkbenchServer
from platform_core.analysis_ir.service import FormalMapping
from platform_core.reasoning.service import DerivationWorkspace
from platform_core.feedback.service import FeedbackWorkspace
from platform_core.continuation.service import ContinuationWorkspace
from platform_core.comparison.service import ComparisonWorkspace


def demo_catalog(stage="w04"):
    """Prepare an isolated browser demo from an explicitly selected successful acceptance suite.

    @param stage Acceptance suite name: w04, w05b, w05c or w06, each with an independent demo catalog.
    @return Separate catalog directory containing test confirmations and real proof receipts.
    @raise ValueError If the acceptance report is unavailable or its content identity differs.
    """
    # @var base Dedicated demo directory; existing demo edits are kept on subsequent starts.
    base = ROOT / "artifacts" / stage / "browser-test"
    if (base / "catalog.json").exists():
        return base
    # @var checks, pointer, source Latest completed acceptance input, never the user's working catalog.
    checks = ROOT / "artifacts" / stage / "checks"
    pointer = json.loads((checks / "latest.json").read_bytes())
    source = checks / pointer["run"]
    report = (source / "report.json").read_bytes()
    if sha(report) != pointer["sha256"] or json.loads(report)["status"] != "passed":
        raise ValueError(stage+" demo requires a successful acceptance report")
    base.mkdir(parents=True,exist_ok=True)
    shutil.copytree(source / "objects",base / "objects",dirs_exist_ok=True)
    shutil.copyfile(source / "history.dump",base / "history.dump")
    write_json(base / "catalog.json",{"dump":"history.dump","sha256":sha((base / "history.dump").read_bytes())})
    return base


def main():
    """Start the local workbench or run its isolated acceptance suite.

    @raise OSError If the requested loopback port is unavailable.
    """
    # args selects the port and optional isolated browser acceptance catalog.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--testing", action="store_true")
    parser.add_argument("--w04-demo", action="store_true")
    parser.add_argument("--w05b-demo", action="store_true")
    parser.add_argument("--w05c-demo", action="store_true")
    parser.add_argument("--w06-demo", action="store_true")
    parser.add_argument("--msa-demo", action="store_true")
    args = parser.parse_args()
    if args.check:
        from check_w03_web import check_web
        check_web()
        return
    # Fixture confirmations never enter the user's working catalog.
    base = demo_catalog("msa") if args.msa_demo else demo_catalog("w06") if args.w06_demo else demo_catalog("w05c") if args.w05c_demo else demo_catalog("w05b") if args.w05b_demo else demo_catalog() if args.w04_demo else ROOT / "artifacts/w03/web-browser-test" if args.testing else BASE
    paper_import.BASE = base
    with catalog() as (importer, pg, dsn):
        semantics = SemanticExtractor(importer, ROOT)
        semantics.install()
        workspace = ReviewWorkspace(semantics)
        workspace.install()
        mapping = FormalMapping(workspace, ROOT)
        mapping.install()
        derivations = DerivationWorkspace(mapping)
        derivations.install()
        feedback = FeedbackWorkspace(derivations)
        feedback.install()
        ContinuationWorkspace(feedback).install()
        ComparisonWorkspace(derivations).install()

        def checkpoint():
            """Publish a complete dump before acknowledging a Web mutation."""
            # Each dump has its own directory; the pointer advances only after successful export.
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
            output = base / "web-checkpoints" / stamp
            output.mkdir(parents=True)
            pg("pg_dump", "--format=custom", "--no-owner", "--file", output / "history.dump", dsn)
            # Flush the dump and its containing directories before advancing the durable catalog pointer.
            with (output / "history.dump").open("rb") as stream:
                os.fsync(stream.fileno())
            for path in (output, output.parent):
                descriptor = os.open(path, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            write_json(base / "catalog.json", {"dump": str((output / "history.dump").relative_to(base)),
                                              "sha256": sha((output / "history.dump").read_bytes())})
            descriptor = os.open(base, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        if args.testing and not workspace.catalog()["projects"]:
            identity = semantics.extract(importer.import_pdf(ROOT / "examples/papers/case_11/source.pdf"))
            workspace.create(identity, "case_11 · 浏览器验收")
        checkpoint()
        server = WorkbenchServer(args.port, workspace, ROOT / "web", checkpoint, args.testing or args.w04_demo or args.w05b_demo or args.w05c_demo or args.w06_demo or args.msa_demo)
        print(f"autoRTA workbench ready: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            checkpoint()
            server.server_close()


if __name__ == "__main__":
    main()
