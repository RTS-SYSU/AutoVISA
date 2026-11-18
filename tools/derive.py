"""Run, reopen or verify the local bidirectional derivation workspace."""

import argparse
from datetime import datetime, timezone
from uuid import uuid4

from paper_import import ROOT, BASE, catalog, write_json
from platform_core.evidence.storage import sha
from platform_core.evidence.rocq import Rocq
from platform_core.semantics.service import SemanticExtractor
from platform_core.review.service import ReviewWorkspace
from platform_core.analysis_ir.service import FormalMapping
from platform_core.reasoning.service import DerivationWorkspace


def module(importer):
    """Bind the shared catalog and actual checker behind the derivation Interface.

    @param importer Installed source module over the local ledger.
    @return Installed derivation workspace.
    """
    # @var review, mapping Existing upstream modules restored from the same immutable catalog.
    review = ReviewWorkspace(SemanticExtractor(importer,ROOT))
    review.semantics.install()
    review.install()
    mapping = FormalMapping(review,ROOT)
    mapping.install()
    workspace = DerivationWorkspace(mapping,lambda directory:Rocq(ROOT,directory,importer.ledger.objects))
    workspace.install()
    return workspace


def main():
    """Execute one derivation action and publish its durable catalog checkpoint."""
    # @var parser, mode Exactly one requested action, without implicitly confirming project mathematics.
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mapping")
    mode.add_argument("--run")
    mode.add_argument("--check",action="store_true")
    args = parser.parse_args()
    if args.check:
        from check_w04 import check
        check()
        return
    with catalog() as (importer,pg,dsn):
        # @var workspace, result Shared Interface and its saved graph with actual evidence.
        workspace = module(importer)
        result = workspace.derive(args.mapping) if args.mapping else workspace.read(args.run)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")+uuid4().hex[:8]
        output = BASE/"derivations"/stamp
        output.mkdir(parents=True)
        write_json(output/"run.json",result)
        pg("pg_dump","--format=custom","--no-owner","--file",output/"history.dump",dsn)
        write_json(BASE/"catalog.json",{"dump":str((output/"history.dump").relative_to(BASE)),
                                      "sha256":sha((output/"history.dump").read_bytes())})
        print("Run:",result["id"],result["status"],"Output:",output,flush=True)


if __name__ == "__main__":
    main()
