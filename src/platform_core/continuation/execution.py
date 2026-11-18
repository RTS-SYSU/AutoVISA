"""Execute a bounded revision run with exact receipt inheritance and real Rocq checks."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

from platform_core.evidence.service import Evidence
from platform_core.evidence.storage import encoded
from platform_core.evidence.terms import Rejected
from platform_core.reasoning.graph import plan as graph_plan


def receipt_owners(graph):
    """Index each original proof attempt once, retaining every node or edge that uses it.

    @param graph Original immutable execution graph.
    @return Attempt-to-owner-list mapping.
    """
    # @var owners Shared receipts can occur on both a node and its unconditional rule edge.
    owners = {}
    # @var node, attempt, edge Claim, receipt identity and relation contributing an ownership reference.
    for node in graph["nodes"]:
        for attempt in node["attempts"]:
            owners.setdefault(attempt,[]).append("node:"+node["key"])
    for edge in graph["edges"]:
        if edge.get("attempt"):
            owners.setdefault(edge["attempt"],[]).append("edge:"+edge["key"])
    return owners


def inherit(original, result, evidence):
    """Reuse only exact current-context receipts whose actual derivation dependencies remain applicable.

    @param original Parent execution with verified immutable evidence.
    @param result Child execution whose graph and new context receive eligible references.
    @param evidence W02 Interface tied to the active real checker.
    """
    # @var nodes, prior_nodes, edges, prior_edges Indices for exact statement and joint-premise comparison.
    nodes = {item["key"]:item for item in result["graph"]["nodes"]}
    prior_nodes = {item["key"]:item for item in original["graph"]["nodes"]}
    edges = {item["key"]:item for item in result["graph"]["edges"]}
    prior_edges = {item["key"]:item for item in original["graph"]["edges"]}
    # @var ledger Durable W02 identity and artifact access for dependency inspection.
    ledger = evidence.db
    # @var blocked Attempts that belong to a removed or mathematically changed relation or claim.
    blocked = set()
    # @var key, old, new Stable owner identity and original/revised mathematical relation.
    for key,old in prior_edges.items():
        new = edges.get(key)
        if old.get("attempt") and (new is None or any(old.get(field) != new.get(field) for field in ("premises","conclusion","rule"))):
            blocked.add(old["attempt"])
    for key,old in prior_nodes.items():
        if key not in nodes or nodes[key]["statement"] != old["statement"]:
            blocked.update(old["attempts"])
    # @var dependency_cache Actual composed proof dependencies, not visual reachability alone.
    dependency_cache = {}

    def changed_dependency(attempt):
        """Detect whether a receipt uses a relation replaced by this particular proposal.

        @param attempt Original receipt identity.
        @return Whether its actual composition transitively depends on a replaced receipt.
        """
        if attempt not in dependency_cache:
            # @var request, dependencies Original construction request and its actual input receipts.
            request = ledger.attempt(attempt)["request"]
            dependencies = [request["rule"],*request["proofs"]] if request["kind"] == "application" else []
            dependency_cache[attempt] = attempt in blocked or any(changed_dependency(item) for item in dependencies)
        return dependency_cache[attempt]

    # @var key, node Child claim identity and mutable evidence attachment destination.
    for key,node in nodes.items():
        # @var previous Same logical claim may retain its exact W02 revision when context and statement match.
        previous = prior_nodes.get(key)
        if node["statement"] is None:
            continue
        if (previous and previous.get("goal") and previous["statement"] == node["statement"] and
            result["context"] == original["context"] and ledger.current(previous["goal"]) == previous["goal"]):
            node["goal"] = previous["goal"]
        else:
            node["goal"] = evidence.goal("w05b/"+result["id"]+"/"+key,result["context"],{"analysis":node["statement"]})
    # @var attempt, owners One original receipt and every graph owner that used it.
    for attempt,owners in receipt_owners(original["graph"]).items():
        # @var assessment, issues The checker assesses artifacts, environment, heads and transitive dependencies.
        assessment = evidence.assess(attempt)
        issues = list(assessment["issues"])
        if assessment["context"] != result["context"]:
            issues.append({"code":"context_changed"})
        if changed_dependency(attempt):
            issues.append({"code":"derivation_dependency_changed"})
        # @var attached, saved Eligible child owners and the immutable receipt being attached.
        attached = []
        if not issues:
            saved = ledger.attempt(attempt)
            for owner in owners:
                # @var owner, kind, key Original owner reference, object kind and stable graph identity.
                kind,key = owner.split(":",1)
                if kind == "node" and key in nodes and nodes[key].get("goal") == assessment["target"]:
                    nodes[key]["attempts"].append(attempt)
                    if prior_nodes[key].get("complete") == attempt and assessment["outcome"] == "complete":
                        nodes[key]["complete"] = attempt
                    attached.append(owner)
                elif kind == "edge" and key in edges:
                    # @var edge, expected Revised implication and its exact ordered joint-premise goals.
                    edge = edges[key]
                    expected = [nodes[premise].get("goal") for premise in edge["premises"]]
                    if (nodes[edge["conclusion"]].get("goal") == assessment["target"] and
                        saved["request"].get("premises") == expected):
                        edge.update(attempt=attempt,outcome=assessment["outcome"],detail=saved["detail"])
                        attached.append(owner)
            if not attached:
                issues.append({"code":"exact_target_or_premises_changed"})
        result["inheritance"].append({"attempt":attempt,"from_run":original["id"],"owners":owners,
                                      "attached_to":attached,"disposition":"reused" if attached else "needs_recheck",
                                      "reasons":issues,"historical_receipt":"preserved"})


def check_pending(result, evidence):
    """Check available local rules and compose only fully proved joint premises within the run budget.

    @param result Mutable execution containing inherited graph evidence and a fixed proof-attempt budget.
    @param evidence Real W02 checker Interface.
    @return Whether an available proof action was deferred by the budget.
    """
    # @var nodes, used, maximum Exact goal references and the per-run attempt counter.
    nodes = {node["key"]:node for node in result["graph"]["nodes"]}
    used,maximum = 0,result["budget"]["max_proof_attempts"]

    def record(edge, attempt, phase):
        """Attach one actual check outcome without confusing a conditional rule with a completed node.

        @param edge Relation being checked or composed.
        @param attempt Real W02 proof-attempt identity.
        @param phase check_rule or compose.
        """
        # @var outcome, target The immutable receipt and the exact node receiving its checked status.
        outcome = evidence.db.attempt(attempt)
        target = nodes[edge["conclusion"]]
        if phase == "check_rule":
            edge.update(attempt=attempt,outcome=outcome["code"],detail=outcome["detail"])
        if phase == "compose" or outcome["code"] == "complete":
            target["attempts"].append(attempt)
        if outcome["code"] == "complete":
            target["complete"] = attempt
        result["events"].append({"phase":phase,"edge":edge["key"],"attempt":attempt,"outcome":outcome["code"]})
        result["usage"]["proof_attempts"] += 1

    # @var edge, attempt Candidate local rule and its actual newly submitted proof attempt.
    for edge in result["graph"]["edges"]:
        if edge.get("attempt") or not edge.get("rule"):
            continue
        if used >= maximum:
            return True
        attempt = evidence.prove(nodes[edge["conclusion"]]["goal"],{"derivation":edge["rule"]},
                                 [nodes[key]["goal"] for key in edge["premises"]])
        used += 1
        record(edge,attempt,"check_rule")
    # @var attempted Prevent repeated failed composition in one strategy pass.
    attempted = set()
    while True:
        # @var ready Conditional implications whose entire premise set already has complete evidence.
        ready = [edge for edge in result["graph"]["edges"] if edge.get("outcome") == "conditional" and
                 edge["key"] not in attempted and not nodes[edge["conclusion"]].get("complete") and
                 all(nodes[key].get("complete") for key in edge["premises"])]
        if not ready:
            return False
        for edge in ready:
            if used >= maximum:
                return True
            attempt = evidence.compose(nodes[edge["conclusion"]]["goal"],edge["attempt"],
                                       [nodes[key]["complete"] for key in edge["premises"]])
            used += 1
            attempted.add(edge["key"])
            record(edge,attempt,"compose")


def execute(derivations, original, proposal, plan, request, identity):
    """Execute a linked revision and save its complete or partial result without editing the parent.

    @param derivations W04 Interface providing the ledger, mapping and real checker dependency.
    @param original Verified parent execution.
    @param proposal Exact feedback proposal being adopted.
    @param plan Concrete reviewed graph and historical route choices.
    @param request Immutable adoption request including decision, author and per-run budget.
    @param identity Already registered child execution identity.
    @return Saved child execution, including actual evidence and remaining obligations.
    """
    # @var ledger, started Shared durable store and monotonic duration of this child only.
    ledger,started = derivations.ledger,monotonic()
    # @var graph, node, field, edge, alignment Independent child objects whose evidence is reassessed below.
    graph = deepcopy(plan["graph"])
    for node in graph["nodes"]:
        node["origin"] = {"run":original["id"],"node":node["key"],"revision":node["revision"]} if any(
            item["key"] == node["key"] for item in original["graph"]["nodes"]) else {"proposal":proposal["id"]}
        node["attempts"] = []
        for field in ("goal","complete","proposed"):
            node.pop(field,None)
    for edge in graph["edges"]:
        edge.update(attempt=None,outcome="pending")
        edge.pop("detail",None)
        edge.pop("proposed",None)
    for alignment in graph["alignments"]:
        alignment.update(attempt=None,status="candidate")
    # @var files Original context, feedback and the reviewed plan are fixed input artifacts.
    files = {"input/adoption.json":ledger.objects.put(encoded(request)),
             "input/proposal.json":proposal["id"],"input/plan.json":ledger.objects.put(encoded(plan)),
             "input/parent-graph.json":ledger.objects.put(encoded(original["graph"]))}
    # @var name Implementation artifact name captured with this exact execution.
    for name in ("execution.py","plans.py","service.py","schema.sql"):
        files["implementation/"+name] = ledger.objects.put(Path(__file__).with_name(name).read_bytes())
    # @var result Mutable execution record, finalized once and then retained as immutable history.
    result = {"schema_version":1,"id":identity,"mapping":original["mapping"],"freeze":original["freeze"],
              "review_revision":original["review_revision"],"execution":"local_continuation","status":"running",
              "parent":original["id"],"proposal":proposal["id"],"adoption":request["id"],"decision":request["decision"],
              "base_selection":plan["selection"],"strategy":plan["strategy"],"initial_input_isolation":False,
              "history_inputs":[original["id"]],"budget":request["budget"],"files":files,"events":[],
              "graph":graph,"context":None,"inheritance":[],"tasks":deepcopy(proposal["tasks"]),
              "usage":{"proof_attempts":0,"external_calls":0,"external_cost_usd":0,"elapsed_ms":None},
              "end_reason":None}
    try:
        if derivations.checker_factory is None:
            raise Rejected("checker_unavailable","关联运行需要实际证明检查器。")
        # @var temporary Isolated checker working directory; durable receipts live in the ledger.
        with TemporaryDirectory(prefix="autorta-w05b-") as temporary:
            # @var checker, evidence One real checker session fixes all environment and library identities.
            checker = derivations.checker_factory(Path(temporary)/"checker")
            evidence = Evidence(ledger,checker)
            result["checker_profile"] = checker.profile_id
            # @var old_context Parent context whose profile and revision determine reuse eligibility.
            old_context = ledger.revision(original["context"])
            if old_context["body"]["profile"] == checker.profile_id and ledger.current(original["context"]) == original["context"]:
                result["context"] = original["context"]
            else:
                result["context"] = evidence.context("w05b/"+identity,hypotheses=old_context["body"]["hypotheses"],
                    note=json.dumps({"mapping":original["mapping"],"parent":original["id"],"proposal":proposal["id"]},sort_keys=True))
            inherit(original,result,evidence)
            # @var exhausted Whether the fixed check limit postponed an otherwise available action.
            exhausted = check_pending(result,evidence)
            result["end_reason"] = "budget_exhausted" if exhausted else "strategy_exhausted"
        # @var edges, nodes Checked relation and node indices update only actual task outcomes.
        edges = {edge["key"]:edge for edge in graph["edges"]}
        nodes = {node["key"]:node for node in graph["nodes"]}
        # @var alignment, relation Revised alignment and the actual implication receipt it references.
        for alignment in graph["alignments"]:
            relation = edges[alignment["edge"]]
            alignment.update(attempt=relation["attempt"],status="checked" if relation["outcome"] in ("conditional","complete") else "candidate")
        # @var task, target Proposed proof task and its exact node or relation identity.
        for task in result["tasks"]:
            target = task.get("target")
            if task["kind"] == "prove_claim" and nodes.get(target,{}).get("complete"):
                task["status"] = "proved"
            elif task["kind"] == "check_joint_sufficiency" and edges.get(target,{}).get("outcome") in ("conditional","complete"):
                task.update(status="checked",attempt=edges[target]["attempt"])
        result["status"] = "completed" if all(nodes[key].get("complete") for key in graph["roots"]) else "partial"
        if result["status"] == "completed":
            result["end_reason"] = "goals_completed"
    # @var error Actual execution failure retained alongside any evidence already saved.
    except Exception as error:
        result.update(status="failed",end_reason="execution_failed",
                      error={"code":getattr(error,"code","execution_failed"),"message":str(error)})
    result["usage"]["elapsed_ms"] = round((monotonic()-started)*1000)
    # @var parent_totals Legacy runs retain unknown cost instead of silently resetting it to zero.
    parent_totals = original.get("cumulative_usage",{
        "known_proof_attempts":len({event["attempt"] for event in original.get("events",[]) if event.get("attempt")}),
        "known_external_cost_usd":0,"unknown_cost_runs":[original["id"]]})
    result["cumulative_usage"] = {
        "known_proof_attempts":parent_totals["known_proof_attempts"]+result["usage"]["proof_attempts"],
        "known_external_cost_usd":parent_totals["known_external_cost_usd"]+result["usage"]["external_cost_usd"],
        "unknown_cost_runs":parent_totals["unknown_cost_runs"]}
    result["plan_at_completion"] = graph_plan(graph,plan["choices"])
    # Save partial states as actual executions; route selection does not modify this result afterward.
    # @var manifest, cursor Immutable result identity and its append-only registration transaction.
    manifest = ledger.objects.put(encoded(result))
    with ledger.db,ledger.db.cursor() as cursor:
        cursor.execute("INSERT INTO derivation_results(run,manifest) VALUES (%s,%s)",(identity,manifest))
    derivations.select(identity,None,plan["choices"])
    return derivations.read(identity)
