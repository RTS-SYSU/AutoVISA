"""A small public Interface for independent MSA projects and immutable review history."""

import json
from pathlib import Path
from uuid import uuid4

from platform_core.evidence.storage import encoded, sha
from .document import blank, normalize, require, text, revise, mathematics


class MsaWorkspace:
    """Own source-independent projects over the existing immutable ledger.

    @ivar ledger Shared PostgreSQL index and content-addressed objects.
    @ivar root Project checkout containing formal adapters and the local workbench.
    """

    def __init__(self, ledger, root):
        """Bind persistence and the reviewed project configuration.

        @param ledger Existing immutable evidence ledger.
        @param root Project root directory.
        """
        self.ledger,self.root = ledger,Path(root)

    def install(self):
        """Install additive MSA history tables without migrating existing paper projects."""
        self.ledger.install()
        # @var cursor Schema transaction shared with the established append-only trigger.
        with self.ledger.db,self.ledger.db.cursor() as cursor:
            cursor.execute(Path(__file__).with_name("schema.sql").read_text())

    def create(self, name, document, actor):
        """Create from a blank input or an imported MSA, resetting external review claims.

        @param name New project name.
        @param document Versioned JSON input, or None to start from nothing.
        @param actor User initiating this import, not a claim of completed mathematical review.
        @return Saved project with its first immutable revision.
        """
        text(name,"项目名称",200)
        text(actor,"作者",80)
        # @var original, current Untouched input and a separate reviewable draft.
        original = document if document is not None else blank(name)
        current = normalize(original,importing=True)
        # @var project, envelope, revision Stable project identity and initial saved content.
        project = uuid4().hex
        envelope = {"project":project,"parent":None,"document":current,"actor":actor,
                    "reason":"导入原始 MSA；所有条目等待核对。","changes":[]}
        revision = self.ledger.objects.put(encoded(envelope))
        # @var cursor Atomic registration of the original input and initial revision.
        with self.ledger.db,self.ledger.db.cursor() as cursor:
            cursor.execute("INSERT INTO msa_projects(id,name,original) VALUES (%s,%s,%s)",
                           (project,name,self.ledger.objects.put(encoded(original))))
            cursor.execute("INSERT INTO msa_revisions(id,project,parent,generation) VALUES (%s,%s,NULL,1)",
                           (revision,project))
        return self.read(project)

    def catalog(self):
        """List available independent MSA workspaces.

        @return Stable project identities, display names and original input references.
        """
        return [{**row,"created_at":row["created_at"].isoformat()} for row in
                self.ledger.rows("SELECT * FROM msa_projects ORDER BY created_at DESC")]

    def read(self, project, revision=None):
        """Reopen an explicitly selected revision without reinterpreting its mathematical content.

        @param project Project identity.
        @param revision Historical revision, or None for the current head.
        @return Document, provenance, history and the current head identity.
        """
        # @var rows, history Stable project and ordered immutable revision index.
        rows = self.ledger.rows("SELECT * FROM msa_projects WHERE id=%s",(project,))
        require(bool(rows),"unknown_msa","找不到 MSA 项目。")
        history = self.ledger.rows("SELECT id,parent,generation FROM msa_revisions WHERE project=%s ORDER BY generation DESC",(project,))
        # @var identity, record Selected content address and its verified stored envelope.
        identity = revision or history[0]["id"]
        require(any(row["id"]==identity for row in history),"unknown_msa_revision","修订不属于该 MSA 项目。")
        record = json.loads(self.ledger.objects.get(identity))
        require(record["project"]==project and record["parent"]==next(row["parent"] for row in history if row["id"]==identity),
                "revision_mismatch","MSA 修订索引与内容不同。")
        self.ledger.objects.get(rows[0]["original"])
        return {"id":project,"name":rows[0]["name"],"revision":identity,"head":history[0]["id"],
                "document":record["document"],"audit":{key:record[key] for key in ("actor","reason","changes","parent")},
                "history":history,"original":rows[0]["original"],"blockers":self.blockers(record["document"]),
                "papers":self.ledger.rows("SELECT extraction FROM msa_papers WHERE project=%s",(project,)),
                "freezes":self.ledger.rows("SELECT id,revision FROM msa_freezes WHERE project=%s ORDER BY created_at",(project,))}


    def blockers(self, document):
        """Explain missing review and source information without inventing mathematical support.

        @param document Current or historical validated MSA.
        @return Concrete reasons why this semantic revision cannot yet be frozen.
        """
        # @var issues, keys Mutable diagnostics and identities usable as derivation provenance.
        issues = []
        keys = {entry["key"] for entry in document["symbols"]+document["items"]}
        # @var entry, source, kind Individual semantic entity and its explicit origin.
        for entry in document["symbols"]+document["items"]:
            if entry["decision"]=="excluded":
                continue
            if entry["decision"]!="confirmed":
                issues.append({"code":"review_required","item":entry["key"],"message":"条目尚未核对。"})
            if not entry["sources"]:
                issues.append({"code":"source_required","item":entry["key"],"message":"请填写手工来源或有效引用。"})
            for source in entry["sources"]:
                try:
                    require(isinstance(source,dict),"invalid_source","来源必须是对象。")
                    kind = source.get("kind")
                    if kind=="manual":
                        text(source.get("author"),"来源作者",80)
                        text(source.get("note"),"来源说明")
                    elif kind=="pdf":
                        from platform_core.paper_ingestion.models import SourceAnchor
                        from platform_core.paper_ingestion.service import PaperImporter
                        from platform_core.paper_ingestion.pdf import Poppler
                        PaperImporter(self.ledger,Poppler()).resolve(SourceAnchor(**source["anchor"]))
                    elif kind=="derived":
                        require(isinstance(source.get("items"),list) and bool(source["items"]) and
                            all(key in keys and key!=entry["key"] for key in source["items"]),
                            "invalid_source","推导来源必须指向其他已登记条目。")
                        text(source.get("note"),"推导说明")
                    elif kind=="decision":
                        require(bool(self.ledger.rows("SELECT id FROM msa_revisions WHERE id=%s",
                            (source.get("revision"),))),"invalid_source","找不到所引用的核对决定。")
                        text(source.get("note"),"决定说明")
                    else:
                        require(False,"unverified_source","该来源类型尚无已验证记录，请补充手工来源或有效论文引用。")
                except (ValueError,KeyError,TypeError) as error:
                    issues.append({"code":getattr(error,"code","invalid_source"),"item":entry["key"],"message":str(error)})
            if entry.get("material_role")=="author_proof":
                issues.append({"code":"author_proof_excluded","item":entry["key"],"message":"作者证明材料请显式排除，不直接作为模型条件。"})
        # @var goals Selected, nonexcluded goal identities.
        goals = {entry["key"] for entry in document["items"] if entry["category"]=="goal" and entry["decision"]!="excluded"}
        if not document["selected"] or any(key not in goals for key in document["selected"]):
            issues.append({"code":"goals_required","message":"请选择至少一个有效目标。"})
        if document["primary"] not in document["selected"]:
            issues.append({"code":"primary_required","message":"请从所选目标中指定主要目标。"})
        return issues

    def preview(self, project, expected, document):
        """Prepare exact differences and review invalidations before a revision is saved.

        @param project Existing MSA identity.
        @param expected Revision the editor actually observed.
        @param document Complete proposed version.
        @return Stable token, normalized content, differences and freeze blockers.
        """
        # @var current, revised, changes Verified head and proposed semantic state.
        current = self.read(project)
        require(current["head"]==expected,"revision_conflict","MSA 已有新修订，请先重开最新版本。")
        revised,changes = revise(current["document"],document)
        # @var result Canonical review payload; display-only fields cannot become mathematical changes.
        result = {"project":project,"parent":expected,"document":revised,"changes":changes,
                  "mathematics_changed":mathematics(current["document"])!=mathematics(revised),
                  "proof_policy_changed":current["document"]["proof_mode"]!=revised["proof_mode"],
                  "blockers":self.blockers(revised)}
        return {**result,"token":sha(encoded(result))}

    def commit(self, project, expected, document, preview, actor, reason):
        """Append the exact previewed revision with compare-and-swap history protection.

        @param project Project being edited.
        @param expected Last observed revision.
        @param document Proposed input previously sent to preview().
        @param preview Exact preview token.
        @param actor Person saving this revision.
        @param reason Review or edit explanation.
        @return New project state; earlier revisions remain readable.
        """
        text(actor,"核对人",80)
        text(reason,"修订说明")
        # @var prepared, envelope, identity Exact reviewed content and its new revision identity.
        prepared = self.preview(project,expected,document)
        require(preview==prepared["token"],"preview_mismatch","提交内容与预览不同，请重新核对。")
        envelope = {"project":project,"parent":expected,"document":prepared["document"],
                    "changes":prepared["changes"],"actor":actor,"reason":reason}
        identity = self.ledger.objects.put(encoded(envelope))
        # @var cursor, head Serialize concurrent edits of this project only.
        with self.ledger.db,self.ledger.db.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",("msa/"+project,))
            cursor.execute("SELECT id,generation FROM msa_revisions WHERE project=%s ORDER BY generation DESC LIMIT 1",(project,))
            head = cursor.fetchone()
            require(head["id"]==expected,"revision_conflict","MSA 已有新修订。")
            cursor.execute("INSERT INTO msa_revisions(id,project,parent,generation) VALUES (%s,%s,%s,%s)",
                           (identity,project,expected,head["generation"]+1))
        return self.read(project)

    def freeze(self, project, expected, actor, reason):
        """Freeze explicitly reviewed semantics without asserting formalization or proof success.

        @param project Project identity.
        @param expected Exact current revision being frozen.
        @param actor Reviewer making the freeze decision.
        @param reason Explanation of the semantic confirmation.
        @return Immutable context; unsupported mathematics remains available for capability diagnostics.
        """
        text(actor,"核对人",80)
        text(reason,"冻结说明")
        # @var current, previous Exact reviewed input and any previously published freeze of it.
        current = self.read(project)
        require(current["head"]==expected,"revision_conflict","冻结前请核对最新修订。")
        require(not current["blockers"],"review_incomplete","请先完成来源、条目和目标核对。")
        previous = self.ledger.rows("SELECT id FROM msa_freezes WHERE revision=%s",(expected,))
        if previous:
            return self.frozen(previous[0]["id"])
        # @var record, identity Immutable context contains no global theorem assumptions outside the MSA.
        record = {"schema_version":1,"project":project,"revision":expected,"document":current["document"],
                  "mathematics":sha(encoded(mathematics(current["document"]))),"actor":actor,"reason":reason,
                  "semantic_review":"confirmed","formalization":"pending","proof_status":"unproved"}
        identity = self.ledger.objects.put(encoded(record))
        # @var cursor, head Recheck the head inside the same lock used by commit().
        with self.ledger.db,self.ledger.db.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",("msa/"+project,))
            cursor.execute("SELECT id FROM msa_revisions WHERE project=%s ORDER BY generation DESC LIMIT 1",(project,))
            head = cursor.fetchone()
            require(head["id"]==expected,"revision_conflict","冻结时已有更新的修订。")
            cursor.execute("INSERT INTO msa_freezes(id,project,revision) VALUES (%s,%s,%s) ON CONFLICT(revision) DO NOTHING",
                           (identity,project,expected))
            cursor.execute("SELECT id FROM msa_freezes WHERE revision=%s",(expected,))
            identity = cursor.fetchone()["id"]
        return self.frozen(identity)

    def frozen(self, identity):
        """Read a frozen context and verify its original reviewed revision.

        @param identity Freeze content address.
        @return Verified frozen document, with semantic confirmation separate from proof status.
        """
        # @var rows, record, revision Indexed freeze and the exact immutable review it references.
        rows = self.ledger.rows("SELECT * FROM msa_freezes WHERE id=%s",(identity,))
        require(bool(rows),"unknown_msa_freeze","找不到冻结的 MSA。")
        record = json.loads(self.ledger.objects.get(identity))
        require((record["project"],record["revision"])==(rows[0]["project"],rows[0]["revision"]),
                "context_mismatch","冻结索引不同。")
        revision = json.loads(self.ledger.objects.get(record["revision"]))
        require(record["document"]==revision["document"] and record["mathematics"]==sha(encoded(mathematics(record["document"]))),
                "context_mismatch","冻结上下文与原核对修订不同。")
        return {**record,"id":identity}

    def export(self, project, revision=None):
        """Export a portable MSA document without transporting proof or confirmation authority.

        @param project Project to export.
        @param revision Optional exact historical revision.
        @return Versioned JSON input; reimport resets review decisions.
        """
        return self.read(project,revision)["document"]

    def save_result(self, record):
        """Persist an immutable mapping or proof receipt linked to a verified freeze.

        @param record Serializable result whose kind and freeze identify its history.
        @return Receipt including its stable content address.
        """
        self.frozen(record["freeze"])
        # @var identity, cursor Durable content object and its append-only index.
        identity = self.ledger.objects.put(encoded(record))
        with self.ledger.db,self.ledger.db.cursor() as cursor:
            cursor.execute("INSERT INTO msa_results(id,freeze_id,kind) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                           (identity,record["freeze"],record["kind"]))
        return {**record,"id":identity}

    def result(self, identity):
        """Read an original result without re-running today's compiler or checker.

        @param identity Immutable result content address.
        @return Verified original receipt, including source and environment references.
        """
        # @var rows, record Persisted index and content-addressed receipt.
        rows = self.ledger.rows("SELECT * FROM msa_results WHERE id=%s",(identity,))
        require(bool(rows),"unknown_msa_result","找不到映射或证明记录。")
        record = json.loads(self.ledger.objects.get(identity))
        require((record["kind"],record["freeze"])==(rows[0]["kind"],rows[0]["freeze_id"]),
                "result_mismatch","结果索引与内容不同。")
        self.frozen(record["freeze"])
        return {**record,"id":identity}

    def results(self, freeze):
        """List versions attached to one explicitly frozen semantic context.

        @param freeze Stable semantic context identity.
        @return Ordered historical mapping and proof receipt references.
        """
        self.frozen(freeze)
        return self.ledger.rows("SELECT id,kind FROM msa_results WHERE freeze_id=%s ORDER BY created_at",(freeze,))

    def map(self, freeze):
        """Translate reviewed mathematics without copying a case-specific theorem template.

        @param freeze Exact frozen context.
        @return Mapping with typed goals, source bindings and explicit capability gaps.
        """
        from .mapping import prepare
        # @var result Immutable translation linked to implementation bytes.
        result = prepare(self.frozen(freeze))
        result["compiler"] = {name:self.ledger.objects.put((self.root/name).read_bytes()) for name in (
            "src/platform_core/msa/mapping.py","src/platform_core/analysis_ir/language.py")}
        return self.save_result(result)

    def prove(self, mapping, max_checks):
        """Submit a bounded real check while preserving original semantics and prior evidence.

        @param mapping Exact mapped MSA version.
        @param max_checks Explicit candidate-check budget.
        @return New immutable proof receipt, including unsuccessful obligations.
        """
        from .proof import prove
        return prove(self,mapping,max_checks)

    def artifact(self, result, digest):
        """Open evidence bytes only when referenced by the selected original result.

        @param result Result identity selected in the workbench.
        @param digest Content hash of an archived source, log or environment.
        @return Original bytes after the store verifies their content hash.
        """
        # @var record Explicit result containing the requested artifact reference.
        record = self.result(result)
        require(digest in json.dumps(record),"unknown_artifact","该文件不属于所选结果。")
        return self.ledger.objects.get(digest)

    def from_pdf(self, extraction, name, actor):
        """Create an unfilled MSA associated with any successfully imported digital PDF.

        @param extraction Verified PDF layout identity, independent of paper title or contents.
        @param name User-selected workspace title.
        @param actor Import initiator.
        @return MSA with its PDF source available for page review and manual annotation.
        """
        from platform_core.paper_ingestion.service import PaperImporter
        from platform_core.paper_ingestion.pdf import Poppler
        # @var layout, project Existing source layout and a separate new semantic workspace.
        layout = PaperImporter(self.ledger,Poppler()).open(extraction)
        project = self.create(name,None,actor)
        # @var cursor Append attachment without claiming that textual extraction is semantic interpretation.
        with self.ledger.db,self.ledger.db.cursor() as cursor:
            cursor.execute("INSERT INTO msa_papers(project,extraction) VALUES (%s,%s)",(project["id"],extraction))
        return {**self.read(project["id"]),"import_issues":[issue.code for issue in layout.issues]}
