"""Bounded real proof attempts over dynamically mapped MSA targets."""

import time
import re
from tempfile import TemporaryDirectory
from uuid import uuid4
from platform_core.evidence.terms import Rejected
from .document import require
from .checker import MsaRocq, CEIL_BRIDGE


def used_resources(symbol_log):
    """Identify the exposed Prosa resources in Rocq's actual dependency declaration list.

    @param symbol_log Archived Print All Dependencies output, not a candidate's claimed imports.
    @return Fully qualified known resource identities that occur as dependency declarations.
    """
    # @var names Reported short module paths are unambiguous within the locked import closure.
    names = {"div_mod.div_ceil":"prosa.util.div_mod.div_ceil",
             "div_mod.div_ceil_monotone1":"prosa.util.div_mod.div_ceil_monotone1",
             "ssrnat.leP":"mathcomp.ssreflect.ssrnat.leP"}
    return [identity for name,identity in names.items() if re.search(r"(?m)^"+re.escape(name)+r"\s*:",symbol_log)]


def prove(workspace, mapping, max_checks):
    """Attempt selected goals with explicit routes, retaining failures and exact evidence.

    @param workspace MSA persistence Interface.
    @param mapping Immutable mapping result identity.
    @param max_checks Maximum candidate checks; no external model request is made.
    @return New proof receipt linked to the unchanged mapping and freeze.
    """
    require(type(max_checks) is int and 1<=max_checks<=8,"invalid_budget","每次请选择 1 至 8 次检查。")
    # @var mapped, result Exact original translation and new append-only proof attempt.
    mapped = workspace.result(mapping)
    require(mapped["kind"]=="mapping","invalid_mapping","请指定映射记录。")
    result = {"kind":"proof","freeze":mapped["freeze"],"mapping":mapping,"run":uuid4().hex,
              "route":mapped["proof_mode"],"budget":{"checks":max_checks},
              "usage":{"checks":0,"model_calls":0},"status":"open","goals":[],"environment":None,
              "limitations":["当前使用有限的算术规则；尚未接入通用模型驱动双向推理。"]}
    # @var started Wall time includes environment verification and failed compilation.
    started = time.monotonic()
    try:
        require(mapped["status"] in ("mapped","partial"),"mapping_blocked","请先处理共享模型的映射缺口。")
        with TemporaryDirectory(prefix="autorta-msa-check-") as directory:
            # @var checker New environment is pinned in this receipt, never retroactively assigned to old evidence.
            checker = MsaRocq.__new__(MsaRocq)
            try:
                checker.__init__(workspace.root,directory,workspace.ledger.objects,mapped["capability"]["library"])
            except (Rejected,FileNotFoundError):
                result["environment"] = {"id":None,"build":getattr(checker,"base",{}),"status":"rejected"}
                raise
            result["environment"] = {"id":checker.profile_id,"profile":checker.profile,"build":checker.base}
            for goal in mapped["goals"]:
                # @var checked Per-goal status always retains its original obligation.
                checked = {"key":goal["key"],"status":"open","obligation":goal.get("rocq"),
                           "reason":"budget_exhausted","evidence":None}
                result["goals"].append(checked)
                if goal["status"]!="mapped":
                    checked["reason"]="mapping_blocked"
                    continue
                if result["usage"]["checks"]>=max_checks:
                    continue
                # @var attempt, manifest Unique compiled module names and archived tool outputs.
                attempt = uuid4().hex
                manifest = {"files":{},"commands":[]}
                checked["attempt"],checked["evidence"] = attempt,manifest
                # @var reuse Only the library route may invoke a theorem covering this resource goal.
                reuse = mapped["proof_mode"]=="library_reuse" and mapped["capability"]["library"]=="prosa-ceil-v1"
                bridge = CEIL_BRIDGE if reuse else ""
                names = [entry["rocq"] for entry in mapped["definitions"]]
                unfold = ("unfold "+", ".join(names)+" in *; ") if names else ""
                lemmas = "Nat.le_trans, Nat.le_add_r, Nat.le_add_l, Nat.le_refl"
                if reuse:
                    lemmas += ", msa_ceil_monotone"
                # @var candidate Controlled proof strategy, not arbitrary code from input prose.
                candidate = bridge+mapped["source"]+"\nLemma candidate : "+goal["rocq"]+".\nProof. intros; "+unfold+"eauto 6 using "+lemmas+". Qed.\n"
                # @var exact Target references the same archived generated definitions in its candidate module.
                exact = goal["rocq"]
                for name in sorted(names,key=len,reverse=True):
                    exact = re.sub(r"\b"+re.escape(name)+r"\b","C"+attempt+"."+name,exact)
                checked["strategy"] = "prosa-ceil-reflection" if reuse else "bounded-natural-arithmetic"
                checked["reused_resources"] = []
                result["usage"]["checks"] += 1
                try:
                    checker.check(attempt,exact,candidate,{},manifest)
                    checked["reused_resources"] = used_resources(workspace.ledger.objects.get(
                        manifest["files"]["logs/symbols"]).decode("utf-8"))
                    checked.update(status="proved",reason=None)
                except Rejected as error:
                    checked.update(reason=error.code,message=str(error))
            result["status"] = "proved" if result["goals"] and all(goal["status"]=="proved" for goal in result["goals"]) else "open"
    except (Rejected,FileNotFoundError) as error:
        result["error"] = {"code":getattr(error,"code","environment_unavailable"),"message":str(error)}
        if not result["goals"]:
            result["goals"] = [{"key":goal["key"],"status":"open","obligation":goal.get("rocq"),
                               "reason":result["error"]["code"],"evidence":None} for goal in mapped["goals"]]
    result["usage"]["elapsed_seconds"] = round(time.monotonic()-started,3)
    return workspace.save_result(result)
