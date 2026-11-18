"""Behavioral acceptance for source-independent MSA workspaces."""


import json
from copy import deepcopy
from platform_core.evidence.terms import Rejected


def exercise(workspace, report):
    """Check the first public MSA workflow without a PDF or model API.

    @param workspace Production MSA workspace over the real local ledger.
    @param report Mutable acceptance observations.
    @return Project identity retained for restoration.
    """
    # @var project A new user workspace must contain no borrowed case assumptions.
    project = workspace.create("空白实时分析", None, "acceptance")
    assert project["document"]["items"] == []
    assert project["document"]["symbols"] == []
    assert workspace.read(project["id"])["revision"] == project["revision"]
    report["checks"]["blank_msa_without_pdf_or_case_defaults"] = "passed"
    # @var document Imported mathematics is independently authored and initially unreviewed.
    document = json.loads((workspace.root/"examples/msa/execution-budget.json").read_bytes())
    project = workspace.create("独立预算案例",document,"acceptance")
    assert project["blockers"], "Imported content must not be pre-confirmed"
    # @var reviewed Exact same mathematical content after an explicit fixture review.
    reviewed = deepcopy(project["document"])
    for entry in reviewed["symbols"]+reviewed["items"]:
        entry["decision"] = "confirmed"
    preview = workspace.preview(project["id"],project["revision"],reviewed)
    revised = workspace.commit(project["id"],project["revision"],reviewed,preview["token"],"fixture reviewer","已核对预算子问题。")
    frozen = workspace.freeze(project["id"],revised["revision"],"fixture reviewer","冻结已核对输入。")
    assert workspace.frozen(frozen["id"])["document"] == reviewed
    assert workspace.read(project["id"],project["revision"])["document"] == document
    assert workspace.export(project["id"],revised["revision"]) == reviewed
    report["checks"]["review_freeze_and_export_without_paper"] = "passed"
    report["freeze"] = frozen["id"]
    # @var mapped A typed translation cannot itself prove the selected guarantee.
    mapped = workspace.map(frozen["id"])
    assert mapped["status"] == "mapped", mapped
    assert mapped["goals"][0]["key"] == "own_fits"
    assert mapped["goals"][0]["proof_status"] == "unproved"
    assert mapped["bindings"]["own_fits"]["sources"] == reviewed["items"][-1]["sources"]
    report["checks"]["independent_msa_typed_mapping_with_sources"] = "passed"
    report["mapping"] = mapped["id"]
    # @var proof Actual exact-type, kernel, assumption and dependency checks.
    proof = workspace.prove(mapped["id"],1)
    assert proof["status"]=="proved", proof
    assert proof["usage"]["checks"]==1 and proof["usage"]["model_calls"]==0
    assert proof["goals"][0]["evidence"]["libraries"]
    report["checks"]["real_rocq_proves_independent_budget_target"] = "passed"
    report["proof"] = proof["id"]
    # @var reuse_document, reuse_project Library route uses different mathematics and declared resources.
    reuse_document = json.loads((workspace.root/"examples/msa/prosa-ceil.json").read_bytes())
    reuse_project = reviewed_project(workspace,reuse_document)
    reuse_mapping = workspace.map(reuse_project["id"])
    reuse_proof = workspace.prove(reuse_mapping["id"],1)
    assert reuse_proof["status"]=="proved", reuse_proof
    assert reuse_proof["route"]=="library_reuse"
    assert "prosa.util.div_mod.div_ceil_monotone1" in reuse_proof["goals"][0]["reused_resources"]
    assert any("/prosa/" in key for key in reuse_proof["goals"][0]["evidence"]["libraries"])
    report["checks"]["prosa_reflection_exact_type_kernel_and_dependency_audits"] = "passed"
    report["prosa"] = {"freeze":reuse_project["id"],"mapping":reuse_mapping["id"],"proof":reuse_proof["id"]}
    # @var unsupported Reviewed continuous-time input is retained but never silently discretized.
    unsupported = deepcopy(document)
    unsupported["scope"]["time"]="continuous"
    blocked = workspace.map(reviewed_project(workspace,unsupported)["id"])
    assert blocked["status"]=="blocked" and blocked["gaps"][0]["code"]=="unsupported_scope"
    # @var missing Removing the essential premise must leave the selected target unproved.
    missing = deepcopy(document)
    missing["items"]=[item for item in missing["items"] if item["category"]!="model"]
    invalid_mapping = workspace.map(reviewed_project(workspace,missing)["id"])
    failed = workspace.prove(invalid_mapping["id"],1)
    assert failed["status"]=="open" and failed["goals"][0]["reason"]=="type_error"
    assert failed["goals"][0]["evidence"]["files"]
    report["checks"]["semantic_mismatch_and_missing_premise_remain_open"] = "passed"
    # @var altered New mathematical assumptions invalidate review and leave original proof history intact.
    altered = deepcopy(reviewed)
    altered["items"][1]["expression"]["op"]="lt"
    change = workspace.preview(project["id"],revised["revision"],altered)
    assert change["mathematics_changed"]
    assert change["document"]["items"][-1]["decision"]=="pending"
    try:
        workspace.commit(project["id"],revised["revision"],altered,"wrong-token","acceptance","stale preview")
        raise AssertionError("A stale preview was accepted")
    except Rejected as error:
        assert error.code=="preview_mismatch"
    assert workspace.result(proof["id"])["status"]=="proved"
    assert workspace.frozen(frozen["id"])["document"]==reviewed
    report["checks"]["mathematical_review_invalidation_and_original_history"] = "passed"
    report["failed_proof"]=failed["id"]
    return project["id"]


def reviewed_project(workspace,document):
    """Create an isolated fixture with explicit human-review simulation.

    @param workspace Real persistence Interface under acceptance.
    @param document Versioned MSA fixture.
    @return Immutable reviewed context used by subsequent checks.
    """
    # @var project, reviewed Initial import and explicitly reviewed fixture copy.
    project = workspace.create(document["title"],document,"acceptance")
    reviewed = deepcopy(project["document"])
    for entry in reviewed["symbols"]+reviewed["items"]:
        entry["decision"]="confirmed"
    preview = workspace.preview(project["id"],project["revision"],reviewed)
    saved = workspace.commit(project["id"],project["revision"],reviewed,preview["token"],"fixture reviewer","已核对独立验收输入。")
    return workspace.freeze(project["id"],saved["revision"],"fixture reviewer","冻结验收上下文。")
