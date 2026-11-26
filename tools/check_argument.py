"""Compile a platform-generated theorem/lemma development in the pinned Rocq environment."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def check(source, theorem=None):
    """Check the module and, for a proof, audit the named exported theorem."""
    if theorem is not None and (not isinstance(theorem, str) or not re.fullmatch(r"[a-z][a-z_0-9]*", theorem)):
        raise ValueError("Expected a generated theorem name")
    config = json.loads((Path(__file__).resolve().parents[1] / "configs/toolchain.json").read_text())
    prefix = ["opam", "exec", "--root=" + config["opam_root"], "--switch=" + config["switch"], "--"]
    env = {k: v for k, v in os.environ.items() if k not in {"COQPATH", "ROCQPATH", "COQFLAGS", "ROCQFLAGS"}}
    with TemporaryDirectory(prefix="autovisa-argument-") as work:
        def run(args):
            """@param args Fixed tool arguments. @return Completed process with combined diagnostic output."""
            return subprocess.run(prefix + args, cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, timeout=config["command_timeout_seconds"])
        version = run(["rocq", "--version"]).stdout.strip()
        if "version " + config["expected_packages"]["rocq-core"] not in version:
            raise RuntimeError("Rocq version differs from the pinned toolchain")
        Path(work, "Argument.v").write_text(source, encoding="utf8")
        compiled = run(["rocq", "compile", "-q", "Argument.v"])
        kernel = run(["rocqchk", "-silent", "Argument"]) if compiled.returncode == 0 else None
        kernel_checked = kernel is not None and kernel.returncode == 0
        assumptions = None
        log = compiled.stdout
        if theorem is not None and kernel_checked:
            Path(work, "Audit.v").write_text(
                f"Require Argument.\nPrint Assumptions Argument.{theorem}.\n", encoding="utf8"
            )
            audit = run(["rocq", "compile", "-q", "Audit.v"])
            output = audit.stdout.strip()
            passed = audit.returncode == 0 and output == "Closed under the global context"
            assumptions = {"theorem": theorem, "passed": passed, "output": output[-4000:]}
            if not passed:
                log += "\nAssumption audit failed for " + theorem + ".\n" + output
        return {"version": version, "compiled": compiled.returncode == 0,
                "checked": kernel_checked and (theorem is None or bool(assumptions and assumptions["passed"])),
                "kernelChecked": kernel_checked, "assumptionAudit": assumptions,
                "log": log[-12000:], "kernel": kernel.stdout[-4000:] if kernel else ""}


if __name__ == "__main__":
    request = json.load(sys.stdin)
    print(json.dumps(check(request["source"], request.get("theorem"))))
