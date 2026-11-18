"""Reopen legacy W06 evidence after additive MSA schema installation without rerunning proofs."""

import json
from paper_import import ROOT,write_json
from w02_postgres import database
from platform_core.evidence.storage import Ledger
from platform_core.paper_ingestion.service import PaperImporter
from platform_core.paper_ingestion.pdf import Poppler
from platform_core.semantics.service import SemanticExtractor
from platform_core.review.service import ReviewWorkspace
from platform_core.analysis_ir.service import FormalMapping
from platform_core.reasoning.service import DerivationWorkspace
from platform_core.comparison.service import ComparisonWorkspace
from platform_core.msa.service import MsaWorkspace


def check():
    """Verify the existing original run and comparison using their archived environments.

    @return A small compatibility report; no new Rocq candidate is submitted.
    """
    # @var directory, previous Exact legacy acceptance snapshot, independent of the user's current catalog.
    directory=ROOT/"artifacts/w06/checks/20261111T141723Z-552bf211"
    previous=json.loads((directory/"report.json").read_bytes())
    with database() as (dsn,pg):
        pg("pg_restore","--exit-on-error","--no-owner","--dbname",dsn,directory/"history.dump")
        # @var ledger, workspace, reasoning Existing Interfaces reading original sources and proof receipts.
        ledger=Ledger(dsn,directory/"objects")
        try:
            MsaWorkspace(ledger,ROOT).install()
            workspace=ReviewWorkspace(SemanticExtractor(PaperImporter(ledger,Poppler()),ROOT))
            reasoning=DerivationWorkspace(FormalMapping(workspace,ROOT))
            child=reasoning.read(previous["child"])
            comparison=ComparisonWorkspace(reasoning).read(previous["comparison"])
            assert child["id"]==previous["child"]
            assert comparison["id"]==previous["comparison"]
            report={"status":"passed","checks":{"legacy_w06_run_and_comparison_reopen":"passed"},
                    "run":child["id"],"comparison":comparison["id"],"new_proof_checks":0}
        finally:
            ledger.close()
    output=ROOT/"artifacts/msa/legacy-check"
    output.mkdir(parents=True,exist_ok=True)
    write_json(output/"report.json",report)
    print(json.dumps(report),flush=True)
    return output/"report.json"


if __name__=="__main__":
    check()
