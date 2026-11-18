"""Independent rule expansion, explicit alignment and joint-premise route planning."""

from copy import deepcopy
from platform_core.evidence.storage import encoded, sha
from platform_core.evidence.terms import Rejected
from platform_core.analysis_ir.case11 import call, var
from .statements import claims, render

#: Display metadata and exact source keys for the independently generated propositions.
CLAIMS = {
    "trace_witness":("接受轨迹给出截止期内见证",["fig3"]),
    "trace_guard":("接受轨迹起点不超过截止期",["fig3"]),
    "cost_lower_bound":("工作量至少包含自身执行上界",["fig3","parameter_order"]),
    "task_witnesses":("所有通过测试的任务具有工作量见证",["fig3","fig3_acceptance_soundness"]),
    "response_bridge":("工作量见证蕴含任意合法轨迹的截止期保证",["fig3","parameter_order","sporadic_separation","dm_priority"]),
    "direct_jobs":("按任务与作业分解的截止期义务",["fig3_acceptance_soundness","sporadic_deadline"]),
}


def node(key, side, statement, request, title=None, sources=None):
    """Create a claim revision with exact frozen-input provenance.

    @param key Stable node key within this run.
    @param side Forward, backward or root ownership.
    @param statement Typed proposition, or None for an unsupported selected goal.
    @param request Immutable direction input containing mapping and review identities.
    @param title Optional human-facing label for a selected root.
    @param sources Optional semantic source keys overriding claim metadata.
    @return Serializable claim retaining its source and goal-context identities.
    """
    # @var label, keys Presentation and semantic binding keys for this particular claim.
    label,keys = CLAIMS.get(key,(title or key,sources or []))
    return {"key":key,"side":side,"title":title or label,"statement":statement,
            "formal":render(statement) if statement is not None else None,
            "revision":sha(encoded([request["mapping"],key,statement])),
            "mapping":request["mapping"],"freeze":request["freeze"],"review_revision":request["review_revision"],
            "source_keys":sources if sources is not None else keys,"attempts":[]}


def edge(key, premises, conclusion, rule, side):
    """Record one complete AND-premise derivation, separate from alternative routes.

    @param key Stable derivation identity.
    @param premises Ordered jointly required node keys.
    @param conclusion Node established only when every premise and this rule are checked.
    @param rule Local executable proof constructor key.
    @param side Direction or alignment phase proposing the route.
    @return Candidate hyperedge with explicit sufficient-premise order.
    """
    return {"key":key,"premises":premises,"conclusion":conclusion,"rule":rule,"side":side,"attempt":None}


def forward(request):
    """Execute forward rules using only this direction's frozen input.

    @param request Forward request containing shared IR, goals and allowed source materials.
    @return Fresh forward graph; no backward candidate is supplied or inspected.
    """
    # @var statements Mathematical facts determined by the supported model and accepting trace.
    statements = claims()
    if not any(goal["status"] == "mapped" for goal in request["goals"]):
        return {"nodes":[],"edges":[]}
    # @var keys Forward facts that can each be proved from the existing definitions.
    keys = ("trace_witness","trace_guard","cost_lower_bound")
    return {"nodes":[node(key,"forward",statements[key],request) for key in keys],
            "edges":[edge("derive_"+key,[],key,key,"forward") for key in keys]}


def backward(request):
    """Decompose every selected target before seeing any forward candidates.

    @param request Backward request with the same fixed IR and goals as the forward request.
    @return Obligations, original roots and independently available alternative routes.
    """
    # @var statements, nodes, edges Local decomposition data; original goals are never dropped.
    statements,nodes,edges = claims(),[],[]
    for goal in request["goals"]:
        # @var root Original selected target, including unsupported targets with no invented term.
        root = "goal/" + goal["key"]
        nodes.append(node(root,"root",goal["proposition"],request,goal["key"],[goal["key"]]))
        if goal["status"] != "mapped":
            continue
        for key in ("task_witnesses","response_bridge","direct_jobs"):
            nodes.append(node(key,"backward",statements[key],request))
        edges.extend([edge("via_witness",["task_witnesses","response_bridge"],root,"root_via_witness","backward"),
                      edge("via_jobs",["direct_jobs"],root,"root_via_jobs","backward")])
    return {"nodes":nodes,"edges":edges,"roots":["goal/"+goal["key"] for goal in request["goals"]]}


