"""Translate reviewed MSA mathematics through explicit, source-independent domain adapters."""

from platform_core.analysis_ir.language import expression, identifier, MappingFailure
from platform_core.evidence.storage import encoded, sha

#: Runtime capabilities are selected explicitly, never inferred from a paper title or hash.
CAPABILITIES = {
    "nat_arithmetic_v1": {
        "title":"自然数算术子问题", "time":"integer_ticks", "library":"stdlib",
        "signatures":{}, "limitations":["不包含调度、到达轨迹或自动文本形式化。"]
    },
    "prosa_ceil_v1": {
        "title":"Prosa 整数向上取整", "time":"integer_ticks", "library":"prosa-ceil-v1",
        "signatures":{"ceil_div":(["Nat","Nat"],"Nat","prosa.util.div_mod.div_ceil")},
        "limitations":["复用 div_ceil 及其单调性；不声明完整 RTA 或调度定理。"]
    },
}
#: Fully qualified functions avoid accidental MathComp notation changes.
OPERATORS = {"add":"Nat.add","sub":"Nat.sub","mul":"Nat.mul","div":"Nat.div","min":"Nat.min",
             "le":"Nat.le","lt":"Nat.lt","eq":"@eq nat","and":"and"}
#: Adapters in this slice expose only these two sorts.
SORTS = {"Nat":"nat","Prop":"Prop"}


def render(tree, signatures):
    """Render a previously type-checked natural arithmetic tree with hygienic variable names.

    @param tree Validated structured expression.
    @param signatures Typed call signatures including generated function names.
    @return Rocq expression; source prose and descriptions are never executable.
    """
    # @var op Fixed constructor controlling source generation.
    op = tree["op"]
    if op == "var":
        return "msa_var_"+tree["name"]
    if op == "nat":
        return str(tree["value"])
    if op == "call":
        return "("+ " ".join([signatures[tree["symbol"]][2],*(render(arg,signatures) for arg in tree["args"])])+")"
    if op in ("forall","exists"):
        return f'({op} (msa_var_{tree["name"]} : {SORTS[tree["sort"]]}), {render(tree["body"],signatures)})'
    if op == "implies":
        return f'({render(tree["left"],signatures)} -> {render(tree["right"],signatures)})'
    # @var operator Equality needs an explicit sort because imported libraries can change notation.
    operator = OPERATORS[op]
    if op == "eq":
        operator = "eq"
    return f'({operator} {render(tree["left"],signatures)} {render(tree["right"],signatures)})'


def validate(tree, environment, signatures):
    """Type-check the supported fragment before emitting any proof-assistant text.

    @param tree Structured expression or unresolved null.
    @param environment Lexically available input variables.
    @param signatures Declared callable definitions.
    @return Inferred sort and hygienically rendered expression.
    """
    if tree is None:
        raise MappingFailure("expression_required","文字条目还没有结构化表达式。")
    # @var sort Existing Analysis IR checker validates bindings, arities and operand types.
    sort,_ = expression(tree,environment,signatures)
    # @var visit Recursive capability check; a well-typed broader IR can still be unsupported here.
    def visit(node):
        """Reject constructors and quantified sorts outside this adapter.

        @param node Current expression node.
        """
        if node["op"]=="sum" or (node["op"] in ("forall","exists") and node["sort"]!="Nat"):
            raise MappingFailure("unsupported_expression","当前适配器只支持自然数和命题。")
        for value in node.values():
            if isinstance(value,dict):
                visit(value)
            elif isinstance(value,list):
                for child in value:
                    if isinstance(child,dict):
                        visit(child)
    visit(tree)
    return sort,render(tree,signatures)


