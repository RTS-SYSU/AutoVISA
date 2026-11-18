"""W01: fixed reviewed fixtures only; not a sandbox for arbitrary proof scripts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
MODULES = ["Model", "Analysis", "Target", "Examples", "SmokeTarget"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CheckFailure(RuntimeError):
    pass


class W01:
    def __init__(self):
        self.config = json.loads((ROOT / "configs/toolchain.json").read_text())
        self.policy = json.loads((ROOT / "configs/library-policy.json" ).read_text())
        self.lock = json.loads((ROOT / "toolchain/library-lock.json").read_text())
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run = ROOT / "artifacts/w01" / (stamp + "-" + uuid4().hex[:8])
        self.run.mkdir(parents=True)
        self.prefix = ["opam", "exec", "--root=" + self.config["opam_root"],
                       "--switch=" + self.config["switch"], "--"]
        self.timeout = self.config["command_timeout_seconds"]
        self.env = os.environ.copy()
        for key in ["COQPATH", "ROCQPATH", "COQLIB", "COQCORELIB"]:
            self.env.pop(key, None)
        self.report = {
            "schema_version": 1, "purpose": "w01_model_and_checker_validation",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "w01_status": "running",
            "main_goal": {"id": "case11-fig3-acceptance-soundness-int-v1",
                          "declaration_status": "not_checked", "proof_status": "unproved"},
            "commands": [], "fixtures": [], "checks": {},
            "source_hashes": {}, "library_policy": self.policy["profile"],
            "limitations": [
                "Fixed reviewed fixtures; no untrusted-code sandbox.",
                "Main method theorem remains unproved.",
                "Recheck uses a separate directory/process on the same installed environment.",
                "A clean-machine rebuild of the environment has not been executed."
            ],
        }
        self.build = self.run / "build"
        self.build.mkdir()
        self.map = ["-Q", str(self.build), "AutoRTA"]

    def command(self, label, args, cwd=None, required=True, wrapped=True):
        full = (self.prefix if wrapped else []) + list(args)
        log = self.run / "logs" / (label + ".log")
        log.parent.mkdir(exist_ok=True)
        try:
            result = subprocess.run(full, cwd=cwd or self.run, env=self.env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace",
                                    timeout=self.timeout, check=False)
            rc, output = result.returncode, result.stdout
        except subprocess.TimeoutExpired as exc:
            data = exc.stdout or b""
            output = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
            rc, output = None, output + "\nTIMEOUT\n"
        log.write_text(output, encoding="utf-8")
        self.report["commands"].append({"label": label, "argv": full, "returncode": rc,
                                       "log": str(log.relative_to(self.run)),
                                       "log_sha256": digest(log)})
        if required and rc != 0:
            raise CheckFailure(f"{label} failed (code {rc}); see {log}")
        return rc, output

    def preflight(self, source: Path):
        """Validate the explicit imports of our fixed, reviewed source files."""
        text = source.read_text(encoding="utf-8")
        found = []
        for line in text.splitlines():
            match = re.fullmatch(r"From\s+([\w.]+)\s+Require\s+(?:Import|Export)\s+(.+)\.", line.strip())
            if match:
                found.extend(match[1] + "." + part for part in match[2].split())
        unknown = set(found) - set(self.policy["allowed_direct_imports"])
        if unknown:
            raise CheckFailure(f"Unapproved direct import in {source.name}: {sorted(unknown)}")
        return found

    def environment(self):
        _, version = self.command("rocq-version", ["rocq", "--version"])
        _, installed = self.command("installed-packages",
            ["opam", "list", "--root=" + self.config["opam_root"],
             "--switch=" + self.config["switch"], "--installed",
             "--columns=name,version", "--short"], wrapped=False)
        packages = dict(line.split() for line in installed.splitlines() if len(line.split()) == 2)
        for package, expected in self.config["expected_packages"].items():
            if packages.get(package) != expected:
                raise CheckFailure(f"Version mismatch: {package}: {packages.get(package)} != {expected}")
        _, paths = self.command("tool-paths", ["which", "rocq", "rocqchk"])
        binaries = {p: digest(Path(p).resolve()) for p in paths.splitlines() if Path(p).is_file()}
        _, core = self.command("core-library-path", ["rocq", "compile", "-where"])
        self.coqlib = Path(core.strip()).resolve()
        self.report["environment"] = {
            "rocq_version_output": version.strip(), "installed_packages": packages,
            "binaries_sha256": binaries, "python": sys.version,
            "coqlib": str(self.coqlib), "rebuild_verified": False,
        }
        self.command("switch-export",
            ["opam", "switch", "export", str(self.run / "opam-switch.export"),
             "--root=" + self.config["opam_root"], "--switch=" + self.config["switch"]],
            wrapped=False)
        self.report["environment"]["opam_export_sha256"] = digest(self.run / "opam-switch.export")

    def compile_models(self):
        imports = {}
        for name in MODULES:
            source = ROOT / "proofs" / (name + ".v")
            imports[name] = self.preflight(source)
            self.report["source_hashes"][str(source.relative_to(ROOT))] = digest(source)
            shutil.copy2(source, self.build / source.name)
            self.command("compile-" + name, ["rocq", "compile", "-q"] + self.map + [name + ".v"],
                         cwd=self.build)
            if name == "Target":
                self.report["main_goal"]["declaration_status"] = "typechecked"
        self.report["direct_imports"] = imports
        self.report["main_goal"]["declaration_status"] = "typechecked"
        self.report["checks"]["formal_boundary_examples"] = "passed"
        _, output = self.command("kernel-models",
            ["rocqchk"] + self.map + ["-o", "AutoRTA.Examples", "AutoRTA.Target"],
            cwd=self.build)
        self.inventory_dependencies("models", output, [self.build])
        if not self.safe_kernel(output) or "* Axioms: <none>" not in output:
            raise CheckFailure("Model context contains axioms or unsafe checking settings")

    def inventory_dependencies(self, label, output, local_dirs):
        # rocqchk's actual loaded .vo paths, not names inferred from source text.
        matches = re.findall(r"(?m)^\s*\[intern\s+(.+?\.vo)\s+\.\.\.", output)
        if not matches:
            raise CheckFailure(f"{label}: cannot read actual kernel dependency inventory")
        allowed_roots = [(self.coqlib / "theories").resolve(),
                         (self.coqlib / "user-contrib/Stdlib").resolve()]
        allowed_roots += [Path(p).resolve() for p in local_dirs]
        inventory = []
        for name in sorted(set(matches)):
            path = Path(name).resolve()
            if not any(path.is_relative_to(root) for root in allowed_roots):
                raise CheckFailure(f"{label}: dependency outside allowed roots: {path}")
            if not path.is_file():
                raise CheckFailure(f"{label}: missing loaded dependency: {path}")
            actual_hash = digest(path)
            if path.is_relative_to(self.coqlib):
                relative = str(path.relative_to(self.coqlib))
                locked = self.lock["modules"].get(relative)
                if locked is None or locked["vo_sha256"] != actual_hash:
                    raise CheckFailure(f"{label}: unlisted or changed foundational module: {relative}")
                source = path.with_suffix(".v")
                if locked.get("source_sha256") is not None:
                    if not source.is_file() or digest(source) != locked["source_sha256"]:
                        raise CheckFailure(f"{label}: changed foundational source: {relative}")
            inventory.append({"path": str(path), "sha256": actual_hash})
        self.report.setdefault("dependency_inventories", {})[label] = inventory

    def safe_kernel(self, output):
        if "CONTEXT SUMMARY" not in output:
            raise CheckFailure("Missing independent checker context summary")
        expected = [
            "* Theory: Set is predicative",
            "* Theory: Rewrite rules are not allowed",
            "* Constants/Inductives relying on type-in-type: <none>",
            "* Constants/Inductives relying on unsafe (co)fixpoints: <none>",
            "* Inductives whose positivity is assumed: <none>",
        ]
        return all(line in output for line in expected)

    def fixture(self, name, expected):
        directory = self.run / "fixtures" / name
        directory.mkdir(parents=True)
        source = ROOT / "tests/fixtures" / (name + ".v")
        self.preflight(source)
        self.report["source_hashes"][str(source.relative_to(ROOT))] = digest(source)
        shutil.copy2(source, directory / "Candidate.v")
        self.command(name + "-candidate", ["rocq", "compile", "-q"] + self.map + ["Candidate.v"],
                     cwd=directory)
        (directory / "Exact.v").write_text(
            "From AutoRTA Require Import SmokeTarget.\n"
            "Require Import Candidate.\n"
            "Definition checked_candidate : smoke_target := Candidate.candidate.\n",
            encoding="utf-8")
        rc, exact_output = self.command(name + "-exact", ["rocq", "compile", "-q"] + self.map + ["Exact.v"],
                             cwd=directory, required=False)
        if rc is None:
            raise CheckFailure(f"{name}: timed out, cannot classify as target mismatch")
        if rc != 0:
            if "expected to have type" not in exact_output:
                raise CheckFailure(f"{name}: wrapper failed for a reason other than a target mismatch")
            status = "target_mismatch"
        else:
            kernel_rc, kernel = self.command(name + "-kernel", ["rocqchk"] + self.map +
                ["-Q", str(directory), "", "-o", "Exact"], cwd=directory, required=False)
            if kernel_rc is None:
                raise CheckFailure(f"{name}: independent checker timed out")
            if kernel_rc != 0:
                status = "kernel_rejected"
            else:
                self.inventory_dependencies(name, kernel, [self.build, directory])
                if not self.safe_kernel(kernel):
                    status = "unsafe_checking"
                else:
                    (directory / "Audit.v").write_text(
                        "Require Import Exact.\nPrint Assumptions Exact.checked_candidate.\n",
                        encoding="utf-8")
                    _, audit = self.command(name + "-assumptions",
                        ["rocq", "compile", "-q"] + self.map + ["Audit.v"], cwd=directory)
                    if "Axioms:" in audit:
                        status = "unapproved_assumption"
                    elif audit.strip() == "Closed under the global context":
                        status = "accepted"
                    else:
                        raise CheckFailure(f"{name}: unrecognized assumption audit output")
        expected_states = [expected] if isinstance(expected, str) else expected
        passed = status in expected_states
        self.report["fixtures"].append({"name": name, "expected": expected, "actual": status,
                                        "passed": passed})
        if not passed:
            raise CheckFailure(f"{name}: expected {expected}, got {status}")
        return directory

    def recheck(self, good):
        dest = self.run / "recheck"
        model_copy, candidate_copy = dest / "models", dest / "candidate"
        model_copy.mkdir(parents=True)
        candidate_copy.mkdir()
        for module in MODULES:
            shutil.copy2(self.build / (module + ".vo"), model_copy / (module + ".vo"))
        for module in ["Candidate", "Exact"]:
            shutil.copy2(good / (module + ".vo"), candidate_copy / (module + ".vo"))
        args = ["-Q", str(model_copy), "AutoRTA", "-Q", str(candidate_copy), ""]
        _, output = self.command("independent-kernel-recheck",
            ["rocqchk"] + args + ["-o", "Exact", "AutoRTA.Examples", "AutoRTA.Target"], cwd=dest)
        self.inventory_dependencies("recheck", output, [model_copy, candidate_copy])
        if not self.safe_kernel(output) or "* Axioms: <none>" not in output:
            raise CheckFailure("Recheck context is not closed and safe")
        self.report["checks"]["separate_directory_kernel_recheck"] = "passed"

    def execute(self):
        for rel in ["configs/toolchain.json", "configs/library-policy.json", "configs/target.json",
                    "docs/contracts/case11-integer-dm-soundness.zh.md", "toolchain/library-lock.json", "tools/check_w01.py"]:
            self.report["source_hashes"][rel] = digest(ROOT / rel)
        self.environment()
        self.compile_models()
        good = self.fixture("Good", "accepted")
        self.fixture("WrongTarget", "target_mismatch")
        self.fixture("ExtraAssumption", "unapproved_assumption")
        self.fixture("Admitted", "unapproved_assumption")
        self.fixture("UnsafeGuard", "unsafe_checking")
        self.recheck(good)
        self.report["w01_status"] = "passed"

    def save(self):
        self.report["finished_at"] = datetime.now(timezone.utc).isoformat()
        path = self.run / "report.json"
        path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (ROOT / "artifacts/w01/latest.json").write_text(
            json.dumps({"report": str(path.relative_to(ROOT)),
                        "sha256": digest(path)}, indent=2) + "\n", encoding="utf-8")
        return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    if os.name == "nt":
        parser.error("Use ./check.ps1 on Windows, or python3 tools/check_w01.py inside Linux/WSL.")
    check = W01()
    try:
        check.execute()
    except (CheckFailure, OSError, ValueError) as exc:
        check.report["w01_status"] = "failed"
        check.report["error"] = str(exc)
    path = check.save()
    print(json.dumps({"w01_status": check.report["w01_status"],
                      "main_goal": check.report["main_goal"],
                      "fixtures": check.report["fixtures"], "report": str(path),
                      "error": check.report.get("error")}, ensure_ascii=False, indent=2))
    return 0 if check.report["w01_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
