"""Check grounded semantic drafts against case_11 and adversarial layout perturbations."""

from collections import Counter
from dataclasses import replace

import psycopg2

from platform_core.evidence.storage import Ledger, sha
from platform_core.evidence.terms import Rejected
from platform_core.paper_ingestion.service import PaperImporter
from platform_core.semantics.models import SemanticFailure, SemanticSnapshot
from platform_core.semantics.service import SemanticExtractor, review_markdown
from w03_import_cases import fixture_pdf


def exercise(extractor, source, directory, dsn, root, report):
    """Exercise semantic extraction, citation integrity, review gates and persistence.

    @param extractor Semantic service backed by an isolated test database.
    @param source Path to the real case_11 PDF.
    @param directory Test output directory for fixture PDFs and review exports.
    @param dsn Database connection string for an independent reader.
    @param root Project root containing the frozen rules and scope contract.
    @param report Mutable report retaining completed observations on failure.
    @return Updated report containing the saved snapshot identity.
    @raise AssertionError If an observed result violates the extraction contract.
    """
    # checks accumulates evidence even if a later assertion fails.
    checks = report["checks"] = {}

    def expect(name, actual, expected):
        """Record one observable contract assertion.

        @param name Stable acceptance check name.
        @param actual Value observed through the tested interface.
        @param expected Required value.
        @raise AssertionError If the values differ.
        """
        if actual != expected:
            raise AssertionError(f"{name}: {actual!r} != {expected!r}")
        checks[name] = "passed"

    def reject(name, code, operation):
        """Require a specific failure instead of accepting incomplete evidence.

        @param name Stable acceptance check name.
        @param code Expected machine-readable diagnostic.
        @param operation Zero-argument operation under test.
        @raise AssertionError If it succeeds or fails for a different reason.
        """
        try:
            operation()
        except (SemanticFailure, Rejected) as error:
            expect(name, error.code, code)
        else:
            raise AssertionError(name + " unexpectedly succeeded")

    # importer and layout identify the actual source; draft is a review candidate, never a proof.
    importer = extractor.importer
    extraction_id = importer.import_pdf(source)
    layout = importer.open(extraction_id)
    identity = extractor.extract(extraction_id)
    draft = extractor.open(identity)
    items = {item.key: item for item in draft.items}
    report.update({"extraction_id": extraction_id, "semantic_id": identity,
                   "source_sha256": layout.source_sha256, "profile": draft.profile})
    expect("actual_case11_source", draft.source_sha256,
           "d5d16b999822e16220102521cf23c56e6b88b2e4b9b40b0e26ec344a676a2f41")
    expect("category_counts", dict(Counter(item.category for item in draft.items)),
           {"model": 8, "analysis": 3, "goal": 4})
    expect("baseline_has_no_missing_selectors", draft.issues, ())
    expect("review_gate_closed", draft.ready_for_reasoning, False)
    expect("all_items_need_review", {item.status for item in draft.items}, {"needs_review"})
    expect("all_goals_unproved", {item.proof_status for item in draft.items if item.category == "goal"}, {"unproved"})
    expect("parameter_operators_from_input", items["parameter_order"].normalized["expression"], "C_i ≤ D_i ≤ T_i")
    expect("rm_background_preserved", [items[key].material_role for key in ("preemptive_context", "independent_context")],
           ["background", "background"])
    expect("tie_break_not_invented", items["dm_priority"].normalized["equal_deadline_tie_break"], "unspecified")
    expect("formula_interpretations_labeled", {items[key].normalization_origin for key in ("test1", "test2", "fig3")},
           {"reviewed_formula_template"})
    expect("integer_scope_kept_separate", "integer_time" in {choice["id"] for choice in draft.project_choices["choices"]}
           and "integer_time" not in items, True)
    expect("project_contract_pinned", sha((root / draft.project_choices["contract"]).read_bytes()),
           draft.project_choices["contract_sha256"])
    expect("existing_selection_retained", draft.project_choices["prior_selection"]["paper_goal"],
           "fig3_acceptance_soundness")
    # Every selected span must resolve to the exact physical source, including disjoint formula fragments.
    anchors = [anchor for item in draft.items for evidence in item.sources for anchor in evidence.anchors]
    expect("every_anchor_resolves", all(importer.resolve(anchor).anchor == anchor for anchor in anchors), True)
    expect("fig3_algorithm_on_page4", {anchor.page for evidence in items["fig3"].sources
           if evidence.kind == "formula_region" and evidence.selector == "fig3_algorithm"
           for anchor in evidence.anchors}, {4})
    expect("roundtrip_preserves_quotes", SemanticSnapshot.from_dict(draft.to_dict()), draft)
    expect("same_input_same_snapshot", extractor.extract(extraction_id), identity)
    expect("single_snapshot_for_repeat", extractor.ledger.rows(
           "SELECT count(*) AS count FROM semantic_snapshots")[0]["count"], 1)
    # A second connection checks that the result is not held only by the producing service instance.
    reader_ledger = Ledger(dsn, extractor.ledger.objects.root)
    try:
        reader = SemanticExtractor(PaperImporter(reader_ledger, importer.parser), root)
        expect("independent_reader", reader.open(identity), draft)
    finally:
        reader_ledger.close()

    def changed_page(page_number, page):
        """Create an in-memory layout perturbation without publishing it as source evidence.

        @param page_number One-based physical page to replace.
        @param page Perturbed page preserving raw text offsets where applicable.
        @return Isolated layout fixture for testing missing, ambiguous or changed input.
        """
        pages = list(layout.pages)
        pages[page_number - 1] = page
        return replace(layout, pages=tuple(pages))

    # A changed working contract blocks new extraction while historical snapshots retain their pinned context.
    changed_root = directory / "changed-contract"
    (changed_root / "configs").mkdir(parents=True)
    for name in ("case11-semantic-rules.json", "case11-project-choices.json"):
        (changed_root / "configs" / name).write_bytes((root / "configs" / name).read_bytes())
    contract_path = changed_root / draft.project_choices["contract"]
    contract_path.parent.mkdir(parents=True)
    contract_path.write_bytes((root / draft.project_choices["contract"]).read_bytes() + b"\nchanged")
    changed_service = SemanticExtractor(importer, changed_root)
    reject("changed_contract_blocks_new_draft", "decision_contract_changed",
           lambda: changed_service.extract(extraction_id))
    expect("historical_contract_still_readable", changed_service.open(identity), draft)

    # Remove words supporting the parameter inequality: the extractor must not invent the missing condition.
    parameter_anchor = items["parameter_order"].sources[0].anchors[0]
    page = layout.pages[parameter_anchor.page - 1]
    selected_words = tuple(word for word in page.words
                           if word.start < parameter_anchor.end and word.end > parameter_anchor.start)
    without_condition = replace(page, words=tuple(word for word in page.words if word not in selected_words))
    partial = extractor.engine.build(extraction_id, changed_page(page.number, without_condition))
    expect("missing_condition_omitted", "parameter_order" in {item.key for item in partial.items}, False)
    expect("missing_condition_reported", any(issue["code"] == "source_missing" for issue in partial.issues), True)
    expect("dependent_goals_blocked", {item.status for item in partial.items if item.category == "goal"}, {"blocked"})
    # Duplicating the matching words simulates an ambiguous selector; neither occurrence may win silently.
    ambiguous = extractor.engine.build(extraction_id, changed_page(page.number,
                                      replace(page, words=page.words + selected_words)))
    expect("ambiguous_condition_omitted", "parameter_order" in {item.key for item in ambiguous.items}, False)
    expect("ambiguity_reported", any(issue["code"] == "source_ambiguous" for issue in ambiguous.issues), True)
    # An equal-length comparator mutation preserves offsets while changing the mathematical meaning.
    operator = next(word for word in selected_words if word.text == "≤")
    changed = replace(page, text=page.text[:operator.start] + "≥" + page.text[operator.end:],
                      words=tuple(replace(word, text="≥") if word == operator else word for word in page.words))
    changed_draft = extractor.engine.build(extraction_id, changed_page(page.number, changed))
    changed_items = {item.key: item for item in changed_draft.items}
    expect("changed_operator_not_template", changed_items["parameter_order"].normalized["expression"], "C_i ≥ D_i ≤ T_i")
    expect("changed_scope_blocks_goal", changed_items["fig3_acceptance_soundness"].status, "blocked")
    expect("scope_change_reported", any(issue["code"] == "scope_relation_changed" for issue in changed_draft.issues), True)
    # Remove the actual loop keyword from the algorithm region; formulas must not materialize from templates alone.
    algorithm_page = layout.pages[3]
    missing_formula = replace(algorithm_page, words=tuple(word for word in algorithm_page.words if word.text != "endwhile"))
    formula_draft = extractor.engine.build(extraction_id, changed_page(4, missing_formula))
    expect("missing_formula_not_filled", "fig3" in {item.key for item in formula_draft.items}, False)
    expect("formula_gap_reported", any(issue["code"] == "formula_markers_missing" for issue in formula_draft.issues), True)

    def forged_anchor(anchor):
        """Replace the first reference in a draft for integrity boundary tests.

        @param anchor Deliberately altered source reference.
        @return Draft with one changed reference and otherwise unchanged content.
        """
        first_item = draft.items[0]
        evidence = replace(first_item.sources[0], anchors=(anchor, *first_item.sources[0].anchors[1:]))
        altered = replace(first_item, sources=(evidence, *first_item.sources[1:]))
        return replace(draft, items=(altered, *draft.items[1:]))

    # These probes exercise the same validator used on creation and restoration.
    anchor = draft.items[0].sources[0].anchors[0]
    reject("changed_quote_rejected", "source_reference_mismatch",
           lambda: extractor._validate(forged_anchor(replace(anchor, quote="invented")), layout))
    reject("cross_source_rejected", "source_reference_mismatch",
           lambda: extractor._validate(forged_anchor(replace(anchor, source_sha256="0" * 64)), layout))
    reject("cross_layout_rejected", "source_reference_mismatch",
           lambda: extractor._validate(forged_anchor(replace(anchor, extraction_id="0" * 64)), layout))
    reject("premature_reasoning_rejected", "invalid_semantic_draft",
           lambda: extractor._validate(replace(draft, ready_for_reasoning=True), layout))
    # A semantic candidate cannot acquire proof status before a checker has produced separate evidence.
    goal = items["fig3_acceptance_soundness"]
    false_proof = replace(draft, items=tuple(replace(item, proof_status="proved") if item == goal else item
                                           for item in draft.items))
    reject("invented_proof_status_rejected", "invalid_semantic_draft",
           lambda: extractor._validate(false_proof, layout))
    # Reject unrelated input through the public service before creating a semantic catalog row.
    unrelated = directory / "unrelated.pdf"
    unrelated.write_bytes(fixture_pdf())
    other_id = importer.import_pdf(unrelated)
    before = extractor.ledger.rows("SELECT count(*) AS count FROM semantic_snapshots")[0]["count"]
    reject("unrelated_paper_rejected", "unsupported_paper", lambda: extractor.extract(other_id))
    expect("rejection_does_not_publish", extractor.ledger.rows(
           "SELECT count(*) AS count FROM semantic_snapshots")[0]["count"], before)
    # Snapshot history must be immutable even when a caller bypasses the Python service.
    try:
        with extractor.ledger.db, extractor.ledger.db.cursor() as cursor:
            cursor.execute("DELETE FROM semantic_snapshots WHERE id=%s", (identity,))
    except psycopg2.Error:
        expect("database_history_immutable", extractor.open(identity), draft)
    else:
        raise AssertionError("database allowed deletion")
    # Damage only isolated test objects, restoring their original bytes before writing the archive.
    for label, digest in (("rules", draft.profile["files"]["rules"]),
                          ("contract", draft.profile["files"]["decision_contract"]),
                          ("pdf", draft.source_sha256)):
        path = extractor.ledger.objects.root / digest
        original = path.read_bytes()
        try:
            path.write_bytes(b"tampered")
            reject(label + "_corruption_rejected", "artifact_mismatch", lambda: extractor.open(identity))
            path.unlink()
            reject(label + "_missing_rejected", "missing_artifact", lambda: extractor.open(identity))
        finally:
            path.write_bytes(original)
    # Export a human-readable review alongside the machine report, retaining exact quotes.
    (directory / "semantics.md").write_text(review_markdown(draft), encoding="utf-8")
    report["items"] = len(draft.items)
    report["source_references"] = len(anchors)
    return report
