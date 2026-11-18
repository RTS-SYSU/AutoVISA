"""Calculate exact historical differences without submitting proofs or changing route heads."""

from copy import deepcopy

from platform_core.continuation.execution import receipt_owners


def changes(before, after):
    """Compare keyed values without interpreting missing data as a mathematical success.

    @param before Original key-to-value mapping.
    @param after Revised key-to-value mapping.
    @return Deterministically ordered rows with exact values and changed top-level fields.
    """
    # @var rows, key, left, right Stable result rows and the two values for each logical identity.
    rows = []
    for key in sorted(before.keys() | after.keys()):
        left,right = before.get(key),after.get(key)
        # @var kind, fields Structural change and precisely differing fields, excluding unchanged identities.
        kind = "added" if key not in before else "removed" if key not in after else "unchanged" if left == right else "modified"
        fields = sorted(name for name in left.keys() | right.keys() if left.get(name) != right.get(name)) if (
            isinstance(left,dict) and isinstance(right,dict)) else []
        rows.append({"key":key,"change":kind,"before":deepcopy(left),"after":deepcopy(right),"fields":fields})
    return rows


def project(items, fields):
    """Select mathematical fields while keeping proof identities in a separate comparison.

    @param items Graph records with stable key fields.
    @param fields Fields that describe this comparison category.
    @return Keyed record projections; no receipt change becomes a statement change.
    """
    return {item["key"]:{field:item.get(field) for field in fields} for item in items}


def proof_state(node):
    """Describe an actual claim outcome without deriving truth from graph connectivity.

    @param node Saved graph claim with an optional complete proof receipt.
    @return Precise outcome, goal revision and original receipt reference.
    """
    return {"status":"proved" if node.get("complete") else "unencoded" if node["statement"] is None else "open",
            "goal":node.get("goal"),"complete":node.get("complete"),"attempts":node["attempts"]}


def usage(run):
    """Keep per-run usage, known ancestry totals and unavailable legacy measurements distinct.

    @param run Saved execution with optional W05-b usage accounting.
    @return Comparable accounting with None for unrecorded measurements.
    """
    # @var attempts, measured Observed event identities and optional directly recorded counters.
    attempts = {event["attempt"] for event in run.get("events",[]) if event.get("attempt")}
    measured = run.get("usage",{})
    return {"budget":run.get("budget"),"status":run["status"],"end_reason":run.get("end_reason"),
            "proof_attempts":measured.get("proof_attempts",len(attempts)),
            "attempt_count_source":"recorded" if "proof_attempts" in measured else "saved_events",
            "external_calls":measured.get("external_calls"),"external_cost_usd":measured.get("external_cost_usd"),
            "elapsed_ms":measured.get("elapsed_ms"),"error":run.get("error"),
            "cumulative":run.get("cumulative_usage",{"known_proof_attempts":len(attempts),
                "known_external_cost_usd":0,"unknown_cost_runs":[run["id"]]})}


