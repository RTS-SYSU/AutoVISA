"""Map an existing frozen review."""

import argparse
from datetime import datetime, timezone
from uuid import uuid4

from paper_import import ROOT, BASE, catalog, write_json
from platform_core.evidence.storage import sha
from platform_core.semantics.service import SemanticExtractor
from platform_core.review.service import ReviewWorkspace
from platform_core.analysis_ir.service import FormalMapping


def main():
    """Run explicit freeze mapping and preserve its source, IR, Rocq code and receipt."""
    # @var parser, mode CLI arguments requiring exactly a mapping or reopening action.
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze")
    mode.add_argument("--receipt")
    # @var args Parsed mode and immutable identity supplied by the local user.
    args = parser.parse_args()
    with catalog() as (importer, pg, dsn):
        # @var workspace, mapper Restored review history and its formal mapping service.
        workspace = ReviewWorkspace(SemanticExtractor(importer, ROOT))
        workspace.install()
        mapper = FormalMapping(workspace, ROOT)
        mapper.install()
        # @var result Persisted receipt, reopened to verify every referenced artifact before export.
        result = mapper.open(args.receipt) if args.receipt else mapper.compile(args.freeze)
        result = mapper.open(result["id"])
        # Outputs are uniquely named, and the catalog advances only after the new dump is available.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
        # @var output Unique export directory for this operation and database checkpoint.
        output = BASE / "mappings" / stamp
        output.mkdir(parents=True)
        write_json(output / "mapping.json", result)
        write_json(output / "analysis-ir.json", result["ir"])
        for name in ("Mapped.v","Audit.v"):
            if name in result["files"]:
                (output / name).write_bytes(importer.ledger.objects.get(result["files"][name]))
        pg("pg_dump", "--format=custom", "--no-owner", "--file", output / "history.dump", dsn)
        write_json(BASE / "catalog.json", {"dump":str((output / "history.dump").relative_to(BASE)),
                                         "sha256":sha((output / "history.dump").read_bytes())})
        print("Mapping:", result["status"], result["id"], "Output:", output, flush=True)


if __name__ == "__main__":
    main()
