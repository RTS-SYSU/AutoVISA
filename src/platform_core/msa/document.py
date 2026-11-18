"""Versioned MSA input with explicit review and provenance, independent of paper identity."""

from copy import deepcopy

from platform_core.evidence.terms import Rejected
from platform_core.analysis_ir.language import identifier


def require(condition, code, message):
    """Reject a malformed workflow request with a stable public diagnostic.

    @param condition Required invariant.
    @param code Machine-readable diagnostic.
    @param message Explanation suitable for the local workbench.
    """
    if not condition:
        raise Rejected(code,message)


def text(value, label, maximum=8000):
    """Validate a required human-readable field without interpreting it as code.

    @param value User-supplied value.
    @param label Field name in a diagnostic.
    @param maximum Maximum allowed character count.
    @return Original nonempty string, preserving user text.
    """
    require(isinstance(value,str) and bool(value.strip()) and len(value)<=maximum,
            "invalid_msa",label+"必须为非空文本且不超过 "+str(maximum)+" 个字符。")
    return value


def blank(title):
    """Create an empty semantic input without inheriting any example's assumptions.

    @param title Display title.
    @return A versioned MSA document containing no mathematical choices.
    """
    return {"schema_version":1,"title":title,"description":"","scope":{"adapter":"unselected","time":"unspecified"},
            "proof_mode":"independent","symbols":[],"items":[],"selected":[],"primary":None}


def normalize(value, importing=False):
    """Validate transport structure while retaining unresolved mathematics for later checking.

    @param value Complete versioned MSA JSON object.
    @param importing Whether all incoming review claims must be reset to pending.
    @return Independent document with stable keys and explicit review states.
    """
    require(isinstance(value,dict) and set(value)==set(blank("shape")) and
            type(value["schema_version"]) is int and value["schema_version"]==1,
            "invalid_msa_schema","需要 schema_version=1 的完整 MSA 文档。")
    # @var result Copy prevents a caller from changing saved review state through aliasing.
    result = deepcopy(value)
    text(result["title"],"标题",200)
    require(isinstance(result["description"],str),"invalid_msa","原始描述必须是文本。")
    require(isinstance(result["scope"],dict) and all(isinstance(k,str) and isinstance(v,str)
            for k,v in result["scope"].items()),"invalid_msa","范围应为具名文本字段。")
    require(result["proof_mode"] in ("independent","library_reuse"),"invalid_msa","请选择独立构造或库复用。")
    require(isinstance(result["selected"],list) and all(isinstance(k,str) for k in result["selected"]) and
            len(set(result["selected"]))==len(result["selected"]),"invalid_msa","所选目标必须是不同的条目身份。")
    require(result["primary"] is None or isinstance(result["primary"],str),"invalid_msa","主要目标必须是条目身份。")
    # @var family, entries, keys Each semantic family has distinct stable local identities.
    for family in ("symbols","items"):
        entries = result[family]
        require(isinstance(entries,list) and len(entries)<=200,"invalid_msa","每类条目应为最多 200 项的列表。")
        keys = set()
        # @var entry Semantic item or symbol, reviewed separately from its input source.
        for entry in entries:
            require(isinstance(entry,dict),"invalid_msa","条目必须是对象。")
            # @var expected Explicit fields prevent silently discarding imported mathematical content.
            expected = ({"key","sort","unit","description","sources","decision"} if family=="symbols" else
                        {"key","category","title","description","parameters","result","expression","material_role","sources","decision"})
            require(set(entry)==expected,"invalid_msa","条目字段不符合版本 1 格式。")
            identifier(entry["key"])
            require(entry["key"] not in keys,"duplicate_symbol","条目身份不能重复："+entry["key"])
            keys.add(entry["key"])
            require(isinstance(entry["description"],str),"invalid_msa","解释必须是文本。")
            require(entry["decision"] in ("pending","confirmed","excluded"),"invalid_msa","核对状态不受支持。")
            if importing:
                entry["decision"] = "pending"
            require(isinstance(entry["sources"],list),"invalid_msa","来源必须是列表。")
            if family=="symbols":
                require(isinstance(entry["sort"],str) and isinstance(entry["unit"],str),"invalid_msa","符号需声明类型和单位。")
            else:
                require(entry["category"] in ("model","analysis","goal"),"invalid_msa","条目类别不受支持。")
                text(entry["title"],"条目标题",200)
                require(isinstance(entry["parameters"],list) and all(isinstance(p,list) and len(p)==2 and
                    all(isinstance(v,str) for v in p) for p in entry["parameters"]),"invalid_msa","参数应为 [名称,类型] 列表。")
                require(isinstance(entry["result"],str) and (entry["expression"] is None or isinstance(entry["expression"],dict)),
                        "invalid_msa","需要结构化表达式对象或明确留空。")
                require(entry["material_role"] in ("model_definition","analysis_definition","guarantee_statement",
                    "background","author_proof","scope_limit"),"invalid_msa","材料角色不受支持。")
    return result



def mathematics(document):
    """Select structural mathematical content independently of prose and source corrections.

    @param document Validated MSA document.
    @return Canonical mathematical fields for change classification, not an equivalence proof.
    """
    return {"scope":document["scope"],
            "symbols":[{key:entry[key] for key in ("key","sort","unit")} for entry in document["symbols"]
                       if entry["decision"]!="excluded"],
            "items":[{key:entry[key] for key in ("key","category","parameters","result","expression","material_role")}
                     for entry in document["items"] if entry["decision"]!="excluded"],
            "selected":document["selected"],"primary":document["primary"]}


def revise(before, requested):
    """Invalidate review only where the submitted revision changes its reviewed meaning or source.

    @param before Saved current document.
    @param requested Complete proposed document.
    @return Normalized document and visible field differences.
    """
    # @var after, changes Independent proposed state and a readable exact change list.
    after,changes = normalize(requested),[]
    # @var shared Whether changed shared mathematics requires goals to be reviewed again.
    shared = before["scope"] != after["scope"]
    # @var family, previous, entry, old, changed Stable-identity matching avoids array-position mistakes.
    for family in ("symbols","items"):
        previous = {entry["key"]:entry for entry in before[family]}
        for entry in after[family]:
            old = previous.get(entry["key"])
            changed = old is None or any(old[key]!=entry[key] for key in entry if key!="decision")
            if changed:
                entry["decision"] = "pending"
            if family=="symbols":
                shared = shared or old is None or any(old[key]!=entry[key] for key in ("sort","unit")) or (
                    old["decision"]=="excluded") != (entry["decision"]=="excluded")
            elif entry["category"] in ("model","analysis") or (old is not None and old["category"] in ("model","analysis")):
                shared = shared or old is None or any(old[key]!=entry[key] for key in
                    ("category","parameters","result","expression","material_role")) or (
                    old["decision"]=="excluded") != (entry["decision"]=="excluded")
        shared = shared or any(key not in {entry["key"] for entry in after[family]} and
            (family=="symbols" or old.get("category") in ("model","analysis")) for key,old in previous.items())
    if shared:
        for entry in after["items"]:
            if entry["category"]=="goal" and entry["decision"]!="excluded":
                entry["decision"]="pending"
    # @var key Changes preserve complete before/after values, including removals and explicit confirmations.
    for key in before:
        if before[key] != after[key]:
            changes.append({"field":key,"before":before[key],"after":after[key]})
    return after,changes