def compare(parent, child, parent_ir, child_ir, ledger):
    """Calculate the requested model, graph, route, evidence, obligation and usage differences.

    @param parent Verified parent execution at the explicitly selected route version.
    @param child Verified direct child at its explicitly selected route version.
    @param parent_ir Historical typed mapping for the parent.
    @param child_ir Historical typed mapping for the child.
    @param ledger Existing evidence store for read-only receipt outcomes.
    @return Literal before/after observations; no proof attempt or source record is changed.
    """
    # @var left, right Stable graph claim indices shared by goals, proof progress and open-leaf explanations.
    left = {item["key"]:item for item in parent["graph"]["nodes"]}
    right = {item["key"]:item for item in child["graph"]["nodes"]}
    # @var model_fields Explicit model/analysis scope; source revisions are compared alongside semantics.
    model_fields = ("domain","scope","definitions","bindings","kernel_bindings","primary")
    model = changes({key:parent_ir.get(key) for key in model_fields},{key:child_ir.get(key) for key in model_fields})
    # @var node_fields Mathematical content only; goal revisions and receipts belong to proof rows.
    node_fields = ("title","side","statement","formal","source_keys")
    nodes = changes(project(parent["graph"]["nodes"],node_fields),project(child["graph"]["nodes"],node_fields))
    goals = changes(project([left[key] for key in parent["graph"]["roots"]],node_fields),
                    project([right[key] for key in child["graph"]["roots"]],node_fields))
    # @var edges, alignments Exact directions, ordered joint premises and substitutions, independent of proof results.
    edges = changes(project(parent["graph"]["edges"],("premises","conclusion","rule","side")),
                    project(child["graph"]["edges"],("premises","conclusion","rule","side")))
    alignments = changes(project(parent["graph"]["alignments"],("from","to","direction","instantiation","binders","conditions","edge","bridge_obligations")),
                         project(child["graph"]["alignments"],("from","to","direction","instantiation","binders","conditions","edge","bridge_obligations")))
    routes = changes(parent["selection"]["choices"],child["selection"]["choices"])
    proofs = changes({key:proof_state(node) for key,node in left.items()},
                     {key:proof_state(node) for key,node in right.items()})
    # @var obligations, original_plans, revised_plans Selected closures, rather than every candidate route.
    obligations = []
    original_plans = {item["root"]:item for item in parent["plan"]}
    revised_plans = {item["root"]:item for item in child["plan"]}
    for key in sorted(original_plans.keys() | revised_plans.keys()):
        # @var before, after, old_open, new_open Exact root plans and their unresolved leaf sets.
        before,after = original_plans.get(key),revised_plans.get(key)
        old_open,new_open = set(before["open"] if before else []),set(after["open"] if after else [])
        obligations.append({"root":key,"before":before,"after":after,
            "introduced":sorted(new_open-old_open),"retained":sorted(new_open & old_open),
            "proved":sorted(item for item in old_open-new_open if right.get(item,{}).get("complete")),
            "left_route":sorted(item for item in old_open-new_open if not right.get(item,{}).get("complete"))})
    # @var prior_receipts, next_receipts, inheritance Original receipt owners and the child's recorded reuse decisions.
    prior_receipts,next_receipts = receipt_owners(parent["graph"]),receipt_owners(child["graph"])
    inheritance = {item["attempt"]:item for item in child.get("inheritance",[])}
    receipts = []
    for identity in sorted(prior_receipts.keys() | next_receipts.keys()):
        # @var saved, inherited, kind Verified outcome, actual inheritance decision and presence in each run.
        saved = ledger.attempt(identity)
        inherited = inheritance.get(identity)
        kind = "shared" if identity in prior_receipts and identity in next_receipts else "new" if identity in next_receipts else "historical"
        receipts.append({"attempt":identity,"change":kind,"outcome":saved["code"],"target":saved["target"],
            "before_owners":prior_receipts.get(identity,[]),"after_owners":next_receipts.get(identity,[]),
            "inheritance":inherited,"detail":saved["detail"]})
    # @var before_usage, after_usage Actual independent budgets and usage; a difference is not cumulative work.
    before_usage,after_usage = usage(parent),usage(child)
    return {"model":model,"versions":changes({key:parent.get(key) for key in ("mapping","freeze","review_revision","context","checker_profile")},
                {key:child.get(key) for key in ("mapping","freeze","review_revision","context","checker_profile")}),"goals":goals,"nodes":nodes,"edges":edges,"alignments":alignments,"routes":routes,
            "proofs":proofs,"obligations":obligations,"receipts":receipts,
            "usage":{"before":before_usage,"after":after_usage,"delta":{
                key:after_usage[key]-before_usage[key] if before_usage[key] is not None and after_usage[key] is not None else None
                for key in ("proof_attempts","external_calls","external_cost_usd","elapsed_ms")}},
            "summary":{"model_changed":any(row["change"] != "unchanged" for row in model),
                "goals_changed":sum(row["change"] != "unchanged" for row in goals),
                "added_nodes":sum(row["change"] == "added" for row in nodes),
                "changed_connections":sum(row["change"] != "unchanged" for row in edges),
                "newly_proved":[key for key,node in right.items() if node.get("complete") and not left.get(key,{}).get("complete")],
                "reopened":[key for key,node in left.items() if node.get("complete") and key in right and not right[key].get("complete")],
                "new_receipts":sum(row["change"] == "new" for row in receipts),
                "shared_receipts":sum(row["change"] == "shared" for row in receipts),
                "historical_receipts":sum(row["change"] == "historical" for row in receipts)}}
