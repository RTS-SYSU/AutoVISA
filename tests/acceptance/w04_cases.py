"""Exercise the public derivation Interface using reviewed test fixtures and real proof receipts."""

from copy import deepcopy
import json

from platform_core.evidence.terms import Rejected
from platform_core.reasoning.graph import plan


def fixture(workspace, root, selected=None):
    """Freeze a clearly labeled case_11 fixture without touching a real user's review.

    @param workspace Installed review workspace in an isolated acceptance catalog.
    @param root Checkout containing the source PDF.
    @param selected Optional complete selected-goal list for coverage tests.
    @return Frozen fixture identity.
    """
    # @var semantic, current Original extracted source and the fixture's pending first revision.
    workspace.semantics.install()
    semantic = workspace.semantics.extract(workspace.importer.import_pdf(root/"examples/papers/case_11/source.pdf"))
    current = workspace.create(semantic,"W04 · 隔离推导验收")
    patch = {"items":{item["key"]:{"decision":"confirmed"} for item in current["state"]["items"]
                      if item["decision"] != "excluded"}}
    if selected:
        patch["selected"] = selected
    preview = workspace.prepare(current["project"],current["revision"],patch)
    current = workspace.commit(current["project"],current["revision"],patch,preview["token"],
                               "w04-acceptance-fixture","工程验收夹具，不代表用户数学确认。")
    preview = workspace.preview_freeze(current["project"],current["revision"])
    return workspace.freeze(current["project"],current["revision"],preview["token"],"w04-acceptance-fixture")["id"]


