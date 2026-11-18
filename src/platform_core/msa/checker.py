"""Versioned library environments for generic MSA checks, separate from legacy case fixtures."""

import json
import os
from pathlib import Path
from platform_core.evidence.rocq import Rocq
from platform_core.evidence.storage import encoded, sha
from platform_core.evidence.terms import Rejected

#: Reviewed reflection bridge; it does not add a hypothesis or change a natural-number model.
CEIL_BRIDGE = """(** @param d Natural divisor. @param m Smaller input. @param n Larger input.
    @return Nat.le consequence of the Prosa theorem, via MathComp's proved reflection lemma. *)
Lemma msa_ceil_monotone : forall d m n, Nat.le m n ->
    Nat.le (prosa.util.div_mod.div_ceil m d) (prosa.util.div_mod.div_ceil n d).
Proof.
  intros d m n H.
  exact (elimT leP (div_ceil_monotone1 d m n (introT leP H))).
Qed.
"""


class MsaRocq(Rocq):
    """Reuse kernel auditing with a standalone, explicitly selected library environment.

    @ivar imports Fixed imports selected by the adapter, never supplied as user source.
    @ivar model_names Empty tuple: this checker does not compile a case-specific scheduling model.
    @ivar profile, profile_id Frozen library, compiler and implementation identities.
    @ivar config, prefix, env Verified command settings and process environment.
    @ivar work, models, maps Private compilation directory and namespace mapping.
    @ivar objects, base, lock, coqlib Evidence store, shared manifest and installed library identities.
    """

    def __init__(self, root, work, objects, library):
        """Verify one library environment without changing an earlier run's policy.

        @param root Current checkout used only to create a new environment version.
        @param work New private directory.
        @param objects Durable content-addressed evidence store.
        @param library Reviewed library profile selected by the domain adapter.
        """
        self.root,self.objects = Path(root),objects
        self.work = Path(work)
        self.work.mkdir(parents=True,exist_ok=True)
        self.models = self.work/"models"
        self.models.mkdir()
        self.model_names,self.maps = (),[]
        self.config = json.loads((self.root/"configs/toolchain.json").read_bytes())
        self.config["command_timeout_seconds"] = 180 if library=="prosa-ceil-v1" else 60
        self.prefix = ["opam","exec","--root="+self.config["opam_root"],"--switch="+self.config["switch"],"--"]
        self.env = {key:value for key,value in os.environ.items()
                    if key not in {"COQPATH","ROCQPATH","COQLIB","COQCORELIB","ROCQFLAGS","COQFLAGS"}}
        self.env["LC_ALL"]="C"
        self.base = {"files":{},"commands":[]}
        self.imports = "From Stdlib Require Import Arith.PeanoNat.\n"
        # @var expected, locks Baseline package requirements and immutable source identities.
        expected = dict(self.config["expected_packages"])
        locks = {}
        self.lock = json.loads((self.root/"toolchain/library-lock.json").read_bytes())["modules"]
        if library=="prosa-ceil-v1":
            # @var extension Reviewed exact closure, not blanket permission to import all Prosa modules.
            extension = json.loads((self.root/"toolchain/prosa-ceil-lock.json").read_bytes())
            expected.update(extension["packages"])
            self.lock = {**self.lock,**extension["modules"]}
            self.imports += "Require Import prosa.util.div_mod.\n"
            locks["toolchain/prosa-ceil-lock.json"] = objects.put(encoded(extension))
        elif library!="stdlib":
            raise Rejected("unknown_library_profile",library)
        self.coqlib = Path(self.run(self.base,self.models,"where",["rocq","compile","-where"]).strip()).resolve()
        # @var version, packages Actual tool versions must match the selected environment contract.
        version = self.run(self.base,self.models,"version",["rocq","--version"]).strip()
        packages = self.run(self.base,self.models,"packages",["opam","list","--root="+self.config["opam_root"],
                            "--switch="+self.config["switch"],"--installed","--columns=name,version","--short"])
        installed = dict(line.split() for line in packages.splitlines() if len(line.split())==2)
        for key,value in expected.items():
            if installed.get(key)!=value:
                raise Rejected("environment_mismatch",key)
        for relative in self.lock:
            self.foundation(relative)
        for relative in ("configs/toolchain.json","toolchain/library-lock.json","src/platform_core/msa/checker.py",
                         "src/platform_core/msa/proof.py","src/platform_core/msa/mapping.py",
                         "src/platform_core/evidence/rocq.py","src/platform_core/analysis_ir/language.py"):
            locks[relative] = objects.put((self.root/relative).read_bytes())
        # @var binaries Executable bytes are pinned alongside their reported versions.
        binaries = self.run(self.base,self.models,"binaries",["which","rocq","rocqchk"]).splitlines()
        self.base["files"].update({"locked/"+key:value for key,value in locks.items()})
        self.profile = {"library":library,"packages":expected,"rocq":version,"locks":locks,
                        "imports":self.imports,"allowed_axioms":[],"limits":self.config["command_timeout_seconds"],
                        "binaries":{Path(name).name:sha(Path(name).read_bytes()) for name in binaries}}
        self.profile_id = objects.put(encoded(self.profile))
