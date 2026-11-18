"""Compile in private directories and let Rocq check the submitted term twice."""

import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from .storage import encoded, sha
from .terms import Rejected, SYMBOLS

#: Model units in compilation order. Each importer follows its dependencies.
MODELS = ("Model", "Analysis", "Target", "SmokeTarget", "Service")
#: Fixed imports shared by the candidate and its target wrapper.
IMPORTS = ("From Stdlib Require Import Arith.PeanoNat Lists.List.\n"
           "From AutoRTA Require Import Model Analysis Target SmokeTarget Service.\n")
#: Required kernel summary entries for universe, recursion and positivity checks.
SAFE_LINES = {
    "* Theory: Set is predicative", "* Theory: Rewrite rules are not allowed",
    "* Constants/Inductives relying on type-in-type: <none>",
    "* Constants/Inductives relying on unsafe (co)fixpoints: <none>",
    "* Inductives whose positivity is assumed: <none>",
}


class Rocq:
    """Check proof submissions against one frozen installation and model build.

    @ivar root Project directory containing the reviewed sources and lock files.
    @ivar objects Content-addressed store for sources, logs and compiled objects.
    @ivar work Session directory containing the shared build and temporary attempts.
    @ivar models Private directory for the compiled AutoRTA modules.
    @ivar config Toolchain settings including package versions and command timeout.
    @ivar prefix Argument prefix selecting the configured opam root and switch.
    @ivar env Child process environment with a fixed locale and restricted Rocq search paths.
    @ivar base Shared model-build manifest containing file digests and command records.
    @ivar maps Rocq arguments binding the models directory to the AutoRTA namespace.
    @ivar coqlib Installation root used to resolve foundation modules.
    @ivar lock Expected binary and source digests keyed by library-relative path.
    @ivar profile Serializable identities of reviewed sources, tools, packages and symbols.
    @ivar profile_id Content address of the profile pinned by each new context.
    """
    def __init__(self, root, work, objects):
        """Verify the toolchain and build models for one checker session.

        @param root Project root containing the reviewed configuration and proof sources.
        @param work Private working directory in which the models subdirectory must be new.
        @param objects Object store receiving frozen inputs and build logs.
        @raise Rejected If a tool, package, foundation digest or axiom policy fails validation.
        @raise FileExistsError If the model build directory already exists.
        """
        self.root, self.objects = Path(root), objects
        self.work = Path(work)
        self.work.mkdir(parents=True, exist_ok=True)
        self.models = self.work / "models"
        self.models.mkdir()  # Never load .vo files from an earlier session.
        self.config = json.loads((self.root / "configs/toolchain.json").read_bytes())
        self.prefix = ["opam", "exec", "--root=" + self.config["opam_root"],
                       "--switch=" + self.config["switch"], "--"]
        self.env = {k: v for k, v in os.environ.items()
                    if k not in {"COQPATH", "ROCQPATH", "COQLIB", "COQCORELIB", "ROCQFLAGS", "COQFLAGS"}}
        self.env["LC_ALL"] = "C"
        self.base = {"files": {}, "commands": []}
        self.maps = ["-Q", str(self.models), "AutoRTA"]
        self.coqlib = Path(self.run(self.base, self.models, "where", ["rocq", "compile", "-where"]).strip()).resolve()
        # version comes from Rocq itself; installed maps opam package names to versions.
        version = self.run(self.base, self.models, "version", ["rocq", "--version"]).strip()
        pkgs = self.run(self.base, self.models, "packages", ["opam", "list", "--root=" + self.config["opam_root"],
                        "--switch=" + self.config["switch"], "--installed",
                        "--columns=name,version", "--short"])
        installed = dict(line.split() for line in pkgs.splitlines() if len(line.split()) == 2)
        for key, expected in self.config["expected_packages"].items():
            if installed.get(key) != expected:
                raise Rejected("environment_mismatch", key)
        # bins identifies the executables to hash; locks maps each reviewed input path to its digest.
        bins = self.run(self.base, self.models, "binaries", ["which", "rocq", "rocqchk"]).splitlines()
        locks = {}
        for name in ("toolchain/library-lock.json", "configs/toolchain.json", "configs/library-policy.json",
                     "configs/target.json", "configs/contracts/case11-integer-dm-soundness.zh.md"):
            data = (self.root / name).read_bytes()
            locks[name] = self.objects.put(data)
            if name.endswith("library-lock.json"):
                self.lock = json.loads(data)["modules"]
            if name.endswith("library-policy.json") and json.loads(data)["allowed_axioms"] != []:
                raise Rejected("policy_mismatch", "W02 requires a closed global context")
        # A history-only query must not report a healthy environment if installed files drifted.
        for relative in self.lock:
            self.foundation(relative)
        for name in MODELS:
            path = self.models / (name + ".v")
            path.write_bytes((self.root / "proofs" / path.name).read_bytes())
            locks["proofs/" + path.name] = self.objects.put(path.read_bytes())
            self.run(self.base, self.models, "model-" + name, ["rocq", "compile", "-q", *self.maps, path.name])
            for suffix in (".v", ".vo"):
                p = path.with_suffix(suffix)
                self.base["files"]["models/" + p.name] = self.objects.put(p.read_bytes())
        for name in ("terms.py", "rocq.py", "service.py", "storage.py", "schema.sql"):
            locks["checker/" + name] = self.objects.put(Path(__file__).with_name(name).read_bytes())
        # @var relative Rule and expression implementations contributing to the checked statement language.
        for relative in ("src/platform_core/analysis_ir/language.py",
                         "src/platform_core/reasoning/statements.py", "src/platform_core/reasoning/rules.py"):
            locks[relative] = self.objects.put((self.root / relative).read_bytes())
        self.base["files"].update({"locked/" + k: v for k, v in locks.items()})
        self.profile = {"locks": locks, "packages": self.config["expected_packages"], "rocq": version,
                        "symbols": {k: list(v) for k, v in SYMBOLS.items()},
                        "binaries": {Path(p).name: sha(Path(p).read_bytes()) for p in bins}}
        self.profile_id = self.objects.put(encoded(self.profile))

    def foundation(self, relative):
        """Verify the installed bytes for a reviewed foundation module.

        @param relative POSIX path of the compiled module relative to the library root.
        @return Locked SHA-256 digest of the verified .vo file.
        @raise Rejected If the module is unlisted or a required binary or source differs.
        """
        # Each lock entry binds a compiled binary and, where recorded, its source.
        entry = self.lock.get(relative)
        if entry is None:
            raise Rejected("unapproved_dependency", relative)
        path = self.coqlib / relative
        if not path.is_file() or sha(path.read_bytes()) != entry["vo_sha256"]:
            raise Rejected("dependency_mismatch", relative)
        source = path.with_suffix(".v")
        if entry.get("source_sha256") and (not source.is_file() or sha(source.read_bytes()) != entry["source_sha256"]):
            raise Rejected("dependency_mismatch", str(source))
        return entry["vo_sha256"]

    def run(self, manifest, cwd, label, argv, failure="tool_failure"):
        """Execute one command and archive its output before classifying the result.

        @param manifest Mutable build or receipt manifest receiving the log and command record.
        @param cwd Working directory used by the tool.
        @param label Stage name used as the log key within this manifest.
        @param argv Executable and arguments passed after the opam environment selector.
        @param failure Diagnostic code for a nonzero exit, subject to exact-type diagnostic checks.
        @return Combined stdout and stderr decoded as UTF-8 with outer whitespace removed.
        @raise Rejected If execution fails, times out or returns a nonzero exit code.
        """
        try:
            completed = subprocess.run(self.prefix + argv, cwd=cwd, env=self.env, capture_output=True,
                                       timeout=self.config["command_timeout_seconds"])
            rc, output = completed.returncode, completed.stdout + completed.stderr
        except subprocess.TimeoutExpired as exc:
            rc, output = None, (exc.stdout or b"") + (exc.stderr or b"")
        except OSError as exc:
            rc, output = -1, str(exc).encode()
        # rc is None on timeout and -1 on a launch error; output retains diagnostic bytes in both cases.
        manifest["files"]["logs/" + label] = self.objects.put(output)
        manifest["commands"].append({"stage": label, "argv": argv, "returncode": rc})
        message = output.decode("utf-8", errors="replace").strip()
        if rc is None:
            raise Rejected("timeout", label)
        if rc != 0:
            # Only a type-conversion diagnostic may be reported as an exact-target mismatch.
            if failure == "target_mismatch" and "expected to have type" not in " ".join(message.split()):
                failure = "tool_failure"
            raise Rejected(failure, label + ": " + message[-1500:])
        return message

    def check(self, attempt, typ, candidate, selected, manifest):
        """Compile the proof and check its frozen type, assumptions and actual dependencies.

        @param attempt Hexadecimal attempt ID used to name the two generated modules.
        @param typ Trusted Rocq proposition rendered from the target and its premises.
        @param candidate Rocq declarations generated from the reviewed input language.
        @param selected Prerequisite .vo filenames mapped to accepted object digests.
        @param manifest Mutable receipt collecting sources, logs, modules and dependencies.
        @raise Rejected If compilation, type conversion, kernel checks or dependency audits fail.
        """
        # C identifies the submitted term. E exports that term under the independently generated target type.
        module = "E" + attempt
        candidate_module = "C" + attempt
        with TemporaryDirectory(dir=self.work) as dirname:
            wd = Path(dirname)
            for name, key in selected.items():
                # Dependencies come from accepted receipts, never from the process load path.
                if not re.fullmatch(r"[CE][0-9a-f]{32}\.vo", name):
                    raise Rejected("dependency_mismatch", name)
                (wd / name).write_bytes(self.objects.get(key))
            # flags exposes only this attempt directory in addition to the private model build.
            flags = [*self.maps, "-Q", str(wd), ""]
            def compile_unit(name, source, stage, failure="tool_failure"):
                """Archive one generated source file and compile it in the attempt directory.

                @param name Logical module name and source basename.
                @param source Generated Rocq text to preserve in the manifest.
                @param stage Log key distinguishing this compilation from the other stages.
                @param failure Diagnostic code passed to the runner for compilation errors.
                @return Decoded compiler output, including responses to audit commands.
                @raise Rejected If the compiler rejects the source or the command times out.
                """
                path = wd / (name + ".v")
                path.write_text(source, encoding="utf-8")
                manifest["files"]["sources/" + path.name] = self.objects.put(path.read_bytes())
                return self.run(manifest, wd, stage, ["rocq", "compile", "-q", *flags, path.name], failure)

            compile_unit(candidate_module, getattr(self, "imports", IMPORTS) + candidate, "candidate", "type_error")
            compile_unit(module, getattr(self, "imports", IMPORTS) + f"Require {candidate_module}.\n"
                         f"Definition checked : {typ} := {candidate_module}.candidate.\n",
                         "exact", "target_mismatch")
            kernel = self.run(manifest, wd, "kernel", ["rocqchk", *flags, "-o", module], "kernel_rejected")
            # Match the context summary, not unrelated strings printed while loading constants.
            _, marker, summary = kernel.rpartition("CONTEXT SUMMARY")
            lines = {s.strip() for s in summary.splitlines()}
            if not marker or not SAFE_LINES.issubset(lines):
                raise Rejected("unsafe_checking", "Unexpected independent kernel context")
            # loaded contains paths reported by rocqchk while interning modules, including transitive imports.
            loaded = set(re.findall(r"(?m)^\s*\[intern\s+(.+?\.vo)\s+\.\.\.", kernel))
            # local indexes reusable proof objects by filename; libraries indexes installed objects by relative path.
            local, libraries = {}, {}
            for name in sorted(loaded):
                p = Path(name).resolve()
                key = sha(p.read_bytes())
                if p.parent == wd and (p.name in selected or p.stem in {candidate_module, module}):
                    if p.name in selected and key != selected[p.name]:
                        raise Rejected("dependency_mismatch", p.name)
                    local[p.name] = self.objects.put(p.read_bytes())
                elif p.parent == self.models and p.stem in getattr(self, "model_names", MODELS):
                    if key != self.base["files"].get("models/" + p.name):
                        raise Rejected("dependency_mismatch", p.name)
                elif p.is_relative_to(self.coqlib):
                    rel = p.relative_to(self.coqlib).as_posix()
                    libraries[rel] = self.foundation(rel)
                else:
                    raise Rejected("unapproved_dependency", str(p))
            if set(local) != {*selected, candidate_module + ".vo", module + ".vo"} or not libraries:
                raise Rejected("dependency_mismatch", "Kernel loaded a different local closure")
            manifest["module"], manifest["modules"], manifest["libraries"] = module, local, libraries
            manifest["files"].update({"vo/" + n: k for n, k in local.items()})
            # audit describes the assumptions of the exported term; lines describes the entire kernel context.
            audit = compile_unit("Audit", f"Require {module}.\nPrint Assumptions {module}.checked.\n", "assumptions")
            if audit != "Closed under the global context" or "* Axioms: <none>" not in lines:
                raise Rejected("unapproved_assumption", audit[:1500])
            compile_unit("Symbols", f"Require {module}.\nPrint All Dependencies {module}.checked.\n", "symbols")
