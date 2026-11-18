"""Adversarial examples for the evidence boundary; every positive receipt runs real Rocq."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import psycopg2

from platform_core.evidence.storage import Ledger
from platform_core.evidence.terms import Rejected


def exercise(service, dsn, objects, report):
    """Exercise the W02 evidence contract against a real checker and a disposable database.

    @param service Evidence service bound to a fresh checker and installed ledger schema.
    @param dsn Database connection string reused by independent concurrent writers.
    @param objects Disposable object directory used by the shared ledger and tamper cases.
    @param report Mutable acceptance report receiving checks, timeline entries and replay IDs.
    @raise AssertionError If a positive or negative case yields a different observation.
    """
    # db reads persisted evidence; cases is the checks mapping shared with the outer acceptance report.
    db, cases = service.db, report["checks"]
    def expect(label, actual, wanted):
        """Record a named check after comparing its observed and expected values.

        @param label Unique check name used in the report.
        @param actual Observed value from the service, database or checker.
        @param wanted Expected value for this case.
        @raise AssertionError If the two values differ.
        """
        if actual != wanted:
            raise AssertionError(f"{label}: expected {wanted!r}, got {actual!r}")
        cases[label] = "passed"

    def outcome(label, key, wanted):
        """Check an attempt's stored outcome and retain its ID as review evidence.

        @param label Name under which to publish this acceptance observation.
        @param key Registered attempt ID to resolve in the ledger.
        @param wanted Outcome code expected for this particular submission.
        @return The same attempt ID, usable as input to subsequent checks.
        @raise AssertionError If the recorded outcome differs from the expected code.
        """
        record = db.attempt(key)
        if record["code"] != wanted:
            raise AssertionError(f"{label}: {record['code']}: {record['detail']}")
        cases[label] = {"status": "passed", "attempt": key, "result": wanted}
        return key

    def trace(label, name):
        """Capture a goal's proof state, current routes and issues at one step of the scenario.

        @param label Human-readable name of the transition being observed.
        @param name Logical goal name used to query all revisions.
        @return Full history response observed at this step.
        """
        state = service.history(name)
        report["timeline"].append({"step": label, "goal": name, "state": state["state"],
                                   "routes": state["routes"], "issues": state["issues"]})
        return state

    # Substituting one expected digest exercises drift detection without editing installed libraries.
    relative = next(iter(service.checker.lock))
    # original preserves the real lock entry so the fixture can restore it even after a check fails.
    original = service.checker.lock[relative]
    try:
        service.checker.lock[relative] = {**original, "vo_sha256": "0" * 64}
        try:
            service.checker.foundation(relative)
        except Rejected as exc:
            expect("changed_foundational_binary_rejected", (exc.code, str(exc)), ("dependency_mismatch", relative))
        else:
            raise AssertionError("Accepted a foundational module with the wrong digest")
    finally:
        service.checker.lock[relative] = original

    # main and its context identify the paper's open theorem independently of the engineering fixtures.
    ctx = service.context("case11-integer", note="W01 reviewed integer DM contract")
    main = service.goal("case11-fig3-acceptance-soundness-int-v1", ctx, "case11")
    ctx = service.context("w02-example", note="Independent acceptance examples")
    # p and q are premise revision IDs; joint is their conjunction and g is its goal revision ID.
    p = service.goal("smoke-arithmetic", ctx, "smoke")
    q = service.goal("truth", ctx, "true")
    joint = {"and": ["smoke", "true"]}
    g = service.goal("joint-demo", ctx, joint)
    # pair is a structured term taking proofs p and q and returning their conjunction.
    pair = {"lambda": ["p", "smoke", {"lambda": ["q", "true", {"app": [
            {"symbol": "pair"}, {"prop": "smoke"}, {"prop": "true"},
            {"var": "p"}, {"var": "q"}]}]}]}
    # rule proves the implication; proof_p and proof_q are the complete attempts for the individual inputs.
    rule = outcome("conditional_kernel", service.prove(g, pair, [p, q]), "conditional")
    proof_p = outcome("first_premise", service.prove(p, {"symbol": "add_zero_right"}), "complete")
    # part captures the history before q has evidence and identifies the missing revision.
    part = trace("one premise still open", "joint-demo")
    expect("A06_open_premise", [part["state"], part["routes"][0]["missing"]], ["partial", [q]])
    outcome("E02-1_missing", service.compose(g, rule, [proof_p]), "missing_premise")
    # wrong and ax identify separate rejected attempts whose compiler and assumption logs are inspected.
    wrong = outcome("E02-2_weaker_goal", service.prove(g, {"symbol": "truth"}), "target_mismatch")
    expect("weaker_candidate_compiled", db.manifest(db.attempt(wrong))["commands"][0]["returncode"], 0)
    ax = outcome("E02-3_actual_axiom", service.prove(g, {"obligation": joint}), "unapproved_assumption")
    expect("named_actual_assumption", "unresolved" in db.attempt(ax)["detail"], True)
    outcome("symbol_policy", service.prove(g, {"symbol": "Prosa.existing_RTA"}), "unapproved_symbol")
    proof_q = outcome("second_premise", service.prove(q, {"symbol": "truth"}), "complete")
    expect("all_premises_still_require_application", trace("ready to compose", "joint-demo")["state"], "partial")
    outcome("wrong_dependency_order", service.compose(g, rule, [proof_q, proof_p]), "dependency_mismatch")
    # other is an alternate context revision; alt proves q_other only within that context.
    other = service.context("alternate", ["true"], note="Explicit strengthened context")
    q_other = service.goal("alternate-truth", other, "true")
    alt = outcome("checked_scoped_hypothesis", service.prove(q_other, {"lambda": ["h", "true", {"var": "h"}]}),
                  "complete")
    # This route stays current while the main demo is revised. Reuse it after database restore.
    scoped_goal = service.goal("scoped-demo", other, "true")
    scoped_rule = outcome("scoped_conditional", service.prove(scoped_goal,
                          {"lambda": ["h", "true", {"lambda": ["p", "true", {"var": "p"}]}]}, [q_other]),
                          "conditional")
    report["restore_route"] = [scoped_goal, scoped_rule, alt]
    outcome("E02-2_wrong_context", service.compose(g, rule, [proof_p, alt]), "context_mismatch")
    # full identifies the checked application; full_m lists the modules actually loaded by its checker.
    full = outcome("A07_closed_application", service.compose(g, rule, [proof_p, proof_q]), "complete")
    full_m = db.manifest(db.attempt(full), verify=True)
    expect("actual_kernel_and_assumptions", {s["stage"] for s in full_m["commands"]},
           {"candidate", "exact", "kernel", "assumptions", "symbols"})
    expect("actual_local_closure", len(full_m["modules"]), 8)
    expect("checked_at_head", trace("kernel checked application", "joint-demo")["state"], "checked")

    # Make downstream staleness observable two edges away from the changed premise.
    outer = service.goal("downstream-demo", ctx, joint)
    # identity forwards a proof of g to the outer target, creating a second dependency level.
    identity = {"lambda": ["x", joint, {"var": "x"}]}
    downstream_rule = outcome("downstream_rule", service.prove(outer, identity, [g]), "conditional")
    outcome("downstream_closed", service.compose(outer, downstream_rule, [full]), "complete")

    # Deliberately corrupt only this disposable run, then restore the original bytes.
    key = db.attempt(proof_p)["manifest"]
    # path names the object being corrupted; good preserves the original bytes for exact restoration.
    path, good = db.objects.root / key, db.objects.get(key)
    try:
        path.write_bytes(b"tamper")
        st = service.history("joint-demo")
        expect("changed_dependency_not_current", st["state"], "partial")
        outcome("tampered_input", service.compose(g, rule, [proof_p, proof_q]), "artifact_mismatch")
        path.unlink()
        outcome("missing_input", service.compose(g, rule, [proof_p, proof_q]), "missing_artifact")
    finally:
        path.write_bytes(good)
    expect("restored_digest", service.history("joint-demo")["state"], "checked")
    # q2 supersedes the premise pinned by the earlier rule and full application.
    q2 = service.goal("truth", ctx, {"eq_nat": [1, 1]}, parent=q)
    st = trace("premise changed", "joint-demo")
    expect("E02-7_premise_stale", st["state"], "open")
    # old is the historical complete attempt whose issue should identify both premise revisions.
    old = next(a for a in st["attempts"] if a["id"] == full)
    expect("A08_reason_points_to_changed_revision",
           any(r.get("was") == q and r.get("now") == q2 for r in old["issues"]), True)
    expect("transitive_stale", service.history("downstream-demo")["state"], "partial")
    outcome("stale_route_rejected", service.compose(g, rule, [proof_p, proof_q]), "goal_revised")
    # g2 is an independently provable replacement for the original conjunction.
    g2 = service.goal("joint-demo", ctx, "true", parent=g)
    outcome("new_target_independent_proof", service.prove(g2, {"symbol": "truth"}), "complete")
    expect("goal_history_retained", len(service.history("joint-demo")["revisions"]), 2)
    outcome("cannot_apply_displaced_target", service.prove(g, {"symbol": "truth"}), "goal_revised")

    # Exercise the actual SQL constraint and the compare-and-append operation on two connections.
    # gate releases both writers against the same expected parent, each using its own connection.
    gate = Barrier(2)
    def compete(n):
        """Try to append one revision from the same parent as a competing writer.

        @param n Natural number distinguishing this writer's proposed equality.
        @return New revision ID on success, or the rejection code from the ledger.
        """
        connection = Ledger(dsn, objects)
        try:
            gate.wait(timeout=10)
            return connection.revise("goal", "truth", {"proposition": {"eq_nat": [n, n]}}, q2, ctx)
        except Rejected as exc:
            return exc.code
        finally:
            connection.close()
    with ThreadPoolExecutor(2) as pool:
        # winners contains both results, one new revision ID and one revision_conflict diagnostic.
        winners = list(pool.map(compete, [2, 3]))
    expect("one_winner_for_same_parent", winners.count("revision_conflict"), 1)
    try:
        with db.db, db.db.cursor() as cur:
            cur.execute("UPDATE outcomes SET code='complete' WHERE attempt=%s", (wrong,))
    except psycopg2.errors.RaiseException:
        cases["immutable_receipt"] = "passed"
    else:
        raise AssertionError("Database allowed rewriting history")

    # newer is the replacement example context saved for reviewing the final invalidation.
    newer = service.context("w02-example", ["true"], parent=ctx, note="Demonstrate context invalidation")
    st = trace("context changed", "joint-demo")
    expect("context_change_stales_current_goal", [st["state"], st["issues"][0]["code"]], ["open", "context_revised"])
    # A context edit alone must not silently change the mathematical scope of the real main goal.
    expect("main_goal_remains_open", service.history(db.revision(main)["name"])["state"], "open")
    report["ids"] = {"main": main, "old_context": ctx, "new_context": newer, "joint_application": full}

