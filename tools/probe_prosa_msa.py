"""Inspect the installed Prosa bridge and retain its actual dependency closure."""
from pathlib import Path
import subprocess, json, re, hashlib
# @var root Local development checkout; no files in the old prototype are modified.
root=Path("/mnt/c/Users/zhenghui/Desktop/autoRTA-platform")
# @var directory Isolated probe retaining source and tool output for review.
directory=root/"artifacts/msa/prosa-probe"
directory.mkdir(parents=True,exist_ok=True)
# @var prefix Explicit installed toolchain selected for every command.
prefix=["opam","exec","--root=/home/ther/.local/share/autorta-opam","--switch=autorta-3.0","--"]
def run(label,args):
    """Execute and retain one actual compiler or audit command.
    @param label Log basename.
    @param args Command vector inside the pinned opam switch.
    @return Decoded successful output.
    """
    result=subprocess.run(prefix+args,cwd=directory,capture_output=True,timeout=120)
    output=result.stdout+result.stderr
    (directory/(label+".log")).write_bytes(output)
    if result.returncode:
        raise RuntimeError(label+": "+output.decode(errors="replace")[-2000:])
    return output.decode()
# @var source Bridge between standard Nat.le and MathComp's boolean comparison.
source="""From Stdlib Require Import Arith.PeanoNat.
Require Import prosa.util.div_mod.
(** @param d Natural divisor. @param m Smaller argument. @param n Larger argument.
    @return Standard-library inequality obtained through MathComp reflection. *)
Lemma msa_ceil_monotone : forall d m n, Nat.le m n ->
    Nat.le (div_ceil m d) (div_ceil n d).
Proof.
  intros d m n H.
  exact (elimT leP (div_ceil_monotone1 d m n (introT leP H))).
Qed.
Print Assumptions msa_ceil_monotone.
Print All Dependencies msa_ceil_monotone.
"""
(directory/"Probe.v").write_text(source)
run("compile",["rocq","compile","-q","Probe.v"])
# @var output, coqlib Independent kernel output and actual installed library directory.
output=run("kernel",["rocqchk","-o","Probe"])
coqlib=Path(run("where",["rocq","compile","-where"]).strip()).resolve()
# @var modules Verified files loaded transitively by the real kernel.
modules={}
for name in sorted(set(re.findall(r"(?m)^\s*\[intern\s+(.+?\.vo)\s+\.\.\.",output))):
    path=Path(name).resolve()
    if path.is_relative_to(coqlib):
        source=path.with_suffix(".v")
        if not source.is_file():
            raise RuntimeError("Missing source: "+str(source))
        modules[path.relative_to(coqlib).as_posix()]={"vo_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                "source_sha256":hashlib.sha256(source.read_bytes()).hexdigest()}
(directory/"closure.json").write_text(json.dumps({"modules":modules},indent=2)+"\n")
print(json.dumps({"modules":len(modules),"kernel_summary":output.split("CONTEXT SUMMARY")[-1]}),flush=True)
