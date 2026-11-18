"""Launch the loopback workbench with durable local catalog checkpoints."""

from datetime import datetime, timezone
import argparse
import os
from uuid import uuid4

from paper_import import ROOT, BASE, catalog, write_json
from platform_core.evidence.storage import sha
from platform_core.semantics.service import SemanticExtractor
from platform_core.review.service import ReviewWorkspace
from platform_core.review.http import WorkbenchServer
from platform_core.analysis_ir.service import FormalMapping
from platform_core.reasoning.service import DerivationWorkspace
from platform_core.feedback.service import FeedbackWorkspace
from platform_core.continuation.service import ContinuationWorkspace
from platform_core.comparison.service import ComparisonWorkspace


def main():
    """Start the local workbench against its durable catalog.

    @raise OSError If the requested loopback port is unavailable.
    """
    # args selects the loopback port.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    base = BASE
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
        checkpoint()
        server = WorkbenchServer(args.port, workspace, ROOT / "web", checkpoint)
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