def prepare(frozen):
    """Map every selected goal and all shared premises, preserving unsupported content as gaps.

    @param frozen Immutable reviewed MSA context.
    @return Auditable mapping result; no theorem is marked proved by translation.
    """
    # @var document, capability Exact frozen input and explicitly chosen adapter.
    document = frozen["document"]
    capability = CAPABILITIES.get(document["scope"].get("adapter"))
    # @var result Mapping includes complete input and provenance links, including excluded entries.
    result = {"freeze":frozen["id"],"revision":frozen["revision"],"kind":"mapping",
              "adapter":document["scope"].get("adapter"),"proof_mode":document["proof_mode"],
              "status":"blocked","gaps":[],"goals":[],"definitions":[],"premises":[],
              "bindings":{entry["key"]:{"revision":frozen["revision"],"sources":entry["sources"],
                          "decision":entry["decision"]} for entry in document["symbols"]+document["items"]},
              "document":document,"source":"","capability":capability}
    try:
        if capability is None:
            raise MappingFailure("unsupported_domain","请显式选择已实现的领域能力；当前不自动假定调度模型。")
        if document["scope"]!={"adapter":result["adapter"],"time":capability["time"]}:
            raise MappingFailure("unsupported_scope","范围含有未映射条件或时间域不匹配。")
        # @var symbols, items Active semantics; excluded author proof text stays in the original document.
        symbols = [entry for entry in document["symbols"] if entry["decision"]!="excluded"]
        items = [entry for entry in document["items"] if entry["decision"]!="excluded"]
        if len({entry["key"] for entry in symbols+items}) != len(symbols+items):
            raise MappingFailure("duplicate_symbol","符号与条目身份必须全局唯一。")
        # @var environment, signatures Global variables and approved function signatures.
        environment = {entry["key"]:entry["sort"] for entry in symbols}
        signatures = dict(capability["signatures"])
        if any(sort!="Nat" for sort in environment.values()):
            raise MappingFailure("unsupported_sort","当前领域能力的全局符号须为 Nat。")
        # @var lines Ordered source definitions; dependency ordering is explicit in the input.
        lines = ["(** Generated from an immutable MSA revision; provenance is retained in the mapping receipt. *)"]
        for index,entry in enumerate(items):
            if entry["material_role"] in ("background","author_proof","scope_limit"):
                raise MappingFailure("unmapped_material",entry["key"]+"：该材料尚未编码为模型、方法或目标，请修订或明确排除。")
            if entry["category"]!="analysis":
                continue
            # @var parameters, local Lexical arguments of a pure analysis definition.
            parameters = entry["parameters"]
            for parameter,_ in parameters:
                identifier(parameter)
            local = dict(parameters)
            if len(local)!=len(parameters) or any(sort!="Nat" for sort in local.values()):
                raise MappingFailure("invalid_binder",entry["key"])
            if entry["key"] in signatures:
                raise MappingFailure("duplicate_symbol",entry["key"])
            # @var inferred, body Type-checked function implementation with no implicit global inputs.
            inferred,body = validate(entry["expression"],local,signatures)
            if inferred!=entry["result"] or inferred not in SORTS:
                raise MappingFailure("sort_mismatch",entry["key"])
            name = "MsaDefinition_"+str(index)
            binders = " ".join(f"(msa_var_{key} : nat)" for key in local)
            lines.extend([f"(** @return Reviewed {inferred} expression; @param inputs Explicit MSA arguments. *)",
                          f"Definition {name} {binders} : {SORTS[inferred]} := {body}."])
            signatures[entry["key"]] = ([sort for _,sort in parameters],inferred,name)
            result["definitions"].append({"key":entry["key"],"rocq":name,"expression":entry["expression"]})
        result["source"] = "\n".join(lines)+"\n"
        # @var entry Every shared model condition must map; none is silently discarded.
        for entry in items:
            if entry["category"]!="model":
                continue
            sort,body = validate(entry["expression"],environment,signatures)
            if entry["parameters"] or entry["result"]!="Prop" or sort!="Prop":
                raise MappingFailure("sort_mismatch",entry["key"]+"：模型条件应为命题。")
            result["premises"].append({"key":entry["key"],"rocq":body,"expression":entry["expression"]})
        # @var key Selected goals are independently classified; shared-context errors block all of them.
        for key in document["selected"]:
            entry = next(item for item in items if item["key"]==key)
            try:
                sort,body = validate(entry["expression"],environment,signatures)
                if entry["parameters"] or entry["result"]!="Prop" or sort!="Prop":
                    raise MappingFailure("sort_mismatch",key+"：目标应为命题。")
                # @var proposition All premises and variables remain explicit in the exported theorem type.
                proposition = " -> ".join([*(item["rocq"] for item in result["premises"]),body])
                if environment:
                    proposition = "forall "+" ".join(f"(msa_var_{key} : nat)" for key in environment)+", "+proposition
                result["goals"].append({"key":key,"status":"mapped","proof_status":"unproved","rocq":proposition,
                                        "expression":entry["expression"]})
            except MappingFailure as error:
                result["gaps"].append({"item":key,"code":error.code,"message":str(error)})
                result["goals"].append({"key":key,"status":"blocked","proof_status":"unproved"})
        result["status"] = "partial" if result["gaps"] else "mapped"
    except MappingFailure as error:
        result["gaps"].append({"code":error.code,"message":str(error)})
        result["goals"] = [{"key":key,"status":"blocked","proof_status":"unproved"} for key in document["selected"]]
    result["translation"] = sha(encoded({"scope":document["scope"],"symbols":document["symbols"],
                                         "source":result["source"],"goals":result["goals"],"premises":result["premises"]}))
    return result
