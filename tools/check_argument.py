"""Compile a platform-generated theorem/lemma development in the pinned Rocq environment."""
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def check(source):
    """@param source Generated Rocq module. @return Compiler and kernel evidence."""
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
        return {"version": version, "compiled": compiled.returncode == 0, "checked": kernel is not None and kernel.returncode == 0,
                "log": compiled.stdout[-12000:], "kernel": kernel.stdout[-4000:] if kernel else ""}


if __name__ == "__main__":
    print(json.dumps(check(json.load(sys.stdin)["source"])))
