"""Create reviewable mathematical proposals and dependency impacts from local feedback rules."""

from copy import deepcopy
import re

from platform_core.evidence.storage import encoded, sha
from platform_core.evidence.terms import Rejected
from platform_core.reasoning.graph import validate
from platform_core.reasoning.statements import claims, implies, render, service_bound

#: Supported local intents; an explicit UI choice takes precedence over text classification.
INTENTS = {"auto","advance_service","split_bridge","arrival_condition","alignment_review","reverse_alignment","scope_review"}
#: Chinese labels used in the saved proposal as well as the local workbench.
TITLES = {"advance_service":"推进服务上下界证明","split_bridge":"拆分调度桥接义务","arrival_condition":"核对释放间隔条件",
          "alignment_review":"核对对齐方向与实例化","reverse_alignment":"提出反向对齐",
          "scope_review":"登记模型或目标范围修订","proof_request":"请求构造证明","clarify":"补充反馈说明"}


def resolve(run, target):
    """Resolve the exact node, alignment or derivation referenced by a feedback request.

    @param run Verified W04 execution with all candidate objects.
    @param target Object containing only kind and key.
    @return Deep copy of the addressed historical object.
    @raise Rejected If the target shape or membership is invalid.
    """
    # @var collections Fixed graph families addressable by the feedback Interface.
    collections = {"node":"nodes","alignment":"alignments","edge":"edges"}
    if not isinstance(target,dict) or set(target) != {"kind","key"} or not isinstance(target["kind"],str) or target["kind"] not in collections:
        raise Rejected("invalid_feedback_target","请选择节点、对齐关系或推导关系。")
    for item in run["graph"][collections[target["kind"]]]:
        if item["key"] == target["key"]:
            return deepcopy(item)
    raise Rejected("unknown_feedback_target","反馈对象不属于该运行。")


def classify(text, requested):
    """Choose a supported local interpretation while retaining ambiguous requests for review.

    @param text Original feedback text, which is stored separately without normalization.
    @param requested Explicit intent or auto from the local form.
    @return Intent key and the phrases that explain the interpretation.
    @raise Rejected If an unknown explicit intent was supplied.
    """
    if not isinstance(requested,str) or requested not in INTENTS:
        raise Rejected("invalid_feedback_intent","未知反馈处理方式。")
    if requested != "auto":
        return requested,["用户选择："+TITLES[requested]]
    # @var clauses Positive clauses inspected by the small, documented local classifier.
    clauses = [clause.strip().lower() for clause in re.split(r"[，。；;\n]",text)
               if not re.match(r"\s*(不要|不用|别|无需|不需要|do not|don't)",clause,flags=re.I)]
    # @var positive Text eligible for action matching after explicit negative clauses are omitted.
    positive = " ".join(clauses)
    if re.search(r"(标记|标成|改成|设为).{0,8}(已证明|证明完成)|mark.{0,20}proven",positive):
        return "proof_request",["要求直接改变证明状态"]
    # @var matches Distinct supported intents; multiple mathematical requests require clarification.
    patterns = {
        "advance_service":r"推进服务|服务上下界证明|service bounds|service counting",
        "scope_review":r"连续时间|实数时间|同步释放|仅考虑同步|修改假设|增加假设|改变模型|change.{0,8}scope",
        "reverse_alignment":r"反转|反向对齐|倒过来|reverse.{0,10}align",
        "split_bridge":r"拆分|分解|拆成|split|decompos",
        "arrival_condition":r"释放间隔|最小间隔|到达条件|零星约束|sporadic|arrival",
        "alignment_review":r"对齐方向|实例化|量词|检查对齐|alignment|quantifier",
    }
    matches = {key:re.search(pattern,positive) for key,pattern in patterns.items()}
    found = [key for key,match in matches.items() if match]
    if "reverse_alignment" in found and "alignment_review" in found:
        found.remove("alignment_review")
    if len(found) == 1:
        return found[0],[matches[found[0]].group()]
    return "clarify",["包含多个处理方向，请选择本轮重点。"] if found else ["当前本地规则未识别明确的修改意图。"]


