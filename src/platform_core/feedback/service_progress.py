"""Build a concrete W06 proof refinement without changing the mathematical contract."""

from copy import deepcopy

from platform_core.reasoning.graph import node, edge
from platform_core.reasoning.statements import claims


#: General lemmas have no task-analysis premise; capacity_witnesses remains a separate open claim.
TITLES = {
    "service_monotone":"服务量随时间单调不减",
    "counters_before_release":"释放前的服务计数均为零",
    "service_never_exceeds_demand":"任意时刻服务量不超过实际需求",
    "pending_dispatch":"待完成作业迫使调度不低于自身优先级的作业",
    "pending_window_balance":"待完成区间：自身服务与非自身服务之和等于区间长度",
    "capacity_implies_service_lower":"具体容量见证足以推出截止期服务下界",
    "capacity_witnesses":"待证明：任务工作量见证保证每个作业存在容量见证",
}


def refine(proposal, graph, choices, feedback):
    """Populate a reviewable service-bound graph using existing immutable scope.

    @param proposal Mutable proposal receiving exact additions, findings and proof tasks.
    @param graph Independent copy of the parent's graph.
    @param choices Independent copy of the explicitly selected historical route.
    @param feedback Original request with its exact addressed node.
    @return None; an unsupported input produces an explanatory needs_details proposal.
    """
    # @var statements, nodes Typed claims and existing graph objects.
    statements = claims()
    nodes = {item["key"]:item for item in graph["nodes"]}
    # @var required Existing split targets must exactly match the supported integer-time model.
    required = {"response_bridge":"response_bridge","proposed_service_lower":"service_lower",
                "proposed_service_upper":"service_upper"}
    if (feedback["target"]["kind"] != "node" or feedback["target"]["key"] not in required or
        any(key not in nodes or nodes[key]["statement"] != statements[claim] for key,claim in required.items())):
        proposal["status"] = "needs_details"
        proposal["findings"].append("请在已拆分服务上下界的运行中选择调度桥接或服务上下界节点。")
        return
    if any(key in nodes for key in TITLES):
        proposal["status"] = "needs_details"
        proposal["findings"].append("该运行已包含服务计数路线；可采用原提案追加预算，或针对容量见证义务继续论证。")
        return
    # @var origin The unchanged bridge supplies frozen source and context identities.
    origin = nodes["response_bridge"]
    # @var key, title, added Newly introduced claim; no source text or status is treated as proof.
    for key,title in TITLES.items():
        added = node(key,"backward" if key == "capacity_witnesses" else "forward",
                     statements[key],origin,title,origin["source_keys"])
        graph["nodes"].append(added)
        proposal["changes"].append({"kind":"add_node","object":key,"field":"statement","label":title,
                                    "before":None,"after":deepcopy(added)})
        proposal["tasks"].append({"key":key,"stage":"proof","kind":"prove_claim","target":key,
                                  "statement":added["statement"],"formal":added["formal"],"status":"open"})
    # @var relations Joint premises are explicit; the open analytical witness has no proof constructor.
    relations = [edge("derive_"+key,[],key,key,"forward") for key in TITLES if key != "capacity_witnesses"]
    relations.extend([
        edge("service_upper_from_execution",["service_never_exceeds_demand"],
             "proposed_service_upper","service_upper_from_execution","backward"),
        edge("service_lower_from_capacity",["capacity_witnesses","capacity_implies_service_lower"],
             "proposed_service_lower","service_lower_from_capacity","backward")])
    # @var relation, conclusion, previous Exact added connection and its prior route selection.
    for relation in relations:
        graph["edges"].append(relation)
        conclusion = relation["conclusion"]
        previous = choices.get(conclusion)
        choices[conclusion] = relation["key"]
        proposal["changes"].extend([
            {"kind":"add_edge","object":relation["key"],"field":"joint_premises",
             "label":"提交实际检查的局部推导","before":None,"after":deepcopy(relation)},
            {"kind":"select_route","object":conclusion,"field":"selected_route",
             "label":"采用服务计数路线","before":previous,"after":relation["key"]}])
    proposal["owner"] = "proof"
    proposal["checks"].update(structure="passed",types="passed")
    proposal["findings"].extend([
        "保留整数时间、任意合法释放、同任务作业不预设 FIFO 的原合同；本轮仅增加待检查的证明路线。",
        "非自身服务计数包含所有其他作业；尚未将其等同于高优先级任务工作量。",
        "容量见证仍需从任务级工作量见证证明，涉及忙区间、先前释放的干扰作业及同任务积压；它是开放义务，不是新增假设或已完成证明。"])
