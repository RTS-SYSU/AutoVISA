"""Review source-cited semantic drafts and freeze explicit, unproved derivation inputs."""

from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

from platform_core.evidence.storage import encoded, sha


class ReviewFailure(ValueError):
    """Represent a rejected review operation.

    @ivar code Stable diagnostic understood by the local HTTP adapter.
    """

    def __init__(self, code, message):
        """Retain a diagnostic and human-readable explanation.

        @param code Stable diagnostic identifier.
        @param message Explanation suitable for the review screen.
        """
        super().__init__(message)
        self.code = code


def require(condition, code, message):
    """Reject a violated review invariant.

    @param condition Boolean condition required to proceed.
    @param code Diagnostic emitted on failure.
    @param message Human-readable explanation.
    @raise ReviewFailure If the condition is false.
    """
    if not condition:
        raise ReviewFailure(code, message)


def label(value, name, limit=12000):
    """Validate a bounded, nonempty user-entered string.

    @param value Submitted string.
    @param name Field label used in diagnostics.
    @param limit Maximum permitted Unicode character count.
    @return The original string, preserving intentional whitespace inside the content.
    @raise ReviewFailure If the string is empty, oversized or has an invalid type.
    """
    require(isinstance(value, str) and bool(value.strip()) and len(value) <= limit,
            "invalid_field", name + " 必须为非空文字，且长度不超过 " + str(limit))
    return value


def leaves_match(value, template):
    """Check an editable normalized expression without accepting new structural keys.

    @param value Proposed JSON expression tree.
    @param template Original tree defining its shape.
    @return True if dictionaries preserve keys and every string leaf remains bounded.
    """
    if isinstance(template, dict):
        return (isinstance(value, dict) and value.keys() == template.keys()
                and all(leaves_match(value[key], child) for key, child in template.items()))
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 12000


