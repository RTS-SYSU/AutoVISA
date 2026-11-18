"""Check actual W06 proof progress, remaining obligations and immutable parent history."""

from tempfile import TemporaryDirectory
from uuid import uuid4

from platform_core.comparison.service import ComparisonWorkspace
from platform_core.evidence.service import Evidence
from platform_core.evidence.storage import encoded, sha
from platform_core.reasoning.statements import claims
from platform_core.feedback.service_progress import TITLES


def exercise(workspace, parent_id, directory, report):
    """Execute the supported refinement through shared production Interfaces.

    @param workspace Installed continuation Interface with the real Rocq checker.
    @param parent_id Successful W05-b split execution to preserve.
    @param directory Dedicated acceptance artifact directory.
    @param report Mutable observations saved even if a later check fails.
    @return Snapshots used to verify independent database restoration.
    """
    # @var feedback, derivations, ledger Shared immutable-history and proof-checking Interfaces.
    feedback,derivations,ledger = workspace.feedback,workspace.derivations,workspace.ledger
    # @var parent, statements Original split and exact supported propositions.
    parent,statements = derivations.read(parent_id),claims()

    def expect(name, condition):
        """Record a behavioral check and emit compact progress.

        @param name Stable acceptance observation key.
        @param condition Required truth value.
        @raise AssertionError If the observed behavior violates the requirement.
        """
        if not condition:
            raise AssertionError(name)
        report["checks"][name] = "passed"
        if len(report["checks"]) % 10 == 0:
            print("W06 checks passed:",len(report["checks"]),flush=True)

    # @var proposal, review Saved concrete refinement and its fixed adoption plan.
    proposal = feedback.submit(parent_id,parent["selection"]["id"],
        {"kind":"node","key":"response_bridge"},"推进服务上下界证明，保留原合同。","W06 acceptance")
    review = workspace.review(proposal["id"])
    expect("recognized_service_refinement",proposal["intent"] == "advance_service")
    expect("concrete_same_scope_plan",review["plan"]["ready"] and not review["plan"]["requires_confirmation"])
    expect("proposal_is_not_proof",proposal["checks"]["proof"] == "not_run")
    expect("contract_not_strengthened",proposal["scope"] == {"model":"unchanged","root_statements":"unchanged"})
    expect("capacity_is_explicitly_open",any(task["key"] == "capacity_witnesses" and task["status"] == "open"
                                             for task in proposal["tasks"]))
    expect("proposal_preserves_parent",derivations.read(parent_id) == parent)
    # @var command Complete authorized operation with a per-run real-proof budget.
    command = {"proposal":proposal["id"],"preview":review["plan"]["token"],"decision":None,
               "budget":{"max_proof_attempts":24},"actor":"W06 acceptance","request_id":uuid4().hex}
    # @var child New immutable proof run; compiler failures remain visible in its events and report.
    child = workspace.adopt(**command)["result"]
    report.update(parent=parent_id,child=child["id"],proposal=proposal["id"],
                  events=child["events"],run_status=child["status"])
    (directory/"child-run.json").write_bytes(encoded(child))
    # @var nodes, edges Checked graph objects indexed by their stable meanings.
    nodes = {item["key"]:item for item in child["graph"]["nodes"]}
    edges = {item["key"]:item for item in child["graph"]["edges"]}
    expect("every_submitted_rule_accepted",all(event["outcome"] in ("complete","conditional") for event in child["events"]))
    expect("new_run_remains_partial",child["status"] == "partial" and child["end_reason"] == "strategy_exhausted")
    expect("mapping_and_scope_unchanged",all(child[key] == parent[key] for key in ("mapping","freeze","review_revision")))
    expect("parent_is_exactly_preserved",derivations.read(parent_id) == parent)
    expect("no_added_context_hypotheses",ledger.revision(child["context"])["body"]["hypotheses"] ==
           ledger.revision(parent["context"])["body"]["hypotheses"] == [])
    # @var key Every general statement receives a closed, exact-type receipt.
    for key in TITLES:
        if key == "capacity_witnesses":
            continue
        expect(key+"_proved",bool(nodes[key].get("complete")))
        # @var proof Readable evidence view includes commands and generated sources from the actual attempt.
        proof = derivations.evidence(child["id"],nodes[key]["complete"])
        expect(key+"_closed_context","Closed under the global context" in proof["assumptions"])
        expect(key+"_original_model_source","models/Service.v" in proof["sources"])
        (directory/(key+"-evidence.json")).write_bytes(encoded(proof))
    expect("service_upper_fully_proved",bool(nodes["proposed_service_upper"].get("complete")))
    expect("original_upper_statement_unchanged",nodes["proposed_service_upper"]["statement"] == statements["service_upper"])
    expect("original_lower_statement_unchanged",nodes["proposed_service_lower"]["statement"] == statements["service_lower"])
    expect("lower_implication_checked",edges["service_lower_from_capacity"]["outcome"] == "conditional")
    expect("all_lower_joint_premises_preserved",edges["service_lower_from_capacity"]["premises"] ==
           ["capacity_witnesses","capacity_implies_service_lower"])
    expect("lower_not_falsely_closed",not nodes["proposed_service_lower"].get("complete"))
    expect("capacity_has_no_invented_proof",not nodes["capacity_witnesses"].get("complete") and
           not any(edge["conclusion"] == "capacity_witnesses" for edge in child["graph"]["edges"]))
    # @var main, other Selected soundness route and separately preserved unsupported goals.
    main = next(item for item in child["plan"] if item["root"] == "goal/fig3_acceptance_soundness")
    other = [item for item in child["plan"] if item["root"] != main["root"]]
    expect("root_keeps_exact_capacity_gap",main["status"] == "unproved" and main["open"] == ["capacity_witnesses"])
    expect("other_selected_goals_preserved",other == [item for item in parent["plan"] if item["root"] != main["root"]])
    expect("bridge_not_falsely_closed",not nodes["response_bridge"].get("complete"))
    expect("checked_joint_bounds_remain_conditional",edges["proposed_bridge_from_bounds"]["outcome"] == "conditional")
    expect("source_bindings_retained",all(nodes[key]["freeze"] == parent["freeze"] and nodes[key]["source_keys"]
                                         for key in TITLES))
    expect("new_checker_profile_rechecks_old_receipts",child["checker_profile"] != parent["checker_profile"] and
           all(item["disposition"] == "needs_recheck" for item in child["inheritance"]))
    expect("actual_checks_within_budget",0 < child["usage"]["proof_attempts"] <= 24)
    expect("no_external_model_calls",child["usage"]["external_calls"] == 0)
    # @var count Idempotent adoption must not create more checks or rewrite the saved run.
    count = len(ledger.rows("SELECT id FROM attempts"))
    expect("retry_returns_original_result",workspace.adopt(**command)["result"] == child)
    expect("retry_does_not_recheck",len(ledger.rows("SELECT id FROM attempts")) == count)
    # @var comparisons, comparison Fixed-version progress comparison, including fully discharged upper bound.
    comparisons = ComparisonWorkspace(derivations)
    comparisons.install()
    comparison = comparisons.create(parent_id,child["id"],parent["selection"]["id"],child["selection"]["id"])
    report["comparison"] = comparison["id"]
    expect("comparison_uses_exact_versions",comparison["parent"]["selection"]["id"] == parent["selection"]["id"] and
           comparison["child"]["selection"]["id"] == child["selection"]["id"])
    expect("comparison_does_not_prove",comparison["proof_checks_submitted"] == 0 and
           len(ledger.rows("SELECT id FROM attempts")) == count)
    # @var scratch Real checker session for boundary examples and rejected proof substitutions.
    with TemporaryDirectory(prefix="autorta-w06-checks-") as scratch:
        # @var checker, evidence Same production checker and append-only evidence service.
        checker = derivations.checker_factory(scratch)
        evidence = Evidence(ledger,checker)
        # @var manifest The concrete endpoint fixture gets ordinary exact-type, kernel and dependency audits.
        manifest = {"files":dict(checker.base["files"]),"commands":[],"environment":checker.profile}
        try:
            checker.check(uuid4().hex,"True",
                (derivations.mapping.root/"tests/fixtures/service_checks.v").read_text(),{},manifest)
        finally:
            (directory/"boundary-checks.json").write_bytes(encoded(manifest))
        expect("boundary_examples_kernel_checked",any(item["stage"] == "kernel" and item["returncode"] == 0
                                                     for item in manifest["commands"]))
        # @var wrong An upper-bound proof must not be accepted as the lower-bound rule.
        wrong = evidence.prove(nodes["proposed_service_lower"]["goal"],
            {"derivation":"service_upper_from_execution"},[nodes["service_never_exceeds_demand"]["goal"]])
        expect("upper_cannot_prove_lower",ledger.attempt(wrong)["code"] == "target_mismatch")
        report["rejected_upper_as_lower"] = wrong
        # @var missing No constructor exists for the unresolved mathematical bridge.
        missing = evidence.prove(nodes["capacity_witnesses"]["goal"],{"derivation":"capacity_witnesses"})
        expect("missing_capacity_proof_is_rejected",ledger.attempt(missing)["code"] == "unknown_rule")
        report["rejected_missing_capacity"] = missing
        # @var omitted Missing the analytical premise prevents composing the conditional lower theorem.
        omitted = evidence.compose(nodes["proposed_service_lower"]["goal"],edges["service_lower_from_capacity"]["attempt"],
                                   [nodes["capacity_implies_service_lower"]["complete"]])
        expect("cannot_compose_without_capacity",ledger.attempt(omitted)["code"] not in ("complete","conditional"))
        report["rejected_incomplete_composition"] = omitted
    expect("negative_checks_do_not_change_saved_run",derivations.read(child["id"]) == child)
    # @var short A separate budget-limited execution retains its partial receipts and original parent.
    short = workspace.adopt(**{**command,"request_id":uuid4().hex,"budget":{"max_proof_attempts":1}})["result"]
    report["budget_child"] = short["id"]
    expect("budget_limit_saves_partial_result",short["usage"]["proof_attempts"] == 1 and
           short["end_reason"] == "budget_exhausted" and short["status"] == "partial")
    expect("budget_limit_keeps_unproved_root",all(item["status"] == "unproved" for item in short["plan"]))
    expect("budget_run_preserves_finished_run",derivations.read(child["id"]) == child)
    expect("budget_run_preserves_parent",derivations.read(parent_id) == parent)
    report["open_obligations"] = child["plan"]
    report["usage"] = child["usage"]
    # @var snapshot Independently restorable artifacts, not a recomputed claim of proof success.
    snapshot = {"parent":parent,"child":child,"budget_child":short,"comparison":comparison,"proposal":proposal}
    (directory/"snapshots.json").write_bytes(encoded(snapshot))
    return snapshot
