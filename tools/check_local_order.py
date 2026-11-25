"""Check locally proposed scalar implications with the project's Rocq installation."""
import ast
import hashlib
import itertools
import json
import operator
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

BINARY = {ast.Add: ("+", operator.add), ast.Sub: ("-", operator.sub), ast.Mult: ("*", operator.mul)}
ORDER = {ast.Lt: ("<", operator.lt), ast.LtE: ("<=", operator.le), ast.Gt: (">", operator.gt),
         ast.GtE: (">=", operator.ge), ast.Eq: ("=", operator.eq)}


def expression(node, variables, values=None):
    """Render an algebra expression or evaluate it at an integer point.
    @param node Parsed scalar expression. @param variables Allowed local names.
    @param values Optional exact integer assignment.
    """
    if isinstance(node, ast.Name) and node.id in variables:
        return "x"+str(variables.index(node.id)) if values is None else values[node.id]
    if isinstance(node, ast.Constant) and type(node.value) is int and abs(node.value)<=100000:
        return str(node.value) if values is None else node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        x=expression(node.operand,variables,values)
        return "(- "+x+")" if values is None else -x
    if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
        symbol,fn=BINARY[type(node.op)]
        l,r=(expression(n,variables,values) for n in (node.left,node.right))
        return f"({l} {symbol} {r})" if values is None else fn(l,r)
    raise ValueError("Unsupported scalar expression")


def relation(node,variables,values=None):
    """@param node One order comparison. @param variables Names. @param values Optional assignment."""
    if not isinstance(node,ast.Compare) or len(node.ops)!=1 or type(node.ops[0]) not in ORDER:
        raise ValueError("Expected a single order relation")
    symbol,fn=ORDER[type(node.ops[0])]
    l,r=(expression(n,variables,values) for n in (node.left,node.comparators[0]))
    return f"({l} {symbol} {r})" if values is None else fn(l,r)


def check(spec,prefix,config):
    """@param spec Proposed local implication. @param prefix Fixed opam command. @param config Toolchain settings."""
    variables=spec["variables"]
    if not 1<=len(variables)<=8 or len(set(variables))!=len(variables) or not all(re.fullmatch("[a-z][a-z0-9_]{0,24}",v) for v in variables):
        raise ValueError("Invalid scalar variable list")
    expressions=spec["premises"]+[spec["conclusion"]]
    if len(expressions)>16 or any(len(s)>350 for s in expressions):
        raise ValueError("Local claim exceeds scalar checker limits")
    trees=[ast.parse(s,mode="eval").body for s in expressions]
    terms=[relation(t,variables) for t in trees]
    # A concrete point refutes only this implication. Rocq must also accept the witness.
    point=None
    for candidate in itertools.islice(itertools.product((1,0,-1,2),repeat=len(variables)),4096):
        env=dict(zip(variables,candidate))
        if all(relation(t,variables,env) for t in trees[:-1]) and not relation(trees[-1],variables,env):
            point=candidate
            break
    bind=" ".join("x"+str(i) for i in range(len(variables)))
    if point is None:
        statement=f"forall {bind} : R, "+" -> ".join(terms)
        # Positive-factor cancellation may require an explicit order lemma before arithmetic normalization.
        cancellation=" | ".join(f"(apply (Rmult_le_reg_l x{i}); nra)" for i in range(len(variables)))
        proof="intros. first [ lra | nra | "+cancellation+" ]."
    else:
        statement=f"exists {bind} : R, "+" /\\ ".join(terms[:-1]+["~ "+terms[-1]])
        proof="exists "+", ".join(f"({x})" for x in point)+". repeat split; lra."
    src="From Stdlib Require Import Reals Lra Psatz.\nOpen Scope R_scope.\nLemma local_claim : "+statement+".\nProof. "+proof+" Qed.\nPrint Assumptions local_claim.\n"
    with TemporaryDirectory(prefix="autovisa-") as wd:
        Path(wd,"LocalClaim.v").write_text(src,encoding="utf8")
        def run(args):
            result=subprocess.run(prefix+args,cwd=wd,capture_output=True,text=True,timeout=config["command_timeout_seconds"])
            return result.returncode,(result.stdout+result.stderr).strip()
        rc,log=run(["rocq","compile","-q","LocalClaim.v"])
        kernel=""
        if rc==0:
            rc,kernel=run(["rocqchk","-silent","LocalClaim"])
        return {"status":("counterexample" if point is not None else "checked") if rc==0 else "open",
                "source":src,"sourceHash":hashlib.sha256(src.encode()).hexdigest(),"compiler":log[-8000:],
                "kernel":kernel[-1200:],"returncode":rc,"assignment":dict(zip(variables,point)) if point is not None and rc==0 else None}


def main():
    """Read structured obligations on stdin and emit reproducible compiler receipts."""
    config=json.loads((Path(__file__).resolve().parents[1]/"configs/toolchain.json").read_text())
    prefix=["opam","exec","--root="+config["opam_root"],"--switch="+config["switch"],"--"]
    os.environ["LC_ALL"]="C"
    for var in ("COQPATH","ROCQPATH","ROCQFLAGS","COQFLAGS"):
        os.environ.pop(var,None)
    version=subprocess.check_output(prefix+["rocq","--version"],text=True).strip()
    if "version "+config["expected_packages"]["rocq-core"] not in version:
        raise RuntimeError("Unexpected Rocq version")
    results=[]
    for spec in json.load(sys.stdin):
        try:
            results.append(check(spec,prefix,config))
        except (ValueError,SyntaxError,subprocess.TimeoutExpired) as exc:
            results.append({"status":"open","diagnostic":str(exc)})
    print(json.dumps({"version":version,"switch":config["switch"],"checks":results}))


if __name__=="__main__":
    main()