class ReviewWorkspace:
    """Own revision previews, confirmations and immutable semantic contexts.

    @ivar semantics Semantic extractor used to reopen the original source draft.
    @ivar importer PDF importer for source verification and source geometry.
    @ivar ledger Shared append-only database and verified object store.
    """

    def __init__(self, semantics):
        """Bind review behavior to an existing semantic catalog.

        @param semantics Installed SemanticExtractor over the local evidence ledger.
        """
        self.semantics = semantics
        self.importer = semantics.importer
        self.ledger = semantics.ledger

    def install(self):
        """Install review tables after source and semantic tables exist."""
        with self.ledger.db, self.ledger.db.cursor() as cursor:
            cursor.execute(Path(__file__).with_name("schema.sql").read_text())

    def catalog(self):
        """List saved drafts, projects and frozen contexts for the opening screen.

        @return JSON-compatible catalog with immutable identities and creation times.
        """
        # Timestamp conversion keeps the HTTP adapter independent of PostgreSQL-specific values.
        result = {}
        for table, key in (("semantic_snapshots", "drafts"), ("review_projects", "projects"),
                           ("review_freezes", "freezes")):
            rows = self.ledger.rows("SELECT * FROM " + table + " ORDER BY created_at DESC")
            result[key] = [{name: str(value) if name == "created_at" else value
                            for name, value in row.items()} for row in rows]
        return result

    def create(self, semantic_id, name):
        """Create a pending review workspace without confirming any new semantic candidate.

        @param semantic_id Existing source-cited draft identity.
        @param name Local project display name.
        @return Newly created workspace, its first revision and freeze blockers.
        """
        # state copies the draft; the original source snapshot remains immutable.
        draft = self.semantics.open(semantic_id)
        state = json.loads(encoded(draft.to_dict()))
        for item in state["items"]:
            item["decision"] = "excluded" if item["material_role"] in ("background", "scope_limit") else "pending"
        # Existing D12/D13 choices were already confirmed; edits to them need fresh review.
        for choice in state["project_choices"]["choices"]:
            choice["decision"] = "confirmed"
        goals = [item["key"] for item in state["items"] if item["category"] == "goal"]
        selected = state["project_choices"]["prior_selection"]["paper_goal"]
        state["selected"] = [selected] if selected in goals else []
        state["primary"] = selected if selected in goals else None
        project = uuid4().hex
        envelope = {"project": project, "parent": None, "state": state, "changes": [],
                    "actor": "system", "reason": "创建核对草稿；继承已有合同决定，不确认抽取条目。"}
        identity = self.ledger.objects.put(encoded(envelope))
        with self.ledger.db, self.ledger.db.cursor() as cursor:
            cursor.execute("INSERT INTO review_projects(id,name,semantic_id) VALUES (%s,%s,%s)",
                           (project, label(name, "项目名", 120), semantic_id))
            cursor.execute("INSERT INTO review_revisions(id,project,parent,generation) VALUES (%s,%s,NULL,1)",
                           (identity, project))
        return self.read(project)

    def _record(self, identity):
        """Verify a revision envelope against its database index.

        @param identity Revision content address.
        @return Decoded revision envelope.
        @raise ReviewFailure If the revision is unknown or disagrees with its index.
        """
        rows = self.ledger.rows("SELECT * FROM review_revisions WHERE id=%s", (identity,))
        require(bool(rows), "unknown_revision", "找不到核对修订")
        record = json.loads(self.ledger.objects.get(identity))
        require(record["project"] == rows[0]["project"] and record["parent"] == rows[0]["parent"],
                "revision_mismatch", "修订索引与内容不一致")
        return record

    def read(self, project, revision=None):
        """Open current or historical state while retaining its source and freeze identity.

        @param project Workspace identity.
        @param revision Optional historical revision; omission selects the current head.
        @return Workspace state, history, gates and frozen snapshots.
        @raise ReviewFailure If the project or requested revision is unknown.
        """
        # history is newest first; head remains explicit when the user views an older revision.
        projects = self.ledger.rows("SELECT * FROM review_projects WHERE id=%s", (project,))
        require(bool(projects), "unknown_project", "找不到核对项目")
        history = self.ledger.rows("SELECT id,parent,generation FROM review_revisions WHERE project=%s "
                                   "ORDER BY generation DESC", (project,))
        identity = revision or history[0]["id"]
        require(identity in {row["id"] for row in history}, "unknown_revision", "修订不属于此项目")
        record = self._record(identity)
        draft = self.semantics.open(projects[0]["semantic_id"])
        self._validate(record["state"], draft)
        return {"project": project, "name": projects[0]["name"], "semantic_id": projects[0]["semantic_id"],
                "revision": identity, "head": history[0]["id"], "state": record["state"],
                "audit": {key: record[key] for key in ("actor", "reason", "changes", "parent")},
                "history": history, "blockers": self._blockers(record["state"]),
                "freezes": self.ledger.rows("SELECT id,revision FROM review_freezes WHERE project=%s", (project,))}

    def _validate(self, state, draft):
        """Validate editable state and all citations against the original verified PDF.

        @param state Proposed or restored review state.
        @param draft Original immutable semantic snapshot.
        @raise ReviewFailure If identities, fields, roles, selections or sources are invalid.
        """
        # original maps stable keys to the immutable candidate shapes; layout is opened only once.
        original = {item.key: item for item in draft.items}
        layout = self.importer.open(draft.extraction_id)
        require(state["extraction_id"] == draft.extraction_id and state["source_sha256"] == draft.source_sha256,
                "source_mismatch", "原始文件身份不可修改")
        require(len(state["items"]) == len(original) and {item["key"] for item in state["items"]} == original.keys(),
                "invalid_field", "不能删除或伪造原始候选条目")
        for item in state["items"]:
            base = original[item["key"]]
            require(item["category"] == base.category and item["requires"] == list(base.requires),
                    "invalid_field", "分类和依赖必须保留")
            label(item["summary"], "条目陈述")
            require(leaves_match(item["normalized"], base.normalized), "invalid_field", "规范化字段结构不匹配")
            require(item["decision"] in ("pending", "confirmed", "excluded"), "invalid_field", "未知核对状态")
            require(item["material_role"] in ("model_definition", "analysis_definition", "guarantee_statement",
                    "background", "scope_limit", "author_proof"), "invalid_field", "未知材料角色")
            # Each candidate keeps at least one exact citation, including user-corrected references.
            require(isinstance(item["sources"], list) and 0 < len(item["sources"]) <= 30,
                    "invalid_source", "条目至少需要一处来源")
            for evidence in item["sources"]:
                require(isinstance(evidence, dict) and set(evidence) == {"selector", "kind", "anchors"}
                        and evidence["kind"] in ("prose", "formula_region"), "invalid_source", "来源结构不正确")
                require(isinstance(evidence["anchors"], list) and 0 < len(evidence["anchors"]) <= 100,
                        "invalid_source", "来源片段数量不正确")
                for anchor in evidence["anchors"]:
                    require(isinstance(anchor, dict) and set(anchor) == {"extraction_id", "source_sha256", "page",
                            "start", "end", "quote"}, "invalid_source", "来源字段不正确")
                    require(anchor["extraction_id"] == draft.extraction_id and anchor["source_sha256"] == draft.source_sha256
                            and type(anchor["page"]) is int and 1 <= anchor["page"] <= len(layout.pages),
                            "invalid_source", "来源不属于当前 PDF")
                    page = layout.pages[anchor["page"] - 1]
                    start, end = anchor["start"], anchor["end"]
                    require(type(start) is int and type(end) is int and 0 <= start < end <= len(page.text)
                            and page.text[start:end] == anchor["quote"]
                            and any(word.start < end and word.end > start for word in page.words),
                            "invalid_source", "引用必须与原文位置和文字完全一致")
        choices = state["project_choices"]
        require(choices["contract_sha256"] == draft.project_choices["contract_sha256"],
                "invalid_field", "合同来源摘要不可修改")
        require([choice["id"] for choice in choices["choices"]] ==
                [choice["id"] for choice in draft.project_choices["choices"]], "invalid_field", "范围选择身份不匹配")
        for choice in choices["choices"]:
            label(choice["statement"], "范围选择")
            require(choice["decision"] in ("pending", "confirmed"), "invalid_field", "范围选择不能被隐式排除")
        goals = {item.key for item in draft.items if item.category == "goal"}
        selected = state["selected"]
        require(isinstance(selected, list) and all(isinstance(key, str) for key in selected)
                and len(set(selected)) == len(selected) and set(selected) <= goals,
                "invalid_selection", "所选目标必须来自当前候选清单且不能重复")
        require((state["primary"] in selected) if selected else state["primary"] is None,
                "invalid_selection", "主要目标必须在所选目标中")

    def _blockers(self, state):
        """Compute actionable reasons preventing context freezing.

        @param state Validated review state.
        @return List of item-specific blocking diagnostics.
        """
        # active holds included definitions and selected guarantees; excluded background never enters reasoning.
        items = {item["key"]: item for item in state["items"]}
        active = [item for item in state["items"] if
                  (item["category"] != "goal" and item["decision"] != "excluded") or item["key"] in state["selected"]]
        blockers = []
        if not state["selected"]:
            blockers.append({"key": "selection", "message": "至少选择一个目标并登记主要目标"})
        for item in active:
            if item["decision"] != "confirmed":
                blockers.append({"key": item["key"], "message": "尚未确认来源、解释及待核对问题"})
            expected_role = {"model": "model_definition", "analysis": "analysis_definition", "goal": "guarantee_statement"}
            if item["material_role"] != expected_role[item["category"]]:
                blockers.append({"key": item["key"], "message": "背景、范围说明或作者证明不能直接作为推导输入"})
            for dependency in item["requires"]:
                if dependency not in items or items[dependency]["decision"] != "confirmed":
                    blockers.append({"key": item["key"], "message": "依赖尚未核对或已排除：" + dependency})
        for choice in state["project_choices"]["choices"]:
            if choice["decision"] != "confirmed":
                blockers.append({"key": choice["id"], "message": "修改后的范围选择需要确认"})
        return blockers

    def prepare(self, project, expected, patch):
        """Preview exact field changes and their effects before confirmation.

        @param project Workspace identity.
        @param expected Revision the editor actually read.
        @param patch Whitelisted item, scope-choice or goal-selection edits.
        @return Preview containing a digest, changes, affected goals and resulting blockers.
        @raise ReviewFailure If the editor is stale or submits unsupported fields.
        """
        # Changes are applied to a copy; preparing a preview never creates a revision.
        current = self.read(project)
        require(current["head"] == expected, "revision_conflict", "项目已更新，请重新载入后合并修改")
        require(isinstance(patch, dict) and bool(patch) and set(patch) <= {"items", "choices", "selected", "primary"},
                "invalid_field", "修改字段不受支持")
        state = deepcopy(current["state"])
        items = {item["key"]: item for item in state["items"]}
        choices = {choice["id"]: choice for choice in state["project_choices"]["choices"]}
        content_changed = False
        for collection, targets, allowed in (("items", items, {"summary", "normalized", "material_role", "sources", "decision"}),
                                             ("choices", choices, {"statement", "decision"})):
            edits = patch.get(collection, {})
            require(isinstance(edits, dict) and set(edits) <= targets.keys(), "invalid_field", "修改对象不存在")
            for key, fields in edits.items():
                require(isinstance(fields, dict) and bool(fields) and set(fields) <= allowed, "invalid_field", "不可修改内部身份字段")
                target = targets[key]
                modified = any(target[field] != value for field, value in fields.items() if field != "decision")
                membership_changed = ("decision" in fields and target["decision"] != fields["decision"]
                                      and "excluded" in (target["decision"], fields["decision"]))
                if membership_changed:
                    content_changed = True
                if modified:
                    content_changed = True
                    target["decision"] = "pending"
                    if collection == "items":
                        target["normalization_origin"] = "user_revision"
                target.update(deepcopy(fields))
        for key in ("selected", "primary"):
            if key in patch:
                state[key] = deepcopy(patch[key])
        # Any definition or scope edit conservatively invalidates all goal confirmations.
        # A reviewer may explicitly reconfirm affected goals in the same exact-change preview.
        affected = [item["key"] for item in state["items"] if item["category"] == "goal"] if content_changed else []
        for key in affected:
            if "decision" not in patch.get("items", {}).get(key, {}):
                items[key]["decision"] = "pending"
        self._validate(state, self.semantics.open(current["semantic_id"]))
        changes = []
        for key, item in items.items():
            before = next(old for old in current["state"]["items"] if old["key"] == key)
            for field, value in item.items():
                if before[field] != value:
                    changes.append({"object": key, "field": field, "before": before[field], "after": value})
        for key, choice in choices.items():
            before = next(old for old in current["state"]["project_choices"]["choices"] if old["id"] == key)
            for field, value in choice.items():
                if before[field] != value:
                    changes.append({"object": key, "field": field, "before": before[field], "after": value})
        for key in ("selected", "primary"):
            if state[key] != current["state"][key]:
                changes.append({"object": "selection", "field": key, "before": current["state"][key], "after": state[key]})
        require(bool(changes), "no_change", "没有需要保存的变更")
        token = sha(encoded([project, expected, state, changes]))
        return {"token": token, "state": state, "changes": changes, "affected_goals": affected,
                "blockers": self._blockers(state), "prior_evidence": "旧快照和证据继续绑定原修订；新版本需重新核对适用性。"}

    def commit(self, project, expected, patch, token, actor, reason):
        """Append an explicitly confirmed revision using optimistic concurrency.

        @param project Workspace identity.
        @param expected Revision used to prepare the edit.
        @param patch Exact edits shown in the preview.
        @param token Digest returned by prepare().
        @param actor Local reviewer label; this is attribution, not authenticated identity.
        @param reason Explanation of the correction or confirmation.
        @return Current workspace after the append.
        @raise ReviewFailure If the preview changed or another writer advanced the head.
        """
        preview = self.prepare(project, expected, patch)
        require(token == preview["token"], "preview_mismatch", "确认必须对应当前展示的具体变更")
        envelope = {"project": project, "parent": expected, "state": preview["state"], "changes": preview["changes"],
                    "actor": label(actor, "核对人", 80), "reason": label(reason, "核对或修订说明", 2000)}
        identity = self.ledger.objects.put(encoded(envelope))
        with self.ledger.db, self.ledger.db.cursor() as cursor:
            # The per-project lock serializes the final head check with the revision insert.
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("review:" + project,))
            cursor.execute("SELECT id,generation FROM review_revisions WHERE project=%s ORDER BY generation DESC LIMIT 1", (project,))
            head = cursor.fetchone()
            require(head["id"] == expected, "revision_conflict", "项目已更新，请重新预览")
            cursor.execute("INSERT INTO review_revisions(id,project,parent,generation) VALUES (%s,%s,%s,%s)",
                           (identity, project, expected, head["generation"] + 1))
        return self.read(project)

    def preview_freeze(self, project, expected):
        """Prepare the exact selected context and expose every unresolved review gate.

        @param project Workspace identity.
        @param expected Current revision to freeze.
        @return Freeze token, blockers and the unproved semantic context to be saved.
        """
        current = self.read(project)
        require(current["head"] == expected, "revision_conflict", "只能冻结当前修订")
        return self._freeze_preview(current)

    def _freeze_preview(self, current):
        """Build the same freeze projection for current and historical revisions.

        @param current Verified workspace response including the viewed revision.
        @return Exact context, its digest and unresolved review gates.
        """
        # Historical contexts use their own identities rather than the latest workspace head.
        project, expected = current["project"], current["revision"]
        state = current["state"]
        # Definitions and selected guarantees are filtered explicitly; full author text stays in the source archive.
        definitions = [item for item in state["items"] if item["category"] != "goal" and item["decision"] == "confirmed"
                       and item["material_role"] in ("model_definition", "analysis_definition")]
        goals = [item for key in state["selected"] for item in state["items"] if item["key"] == key]
        baseline = self.semantics.open(current["semantic_id"]).to_dict()
        changed = any(item["normalization_origin"] == "user_revision" for item in definitions + goals)
        changed |= {item["key"] for item in definitions} != {item["key"] for item in baseline["items"]
                    if item["category"] != "goal" and item["material_role"] in ("model_definition", "analysis_definition")}
        changed |= any(choice["statement"] != old["statement"] for choice, old in
                       zip(state["project_choices"]["choices"], baseline["project_choices"]["choices"]))
        context = {"schema_version": 1, "kind": "reviewed_semantic_context", "project": project,
                   "revision": expected, "semantic_id": current["semantic_id"], "source_sha256": state["source_sha256"],
                   "extraction_id": state["extraction_id"], "model": [item for item in definitions if item["category"] == "model"],
                   "analysis": [item for item in definitions if item["category"] == "analysis"], "goals": goals,
                   "primary": state["primary"], "scope": state["project_choices"],
                   "scope_status": "reviewed_variant" if changed else "contract_scope_reference",
                   "formalization_status": "mapping_required", "proof_status": "unproved",
                   "material_policy": "Definitions, analysis and guarantees only; no author proof route."}
        return {"token": sha(encoded(context)), "context": context, "blockers": current["blockers"]}

    def freeze(self, project, expected, token, actor):
        """Save an immutable context only after all required reviews pass.

        @param project Workspace identity.
        @param expected Revision displayed in the freeze preview.
        @param token Digest of the exact context shown to the reviewer.
        @param actor Local reviewer label attached to the confirmation.
        @return Frozen context identity and verified content.
        @raise ReviewFailure If reviews are incomplete, the preview differs or the head changed.
        """
        preview = self.preview_freeze(project, expected)
        require(not preview["blockers"], "review_incomplete", "仍有未处理的核对事项")
        require(token == preview["token"], "preview_mismatch", "冻结确认与预览不一致")
        context = {**preview["context"], "confirmed_by": label(actor, "核对人", 80)}
        identity = self.ledger.objects.put(encoded(context))
        with self.ledger.db, self.ledger.db.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("review:" + project,))
            cursor.execute("SELECT id FROM review_revisions WHERE project=%s ORDER BY generation DESC LIMIT 1", (project,))
            require(cursor.fetchone()["id"] == expected, "revision_conflict", "项目已更新，请重新冻结")
            cursor.execute("SELECT id FROM review_freezes WHERE revision=%s", (expected,))
            prior = cursor.fetchone()
            if prior:
                identity = prior["id"]
            else:
                cursor.execute("INSERT INTO review_freezes(id,project,revision) VALUES (%s,%s,%s)",
                               (identity, project, expected))
        return self.frozen(identity)

    def frozen(self, identity):
        """Reopen and integrity-check a frozen semantic context without following the current head.

        @param identity Frozen context content address.
        @return Identity and its exact historical context.
        @raise ReviewFailure If the frozen index and manifest disagree.
        """
        rows = self.ledger.rows("SELECT * FROM review_freezes WHERE id=%s", (identity,))
        require(bool(rows), "unknown_freeze", "找不到冻结上下文")
        context = json.loads(self.ledger.objects.get(identity))
        require(context["project"] == rows[0]["project"] and context["revision"] == rows[0]["revision"]
                and context["proof_status"] == "unproved" and context["formalization_status"] == "mapping_required",
                "freeze_mismatch", "冻结清单身份或状态不一致")
        historical = self.read(context["project"], context["revision"])
        require(not historical["blockers"], "freeze_mismatch", "冻结修订的核对条件不完整")
        require({key: value for key, value in context.items() if key != "confirmed_by"} ==
                self._freeze_preview(historical)["context"], "freeze_mismatch", "冻结字段与其核对修订不一致")
        return {"id": identity, "context": context}

