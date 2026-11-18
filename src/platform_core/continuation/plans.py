"""Materialize the exact graph revision that a decision and an adoption will reference."""

from copy import deepcopy

from platform_core.evidence.storage import encoded, sha
from platform_core.evidence.terms import Rejected
from platform_core.reasoning.graph import validate
from platform_core.reasoning.statements import render


def prepare(proposal, original):
    """Build a concrete adoption plan using the proposal's historical route, not today's head.

    @param proposal Verified immutable W05-a proposal.
    @param original Verified execution that owns the proposal's original graph.
    @return Exact plan with a stable review token and explicit blockers.
    """
    # @var graph, selection Independent graph copy and the route revision actually reviewed by the author.
    graph = deepcopy(original["graph"])
    selection = next(item for item in original["selection_history"] if item["id"] == proposal["selection"])
    choices = deepcopy(selection["choices"])
    # @var blockers, changes Concrete reasons to defer adoption and executable relation changes.
    blockers,changes = [],[]
    if proposal["status"] == "needs_details":
        blockers.append("提案尚需补充精确数学内容；请先明确范围、条件或修改对象。")
    elif proposal["intent"] == "advance_service":
        # @var graph, choices The saved proposal fixes all new lemma statements and joint premises.
        graph,choices = deepcopy(proposal["preview"]["graph"]),deepcopy(proposal["preview"]["choices"])
        changes = deepcopy(proposal["changes"])
    elif proposal["intent"] == "split_bridge":
        if proposal["preview"] is None:
            raise Rejected("invalid_proposal","拆分提案缺少具体图修订。")
        graph,choices = deepcopy(proposal["preview"]["graph"]),deepcopy(proposal["preview"]["choices"])
        # @var relation Exact pending sufficient implication now supported by a local proof constructor.
        relation = next(edge for edge in graph["edges"] if edge["key"] == "proposed_bridge_from_bounds")
        relation["rule"] = "bridge_from_service_bounds"
        changes.append({"action":"check_joint_implication","edge":relation["key"],"premises":relation["premises"],
                        "conclusion":relation["conclusion"]})
    elif proposal["intent"] == "reverse_alignment":
        # @var change, old, replacement Exact direction revision, including the old connection being replaced.
        change = next(item for item in proposal["changes"] if item["kind"] == "replace_alignment")
        old,replacement = change["before"],deepcopy(change["after"])
        # @var old_edge Original directed implication that remains available only in parent history.
        old_edge = old["edge"]
        graph["edges"] = [edge for edge in graph["edges"] if edge["key"] != old_edge]
        choices = {target:key for target,key in choices.items() if key != old_edge}
        # @var edge_key New pending relation gets its own identity and never borrows the old implication receipt.
        edge_key = "reverse/"+replacement["key"]
        replacement.update(edge=edge_key,attempt=None,status="candidate")
        graph["alignments"] = [replacement if item["key"] == old["key"] else item for item in graph["alignments"]]
        graph["edges"].append({"key":edge_key,"premises":[replacement["from"]],"conclusion":replacement["to"],
                               "side":"alignment","rule":None,"attempt":None,"outcome":"pending"})
        choices[replacement["to"]] = edge_key
        changes.extend([{"action":"remove_connection","edge":old_edge},
                        {"action":"add_pending_connection","edge":edge_key,"from":replacement["from"],"to":replacement["to"],
                         "instantiation":None,"proof":"required"}])
    elif proposal["intent"] not in ("arrival_condition","alignment_review"):
        blockers.append("当前提案没有可采用的具体修订。")
    # Type validation covers every statement; selected-route validation also checks all joint premises and cycles.
    if not blockers:
        validate(graph,choices)
        # @var node Every retained or introduced claim must match its typed formal rendering.
        for node in graph["nodes"]:
            if node["statement"] is not None and render(node["statement"]) != node["formal"]:
                raise Rejected("target_mismatch","提案中的形式陈述与类型化表达式不同。")
    # @var body Only immutable mathematical inputs enter the token; current heads are observations elsewhere.
    body = {"schema_version":1,"proposal":proposal["id"],"parent":original["id"],"selection":selection["id"],
            "mapping":original["mapping"],"freeze":original["freeze"],"review_revision":original["review_revision"],
            "graph":graph,"choices":choices,"changes":changes,"tasks":proposal["tasks"],
            "scope":proposal["scope"],"requires_confirmation":proposal["requires_math_confirmation"],
            "ready":not blockers,"blockers":blockers,"strategy":"local_continuation_v1"}
    return {**body,"token":sha(encoded(body))}
