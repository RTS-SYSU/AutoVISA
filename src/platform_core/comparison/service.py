"""A small Interface for creating and reopening immutable parent/child comparisons."""

import json
from pathlib import Path
from urllib.parse import urlencode

from platform_core.evidence.storage import encoded
from platform_core.evidence.terms import Rejected
from .differences import compare


class ComparisonWorkspace:
    """Own exact version binding and saved comparison observations.

    @ivar derivations Existing run, route and historical evidence Interface.
    @ivar ledger Shared immutable history and content-addressed storage.
    """

    def __init__(self, derivations):
        """Bind the existing history dependency without creating a proof checker.

        @param derivations Installed DerivationWorkspace over one local catalog.
        """
        self.derivations,self.ledger = derivations,derivations.ledger

    def install(self):
        """Install the append-only comparison index after derivation and continuation history."""
        # @var cursor Schema transaction shared with the existing ledger.
        with self.ledger.db,self.ledger.db.cursor() as cursor:
            cursor.execute(Path(__file__).with_name("schema.sql").read_text())

    def _pair(self, parent, child, parent_selection=None, child_selection=None):
        """Verify actual parentage and resolve each requested route in its owning run.

        @param parent Required parent execution identity, or None when opening the child's picker.
        @param child Child execution identity recorded by an actual adoption.
        @param parent_selection Exact parent route, or None for the current observation.
        @param child_selection Exact child route, or None for the current observation.
        @return Verified parent, child and original adoption request.
        """
        # @var revised, rows, row, request Original child and indexed parent/adoption bindings.
        revised = self.derivations.read(child,child_selection)
        rows = self.ledger.rows("SELECT * FROM proposal_adoptions WHERE run=%s",(child,))
        if not rows:
            raise Rejected("not_linked_run","请选择通过采用提案创建的关联运行。")
        row = rows[0]
        request = json.loads(self.ledger.objects.get(row["manifest"]))
        if (revised.get("parent"),revised.get("adoption"),revised.get("proposal"),revised.get("decision")) != (
            row["parent_run"],row["id"],row["proposal"],row["decision"]) or (
            request["parent"],request["id"],request["proposal"],request["decision"]) != (
            row["parent_run"],row["id"],row["proposal"],row["decision"]):
            raise Rejected("adoption_mismatch","父子运行与原采用记录不一致。")
        if parent is not None and parent != row["parent_run"]:
            raise Rejected("parent_mismatch","比较两侧必须是保存记录中的直接父子运行。")
        return self.derivations.read(row["parent_run"],parent_selection),revised,request

    def options(self, child):
        """Expose exact selectable revisions and saved comparisons for one direct child.

        @param child Linked execution selected from the workbench.
        @return Both version pickers, the adoption baseline and immutable comparison history.
        """
        # @var parent, revised, request Verified relation; defaults resolve once and are sent explicitly on save.
        parent,revised,request = self._pair(None,child)
        # @var rows Saved comparisons belong only to this child and remain separately selectable.
        rows = self.ledger.rows("SELECT * FROM run_comparisons WHERE child_run=%s ORDER BY created_at,id",(child,))
        return {"parent":{"id":parent["id"],"default_selection":request["base_selection"],
                          "selections":parent["selection_history"]},
                "child":{"id":child,"default_selection":revised["selection"]["id"],
                         "selections":revised["selection_history"]},
                "history":[{**row,"created_at":row["created_at"].isoformat()} for row in rows]}

    def _side(self, run):
        """Capture immutable run references and selected routes with navigable original records.

        @param run Verified execution at one explicitly resolved route revision.
        @return Version binding, exact labels and same-origin original-record destinations.
        """
        # @var rows, query Manifest identity and URL parameters that keep navigation pinned to this version.
        rows = self.ledger.rows("SELECT manifest FROM derivation_results WHERE run=%s",(run["id"],))
        query = urlencode({"run":run["id"],"selection":run["selection"]["id"]})
        return {"run":run["id"],"manifest":rows[0]["manifest"],"selection":run["selection"],
                "mapping":run["mapping"],"freeze":run["freeze"],"review_revision":run["review_revision"],
                "context":run["context"],"checker_profile":run.get("checker_profile"),"status":run["status"],
                "labels":{node["key"]:node["title"] for node in run["graph"]["nodes"]},
                "links":{"run":"/reasoning?"+query,
                         "record":"/api/derivation?"+urlencode({"id":run["id"],"selection":run["selection"]["id"]}),
                         "mapping":"/api/mapping?"+urlencode({"id":run["mapping"]}),
                         "freeze":"/api/frozen?"+urlencode({"id":run["freeze"]})}}

    def create(self, parent, child, parent_selection, child_selection):
        """Save one deterministic comparison without mutating either run, route or receipt.

        @param parent Direct parent run identity.
        @param child Adopted child run identity.
        @param parent_selection Explicit immutable route revision belonging to the parent.
        @param child_selection Explicit immutable route revision belonging to the child.
        @return Content-addressed comparison; identical inputs and implementation return the same identity.
        @raise Rejected If either route is omitted, foreign, unknown or the relation is not direct.
        """
        if not all(isinstance(value,str) and value for value in (parent,child,parent_selection,child_selection)):
            raise Rejected("explicit_versions_required","请明确选择两侧运行与路线版本。")
        # @var original, revised, request Verified immutable inputs; route heads are not comparison inputs.
        original,revised,request = self._pair(parent,child,parent_selection,child_selection)
        # @var before_ir, after_ir Original typed models retain their own semantic and source revision bindings.
        before_ir = self.derivations.mapping.open(original["mapping"])["ir"]
        after_ir = self.derivations.mapping.open(revised["mapping"])["ir"]
        # @var decision Original adoption-time mathematical decision, never the proposal's current head.
        decision = json.loads(self.ledger.objects.get(request["decision"])) if request["decision"] else None
        if decision and (decision["proposal"],decision["choice"],decision["preview"]) != (
                request["proposal"],"confirm",request["preview"]):
            raise Rejected("decision_mismatch","采用时的确认与精确提案内容不一致。")
        # @var result Saved observation; implementation bytes explain which comparison rules produced it.
        result = {"schema_version":1,"parent":self._side(original),"child":self._side(revised),
                  "adoption":request,"decision":decision,"proof_checks_submitted":0,
                  "implementation":{name:self.ledger.objects.put(Path(__file__).with_name(name).read_bytes())
                                    for name in ("service.py","differences.py")},
                  "differences":compare(original,revised,before_ir,after_ir,self.ledger)}
        # @var identity, cursor Content address and append-only registration; retries never duplicate a snapshot.
        identity = self.ledger.objects.put(encoded(result))
        with self.ledger.db,self.ledger.db.cursor() as cursor:
            cursor.execute("INSERT INTO run_comparisons(id,parent_run,child_run,parent_selection,child_selection) "
                           "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                           (identity,parent,child,parent_selection,child_selection))
        return {"id":identity,**result}

    def read(self, identity):
        """Reopen the saved comparison, verifying its exact inputs without recalculating its differences.

        @param identity Immutable comparison identity.
        @return Original observation, independent of later route selections or implementation changes.
        @raise Rejected If a referenced artifact or stored version binding cannot be verified.
        """
        # @var rows, result Original index and content-addressed observation.
        rows = self.ledger.rows("SELECT * FROM run_comparisons WHERE id=%s",(identity,))
        if not rows:
            raise Rejected("unknown_comparison","比较记录不存在。")
        result = json.loads(self.ledger.objects.get(identity))
        # @var row, side, record, run Exact database binding and each historical execution under verification.
        row = rows[0]
        for side in ("parent","child"):
            record = result[side]
            if (record["run"],record["selection"]["id"]) != (row[side+"_run"],row[side+"_selection"]):
                raise Rejected("comparison_mismatch","比较记录的运行或路线绑定不一致。")
            run = self.derivations.read(record["run"],record["selection"]["id"])
            if self._side(run) != record:
                raise Rejected("comparison_mismatch","比较的原始输入发生变化。")
            self.ledger.objects.get(record["manifest"])
        # @var digest Archived implementation bytes remain verifiable even after the current code changes.
        for digest in result["implementation"].values():
            self.ledger.objects.get(digest)
        return {"id":identity,**result}
