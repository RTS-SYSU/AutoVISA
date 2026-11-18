"""Focused adapter regressions: actual PDF glyphs, version rejection and archived dependency use."""

from dataclasses import asdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from paper_import import ROOT, write_json
from w02_postgres import database
from platform_core.evidence.storage import Ledger
from platform_core.msa.service import MsaWorkspace
from platform_core.msa.pdf import MsaPoppler
from platform_core.msa.proof import used_resources
from platform_core.paper_ingestion.service import PaperImporter


def check():
    """Run only adapter checks that supplement the already-passed vertical acceptance.

    @return Path to a small report; existing proof checks are not rerun.
    """
    # @var base, pointer, source, saved Previously checked receipts and a separate output namespace.
    base=ROOT/"artifacts/msa/adapter-check"
    base.mkdir(parents=True,exist_ok=True)
    pointer=json.loads((ROOT/"artifacts/msa/checks/latest.json").read_bytes())
    source=ROOT/"artifacts/msa/checks"/pointer["run"]
    saved=json.loads((source/"report.json").read_bytes())
    report={"status":"running","checks":{},"source":pointer["run"]}
    with database() as (dsn,pg):
        pg("pg_restore","--exit-on-error","--no-owner","--dbname",dsn,source/"history.dump")
        ledger=Ledger(dsn,source/"objects")
        try:
            # @var workspace, proof, symbols The symbol display is derived from actual saved audit output.
            workspace=MsaWorkspace(ledger,ROOT)
            workspace.install()
            proof=workspace.result(saved["prosa"]["proof"])
            symbols=ledger.objects.get(proof["goals"][0]["evidence"]["files"]["logs/symbols"]).decode()
            assert "prosa.util.div_mod.div_ceil_monotone1" in used_resources(symbols)
            report["checks"]["display_uses_actual_rocq_dependency_declarations"]="passed"
            # @var temporary Configured incompatibility fails before proof compilation, retaining actual environment logs.
            with TemporaryDirectory(prefix="autorta-bad-profile-") as temporary:
                root=Path(temporary)
                for relative in ("configs/toolchain.json","toolchain/library-lock.json","toolchain/prosa-ceil-lock.json"):
                    path=root/relative
                    path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes((ROOT/relative).read_bytes())
                config=json.loads((root/"toolchain/prosa-ceil-lock.json").read_bytes())
                config["packages"]["rocq-prosa"]="incompatible-test-version"
                (root/"toolchain/prosa-ceil-lock.json").write_text(json.dumps(config))
                rejected=MsaWorkspace(ledger,root).prove(saved["prosa"]["mapping"],1)
                assert rejected["status"]=="open" and rejected["usage"]["checks"]==0
                assert rejected["error"]["code"]=="environment_mismatch"
                assert rejected["environment"]["build"]["files"]["logs/packages"]
                assert rejected["goals"][0]["status"]=="open"
                report["checks"]["incompatible_library_preserves_open_obligation_and_environment_log"]="passed"
                report["rejected_environment"]=rejected["id"]
            # @var importer, extraction General PDF import with a real non-case11 source and invalid glyph codes.
            importer=PaperImporter(ledger,MsaPoppler())
            importer.install()
            extraction=importer.import_pdf(ROOT.parent/"autoRTA_DAC/测试论文/rtss09-yi.pdf")
            layout=importer.open(extraction)
            assert any(issue.code=="invalid_xml_glyphs" for issue in layout.issues)
            assert layout.pages[0].words
            pdf_project=workspace.from_pdf(extraction,"rtss09-yi · 通用 PDF 验收","acceptance")
            word=layout.pages[0].words[0]
            anchor=importer.locate(extraction,1,word.start,word.end).anchor
            assert importer.resolve(anchor).anchor.quote==word.text
            (base/"page.png").write_bytes(importer.render(extraction,1))
            assert not pdf_project["document"]["items"]
            report["checks"]["non_case11_pdf_raw_glyph_warning_source_location_and_render"]="passed"
            report["pdf"]={"project":pdf_project["id"],"extraction":extraction,"anchor":asdict(anchor),"pages":len(layout.pages)}
            pg("pg_dump","--format=custom","--no-owner","--file",base/"history.dump",dsn)
            report["status"]="passed"
        finally:
            ledger.close()
            write_json(base/"report.json",report)
    print(json.dumps(report,ensure_ascii=False),flush=True)
    return base/"report.json"


if __name__=="__main__":
    check()