def exercise(workspace, mapping, report, directory):
    """Run both reasoning branches, compose a checked alignment and retain open scheduling work.

    @param workspace Installed DerivationWorkspace using the real checker factory.
    @param mapping Successful, partially supported W03 fixture receipt identity.
    @param report Mutable acceptance report preserving observations on failure.
    @param directory Artifact directory receiving the full run even when an assertion fails.
    @return Saved execution identity for independent database restoration.
    """
    # @var ledger Shared evidence history; checks is the retained assertion journal.
    ledger,checks = workspace.ledger,report["checks"]

    def expect(name, actual, expected):
        """Compare an observable Interface result.

        @param name Stable acceptance identity.
        @param actual Observed value.
        @param expected Required value.
        """
        if actual != expected:
            raise AssertionError(f"{name}: {actual!r} != {expected!r}")
        checks[name] = "passed"

    def reject(name, action, code):
        """Require a precise selection or integrity rejection.

        @param name Stable observation name.
        @param action Zero-argument action through the relevant Interface.
        @param code Expected rejection code.
        """
        try:
            action()
        except Rejected as error:
            expect(name,error.code,code)
        else:
            raise AssertionError(name+" unexpectedly succeeded")

    # @var run Persisted actual execution, including all Rocq attempts and remaining obligations.
    from w04_http import execute
    run = execute(workspace,mapping,expect)
    (directory/"run.json").write_text(json.dumps(run,ensure_ascii=False,indent=2),encoding="utf-8")
    report["run"] = run["id"]
    expect("actual_rule_execution",run["execution"],"local_rules")
    expect("partial_with_open_main",run["status"],"partial")
    nodes = {item["key"]:item for item in run["graph"]["nodes"]}
    edges = {item["key"]:item for item in run["graph"]["edges"]}
    for key in ("trace_witness","trace_guard","cost_lower_bound","task_witnesses"):
        expect(key+"_proved",bool(nodes[key].get("complete")),True)
    expect("alignment_checked",run["graph"]["alignments"][0]["status"],"checked")
    expect("alignment_retains_instantiation",set(run["graph"]["alignments"][0]["instantiation"]),{"hp","p","t"})
    expect("root_joint_premises",edges["via_witness"]["premises"],["task_witnesses","response_bridge"])
    expect("root_only_conditional",edges["via_witness"]["outcome"],"conditional")
    root = "goal/fig3_acceptance_soundness"
    primary = next(item for item in run["plan"] if item["root"] == root)
    expect("root_remains_unproved",primary["status"],"unproved")
    expect("scheduling_bridge_remains_open",primary["open"],["response_bridge"])
    expect("unsupported_goal_retained","goal/fig3_exactness" in nodes,True)
    expect("unsupported_goal_has_no_fake_term",nodes["goal/fig3_exactness"]["statement"],None)
    requests = [json.loads(ledger.objects.get(run["files"]["input/"+side+".json"])) for side in ("forward","backward")]
    expect("initial_peer_inputs_isolated",[request["peer_inputs"] for request in requests],[[],[]])
    expect("same_fixed_ir",requests[0]["ir"],requests[1]["ir"])
    expect("source_revision_preserved",all(item["review_revision"] == run["review_revision"] for item in nodes.values()),True)
    expect("source_bindings_resolve",all(key in requests[0]["ir"]["bindings"] for item in nodes.values() for key in item["source_keys"]),True)
    expect("material_roles_allowed",all(item["material_role"] in ("model_definition","analysis_definition","guarantee_statement")
                                      for item in requests[0]["materials"]),True)
    expect("backward_request_has_no_forward_graph","forward" not in requests[1] and "output" not in requests[1],True)
    # Every accepted receipt must include independent kernel logs and an actual loaded library closure.
    for relation in edges.values():
        receipt = ledger.manifest(ledger.attempt(relation["attempt"]),verify=True)
        expect(relation["key"]+"_real_kernel","logs/kernel" in receipt["files"] and bool(receipt["libraries"]),True)
        expect(relation["key"]+"_no_rta_library",not any("prosa" in name.lower() for name in receipt["libraries"]),True)
    # A typed but stricter obligation must fail exact-type conversion instead of inheriting the alignment.
    from tempfile import TemporaryDirectory
    from pathlib import Path
    from platform_core.evidence.service import Evidence
    with TemporaryDirectory(prefix="autorta-w04-negative-") as temporary:
        evidence = Evidence(ledger,workspace.checker_factory(Path(temporary)/"checker"))
        changed = deepcopy(nodes["task_witnesses"]["statement"])

        def tighten(tree):
            """Replace the witness deadline bound by a strict bound.

            @param tree Mutable typed expression used only by this negative fixture.
            """
            if isinstance(tree,dict):
                if tree.get("op") == "exists":
                    tree["body"]["left"]["op"] = "lt"
                else:
                    for value in tree.values():
                        tighten(value)
            elif isinstance(tree,list):
                for value in tree:
                    tighten(value)

        tighten(changed)
        target = evidence.goal("w04-negative/"+run["id"],run["context"],{"analysis":changed})
        attempt = evidence.prove(target,{"derivation":"instantiate_witness"},[nodes["trace_witness"]["goal"]])
        expect("changed_interval_rejects_alignment",ledger.attempt(attempt)["code"],"target_mismatch")
        reverse = evidence.prove(nodes["trace_witness"]["goal"],{"derivation":"instantiate_witness"},[nodes["task_witnesses"]["goal"]])
        expect("reversed_alignment_rejected",ledger.attempt(reverse)["code"],"target_mismatch")
        omitted = evidence.compose(nodes[root]["goal"],edges["via_witness"]["attempt"],[nodes["task_witnesses"]["complete"]])
        expect("joint_premise_cannot_be_omitted",ledger.attempt(omitted)["code"],"missing_premise")
        denied = evidence.prove(nodes[root]["goal"],{"symbol":"Prosa.existing_RTA"})
        expect("excluded_rta_symbol_rejected",ledger.attempt(denied)["code"],"unapproved_symbol")
    # Keep an independently sufficient backward route even when it has no forward support.
    choices = dict(run["selection"]["choices"])
    choices[root] = "via_jobs"
    selection = workspace.select(run["id"],run["selection"]["id"],choices)
    direct = next(item for item in selection["plan"] if item["root"] == root)
    expect("backward_only_route_retained",direct["open"],["direct_jobs"])
    expect("backward_route_independent",set(direct["required"]),{root,"direct_jobs"})
    reject("stale_selection_rejected",lambda:workspace.select(run["id"],run["selection"]["id"],choices),"revision_conflict")
    reject("wrong_target_route_rejected",lambda:workspace.select(run["id"],selection["id"],{root:"derive_trace_witness"}),"route_mismatch")
    restored = workspace.read(run["id"])
    expect("selection_history_preserved",len(restored["selection_history"]),2)
    expect("candidate_graph_unchanged",restored["graph"],run["graph"])
    # Exercise the planner's public graph contract with a cyclic selected route.
    cyclic = deepcopy(run["graph"])
    cyclic["edges"].append({"key":"cycle","premises":[root],"conclusion":"response_bridge","outcome":"conditional"})
    cyclic_choices = dict(run["selection"]["choices"])
    cyclic_choices["response_bridge"] = "cycle"
    reject("cycle_rejected",lambda:plan(cyclic,cyclic_choices),"cyclic_route")
    # Corrupt a recorded source object and verify that reopening cannot reuse the altered proof.
    complete = ledger.manifest(ledger.attempt(nodes["trace_witness"]["complete"]))
    source_key = next(value for name,value in complete["files"].items() if name.startswith("sources/C"))
    path = ledger.objects.root/source_key
    saved = path.read_bytes()
    try:
        path.write_bytes(b"corrupted proof")
        reject("proof_artifact_tampering_detected",lambda:workspace.read(run["id"]),"artifact_mismatch")
    finally:
        path.write_bytes(saved)
    expect("history_reopens_exact_mapping",workspace.history(mapping)[0]["id"],run["id"])
    # Export readable Rocq sources, while their content identities stay in the original receipts.
    proofs = directory/"proofs"
    proofs.mkdir()
    for relation in edges.values():
        receipt = ledger.manifest(ledger.attempt(relation["attempt"]))
        for name,digest in receipt["files"].items():
            if name.startswith("sources/C"):
                (proofs/(relation["key"]+".v")).write_bytes(ledger.objects.get(digest))
    return run["id"]