def downstream(graph, seeds, selected=None):
    """Compute affected conclusions through complete hyperedges rather than isolated pairs.

    @param graph Frozen graph with all candidate routes.
    @param seeds Changed or reviewed node identities.
    @param selected Optional conclusion-to-edge map restricting traversal to the selected route.
    @return Sorted affected node identities, including the seeds.
    """
    # @var affected Monotone closure of changed prerequisites and their dependent conclusions.
    affected = set(seeds)
    while True:
        previous = len(affected)
        for edge in graph["edges"]:
            if selected is not None and selected.get(edge["conclusion"]) != edge["key"]:
                continue
            if affected.intersection(edge["premises"]):
                affected.add(edge["conclusion"])
        if len(affected) == previous:
            return sorted(affected)


def build(run, ir, selection, feedback):
    """Produce an immutable proposal, exact differences and prospective impact without adopting changes.

    @param run Original verified derivation execution.
    @param ir Exact W03 mapping belonging to that execution.
    @param selection Historical route selection explicitly referenced by the feedback.
    @param feedback Original request with stable identity, text, target and requested intent.
    @return Proposal body with type-checked draft statements and independently computed impact.
    """
    # @var target, intent, recognized Exact addressed object and an explained local interpretation.
    target = resolve(run,feedback["target"])
    intent,recognized = classify(feedback["text"],feedback["intent"])
    # @var proposal Saved review result, with proof status distinct from draft structural checks.
    proposal = {"schema_version":1,"feedback":feedback["id"],"intent":intent,"title":TITLES[intent],
                "generator":"local_rules","interpretation":recognized,"status":"draft","adopted":False,
                "requires_math_confirmation":False,"changes":[],"tasks":[],"findings":[],
                "checks":{"structure":"not_needed","types":"not_needed","proof":"not_run"},
                "scope":{"model":"unchanged","root_statements":"unchanged"}}
    # @var nodes, draft, choices Frozen indices and a separate hypothetical graph and selection.
    nodes = {node["key"]:node for node in run["graph"]["nodes"]}
    draft,choices = deepcopy(run["graph"]),deepcopy(selection["choices"])
    seeds = ([target["key"]] if feedback["target"]["kind"] == "node" else
             [target["to"]] if feedback["target"]["kind"] == "alignment" else [target["conclusion"]])
    proposal["owner"] = "alignment" if feedback["target"]["kind"] == "alignment" else target.get("side","backward")
    if intent == "advance_service":
        from .service_progress import refine
        refine(proposal,draft,choices,feedback)
    elif intent == "split_bridge":
        if feedback["target"] != {"kind":"node","key":"response_bridge"} or target["statement"] != claims()["response_bridge"]:
            proposal.update(status="needs_details")
            proposal["findings"].append("当前拆分规则针对“工作量见证蕴含任意合法轨迹的截止期保证”，请选中该义务。")
        elif any(node["key"] == "proposed_service_lower" for node in run["graph"]["nodes"]):
            proposal["status"] = "needs_details"
            proposal["findings"].append("该运行已包含服务上下界拆分；请针对新增义务提出下一步反馈。")
        else:
            # @var added New obligations retain every original premise and the [release, release + D) service endpoint.
            added = []
            for direction,label in (("lower","截止期前的服务下界"),("upper","执行服务不超过作业需求")):
                statement = service_bound(direction,target["statement"])
                key = "proposed_service_"+direction
                node = {**deepcopy(target),"key":key,"title":label,"statement":statement,"formal":render(statement),
                        "revision":sha(encoded([feedback["id"],key,statement])),"attempts":[],"proposed":True}
                node.pop("goal",None)
                node.pop("complete",None)
                added.append(node)
                draft["nodes"].append(node)
                proposal["changes"].append({"kind":"add_node","object":key,"field":"statement",
                                            "label":label,"before":None,"after":node})
                proposal["tasks"].append({"key":key,"stage":"proof","kind":"prove_claim","target":key,
                                          "statement":statement,"formal":node["formal"],"status":"open"})
            # @var relation Explicit sufficient-premise proposal; no checker outcome is attached to it.
            relation = {"key":"proposed_bridge_from_bounds","premises":[node["key"] for node in added],
                        "conclusion":"response_bridge","side":"backward","rule":None,"attempt":None,
                        "outcome":"pending","proposed":True}
            draft["edges"].append(relation)
            proposal["changes"].append({"kind":"add_edge","object":relation["key"],"field":"joint_premises",
                                       "label":"用上下界共同支持原桥接义务","before":None,"after":relation})
            # @var old Original bridge route, absent when the bridge is an open leaf.
            old = choices.get("response_bridge")
            choices["response_bridge"] = relation["key"]
            proposal["changes"].append({"kind":"select_route","object":"response_bridge","field":"selected_route",
                                       "label":"拟采用的桥接拆分路线","before":old,"after":relation["key"]})
            # @var sufficiency Exact joint implication that requires its own future proof receipt.
            sufficiency = implies([node["statement"] for node in added],target["statement"])
            proposal["tasks"].append({"key":"check_bounds_sufficiency","stage":"proof","kind":"check_joint_sufficiency",
                                      "target":relation["key"],"statement":sufficiency,"formal":render(sufficiency),"status":"open"})
            proposal["findings"].append("将服务量等于需求量拆成两条相反方向的不等式；原目标、时间端点与全部模型条件保留。")
            proposal["checks"].update(structure="passed",types="passed")
    elif intent == "arrival_condition":
        # @var owners Statements that explicitly retain the legal-arrivals premise.
        owners = [node["key"] for node in nodes.values() if node.get("formal") and "legal_arrivals" in node["formal"]]
        binding = ir["kernel_bindings"]["legal_arrivals"]
        proposal["status"] = "reviewed_no_change"
        proposal["findings"].append("释放间隔条件已包含在 legal_arrivals 的固定模型定义中，并由后续调度义务显式使用。")
        if feedback["target"]["kind"] == "alignment":
            proposal["findings"].append("当前对齐只实例化接受轨迹；其已检查蕴含不需要新增到达假设。到达条件在调度桥接处使用。")
        task = {"key":"review_arrival_scope","stage":"semantics","kind":"condition_audit","status":"recorded",
                "condition":"legal_arrivals","owners":owners,"kernel_binding":binding,
                "source_keys":binding["items"],"finding":"already_in_context"}
        proposal["tasks"].append(task)
        proposal["changes"].append({"kind":"add_review_task","object":target["key"],"field":"condition_review",
                                    "label":"记录条件归属核对","before":None,"after":task})
        proposal["owner"] = "semantics"
    elif intent in ("alignment_review","reverse_alignment"):
        if feedback["target"]["kind"] != "alignment":
            proposal["status"] = "needs_details"
            proposal["findings"].append("请选择具体对齐关系，以便核对蕴含方向和实例化。")
        elif intent == "alignment_review":
            proposal["status"] = "reviewed_no_change"
            task = {"key":"review_alignment","stage":"alignment","kind":"alignment_audit","status":"recorded",
                    "from":target["from"],"to":target["to"],"direction":target["direction"],
                    "instantiation":target["instantiation"],"conditions":target["conditions"],"attempt":target["attempt"]}
            proposal["tasks"].append(task)
            proposal["changes"].append({"kind":"add_review_task","object":target["key"],"field":"alignment_review",
                                        "label":"记录方向、变量替换与所需条件","before":None,"after":task})
            proposal["findings"].append("保留已检查的支持→义务方向，并列出实际实例化与条件。")
        else:
            # @var reversed_relation Draft reverse implication needs its own instantiation and proof.
            reversed_relation = {**deepcopy(target),"from":target["to"],"to":target["from"],
                                 "instantiation":None,"conditions":[],"binders":[],"rule":None,"edge":None,
                                 "status":"candidate","attempt":None}
            proposal["changes"].append({"kind":"replace_alignment","object":target["key"],"field":"alignment",
                                        "label":"对齐方向修订","before":target,"after":reversed_relation})
            required = implies([nodes[target["to"]]["statement"]],nodes[target["from"]]["statement"])
            proposal["tasks"].append({"key":"prove_reverse_alignment","stage":"alignment","kind":"check_reverse_implication",
                                      "target":target["key"],"statement":required,"formal":render(required),"status":"open"})
            proposal["tasks"].append({"key":"rebuild_instantiation","stage":"alignment","kind":"supply_instantiation",
                                      "target":target["key"],"status":"open"})
            proposal["requires_math_confirmation"] = True
            proposal["checks"].update(types="passed")
            proposal["findings"].append("反向蕴含已形成精确待证命题；原实例化和原方向的回执不能作为该反向连接的证明。")
            seeds = [target["from"],target["to"]]
    elif intent == "scope_review":
        proposal.update(status="needs_details",requires_math_confirmation=True,
                        scope={"model":"requested_change","root_statements":"requires_review"},owner="semantics")
        proposal["changes"].append({"kind":"scope_request","object":"context","field":"scope",
                                    "label":"模型或目标范围修订请求","before":ir["scope"],"after":{"requested_text":feedback["text"],"formalization":"pending"}})
        proposal["tasks"].append({"key":"specify_scope","stage":"semantics","kind":"prepare_scope_variant",
                                  "target":"context","status":"open"})
        proposal["findings"].append("已保留具体范围修改请求；新的模型条件与形式目标需要进一步明确。")
        seeds = list(nodes)
    else:
        proposal["status"] = "needs_details"
        proposal["owner"] = "proof" if intent == "proof_request" else proposal["owner"]
        proposal["tasks"].append({"key":"clarify_feedback","stage":proposal["owner"],"kind":"clarify_request",
                                  "target":target["key"],"status":"open"})
        proposal["findings"].append("证明状态由实际证据决定；可继续为该目标构造证明。" if intent == "proof_request" else
                                    "反馈已保存。请指定要拆分的义务、要检查的条件或对齐关系。")
    # Type and structural checks cover only the draft; proof construction and adoption are later steps.
    if proposal["checks"]["structure"] == "passed":
        validate(draft,choices)
    # @var candidate, selected Dependency closures for all candidates and the referenced route revision.
    candidate = downstream(run["graph"],seeds)
    selected = downstream(run["graph"],seeds,selection["choices"])
    # @var current_roots Roots whose selected dependency closure actually includes a changed/reviewed object.
    # @var selected_edges, selected_nodes Relations and nodes participating in the referenced route map.
    selected_edges = [edge for edge in run["graph"]["edges"] if selection["choices"].get(edge["conclusion"]) == edge["key"]]
    selected_nodes = {key for edge in selected_edges for key in [edge["conclusion"],*edge["premises"]]}
    current_roots = [root for root in run["graph"]["roots"] if root in selected and
                     (set(seeds).intersection(selected_nodes) or root in seeds)]
    # @var related Evidence is reported for impact review, never relabeled or invalidated by a proposal.
    related = []
    for edge in run["graph"]["edges"]:
        if edge["conclusion"] in candidate and edge["attempt"]:
            recheck = intent == "scope_review" or (intent == "reverse_alignment" and edge["key"] == target.get("edge"))
            related.append({"attempt":edge["attempt"],"object":edge["key"],
                            "disposition":"recheck_on_adoption" if recheck else "preserved",
                            "reason":"新关系或上下文需要自己的证据。" if recheck else "原命题及原回执保持绑定。"})
    for node in nodes.values():
        for attempt in node["attempts"]:
            if node["key"] in candidate:
                related.append({"attempt":attempt,"object":node["key"],
                                "disposition":"recheck_on_adoption" if intent == "scope_review" else "preserved",
                                "reason":"原运行证据保持不变；采用范围变化后重新评估。" if intent == "scope_review" else "节点陈述没有改变。"})
    proposal["impact"] = {"candidate_nodes":candidate,"candidate_roots":[root for root in run["graph"]["roots"] if root in candidate],
                          "selected_roots":current_roots,"selection":selection["id"],
                          "new_obligations":[task["key"] for task in proposal["tasks"] if task["status"] == "open"],
                          "evidence":related,"proof_status":"unchanged","historical_run":"preserved"}
    proposal["preview"] = {"graph":draft,"choices":choices} if intent in ("split_bridge","advance_service") and proposal["status"] == "draft" else None
    return proposal