def align(left, right, request):
    """Propose a directed instantiation only after both independent graphs exist.

    @param left Completed forward candidate graph.
    @param right Completed backward obligation graph.
    @param request Shared frozen provenance, without additional mathematical assumptions.
    @return Alignment record and its explicit implication-check hyperedge, when applicable.
    """
    # @var available, needed Candidate and obligation keys inspected by the alignment phase.
    available = {item["key"]:item for item in left["nodes"]}
    needed = {item["key"]:item for item in right["nodes"]}
    if "trace_witness" not in available or "task_witnesses" not in needed:
        return [],[]
    # @var substitution Universal trace parameters specialized to a task's priority prefix and Fig.3 initial value.
    substitution = {"hp":call("prefix",var("i"),var("ts")),"p":var("p"),
                    "t":call("ir_initial",call("prefix",var("i"),var("ts")),var("p"))}
    record = {"key":"trace_to_tasks","from":"trace_witness","to":"task_witnesses",
              "direction":"support_implies_obligation","instantiation":substitution,
              "binders":[["ts","TaskSet"],["i","Nat"],["p","Task"]],
              "conditions":["fig3_accepts ts","nth_error ts i = Some p"],
              "rule":"instantiate_witness","edge":"align_trace_to_tasks",
              "bridge_obligations":["response_bridge"],"status":"candidate",
              "freeze":request["freeze"],"review_revision":request["review_revision"]}
    return [record],[edge(record["edge"],["trace_witness"],"task_witnesses","instantiate_witness","alignment")]


def validate(graph, choices):
    """Check route references and reject cycles in the selected dependency graph.

    @param graph Candidate nodes and hyperedges for one fixed run.
    @param choices Conclusion-to-edge choices representing one route per node.
    @return Node and edge dictionaries for planning.
    @raise Rejected If an identity, premise, route ownership or selected cycle is invalid.
    """
    # @var nodes, edges Indexed candidates; duplicate identities must not disappear during indexing.
    nodes = {item["key"]:item for item in graph["nodes"]}
    edges = {item["key"]:item for item in graph["edges"]}
    if len(nodes) != len(graph["nodes"]) or len(edges) != len(graph["edges"]):
        raise Rejected("duplicate_node","Duplicate candidate identity")
    for item in edges.values():
        if item["conclusion"] not in nodes or any(p not in nodes for p in item["premises"]):
            raise Rejected("missing_premise",item["key"])
        if len(set(item["premises"])) != len(item["premises"]):
            raise Rejected("duplicate_premise",item["key"])
    if not isinstance(choices,dict):
        raise Rejected("invalid_selection","Expected conclusion-to-route choices")
    for target,selected in choices.items():
        if selected not in edges or edges[selected]["conclusion"] != target:
            raise Rejected("route_mismatch",str(target))
    # @var active, done DFS marks distinguish a cycle from a shared prerequisite.
    active,done = set(),set()

    def visit(key):
        """Traverse all selected joint premises.

        @param key Current node identity.
        @raise Rejected If the selected route recursively depends on itself.
        """
        if key in active:
            raise Rejected("cyclic_route",key)
        if key in done:
            return
        active.add(key)
        if key in choices:
            for premise in edges[choices[key]]["premises"]:
                visit(premise)
        active.remove(key)
        done.add(key)

    for key in choices:
        visit(key)
    return nodes,edges


def plan(graph, choices):
    """Report exact open leaves without turning a checked implication into a completed theorem.

    @param graph Verified candidate graph with actual complete-node and conditional-edge outcomes.
    @param choices Selected derivation for each supported conclusion.
    @return Per-root status, required nodes, usable routes and unresolved joint premises.
    """
    # @var nodes, edges Validated graph indices used for dependency expansion.
    nodes,edges = validate(graph,choices)
    results = []
    for root in graph["roots"]:
        # @var visited, gaps, routes This root's complete selected dependency closure.
        visited,gaps,routes = set(),[],[]

        def expand(key):
            """Collect remaining obligations in a selected route.

            @param key Node to inspect under this root.
            """
            if key in visited:
                return
            visited.add(key)
            if nodes[key].get("complete"):
                return
            selected = edges.get(choices.get(key))
            if selected is None or selected.get("outcome") not in ("conditional","complete"):
                gaps.append(key)
                return
            routes.append(selected["key"])
            for premise in selected["premises"]:
                expand(premise)
            if not selected["premises"]:
                gaps.append(key)

        expand(root)
        results.append({"root":root,"status":"proved" if nodes[root].get("complete") else "unproved",
                        "required":sorted(visited),"routes":routes,"open":list(dict.fromkeys(gaps))})
    return results
