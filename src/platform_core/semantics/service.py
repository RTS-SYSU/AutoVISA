"""Persist semantic drafts and verify their original-source references."""

import json
from pathlib import Path

from platform_core.evidence.storage import encoded, sha
from .case11 import Case11Extractor
from .models import SemanticFailure, SemanticSnapshot


class SemanticExtractor:
    """Extract and reopen semantic drafts over the imported-paper catalog.

    @ivar importer Source importer supplying verified PDF snapshots.
    @ivar ledger Shared PostgreSQL connection and content-addressed object store.
    @ivar engine Case-specific rules matched against actual input layout.
    @ivar profile Frozen identities of the implementation and configuration.
    """

    def __init__(self, importer, root):
        """Freeze local extraction rules and previously confirmed project choices.

        @param importer Configured PaperImporter backed by the persistent catalog.
        @param root Checkout containing rule files and the mathematical contract.
        """
        self.importer, self.ledger = importer, importer.ledger
        root = Path(root)
        # Rule and choice bytes are frozen before interpretation; root resolves their relative paths.
        rule_bytes = (root / "configs/case11-semantic-rules.json").read_bytes()
        choice_bytes = (root / "configs/case11-project-choices.json").read_bytes()
        rules, choices = json.loads(rule_bytes), json.loads(choice_bytes)
        contract = (root / choices["contract"]).read_bytes()
        # Interpretation rules and project decisions are archived separately from the original PDF.
        files = {"rules": self.ledger.objects.put(rule_bytes), "project_choices": self.ledger.objects.put(choice_bytes),
                 "decision_contract": self.ledger.objects.put(contract)}
        for name in ("models.py", "case11.py", "service.py", "schema.sql"):
            files[name] = self.ledger.objects.put(Path(__file__).with_name(name).read_bytes())
        self.profile = {"name": rules["name"], "mode": rules["method"], "scope": rules["scope"], "files": files}
        self.engine = Case11Extractor(rules, choices, self.profile)

    def install(self):
        """Create the semantic snapshot index with append-only protection.

        @raise psycopg2.Error If the imported-paper schema is unavailable.
        """
        with self.ledger.db, self.ledger.db.cursor() as cursor:
            cursor.execute(Path(__file__).with_name("schema.sql").read_text())

    def extract(self, extraction_id):
        """Match the imported paper and persist a draft with source references.

        @param extraction_id Existing immutable PDF layout identity.
        @return Semantic snapshot content address, including partial extraction results.
        @raise SemanticFailure If the paper is unsupported or provenance validation fails.
        """
        # New drafts must use the pinned contract; old drafts can still reopen their archived choices.
        if self.profile["files"]["decision_contract"] != self.engine.choices["contract_sha256"]:
            raise SemanticFailure("decision_contract_changed", self.engine.choices["contract"])
        # Identity covers the verified source, matching rules, decisions and every emitted citation.
        extraction = self.importer.open(extraction_id)
        snapshot = self.engine.build(extraction_id, extraction)
        self._validate(snapshot, extraction)
        identity = self.ledger.objects.put(encoded(snapshot.to_dict()))
        with self.ledger.db, self.ledger.db.cursor() as cursor:
            cursor.execute("INSERT INTO semantic_snapshots(id,extraction_id,source_sha256,profile_sha256) "
                           "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                           (identity, extraction_id, extraction.source_sha256, sha(encoded(self.profile))))
        return identity

    def _validate(self, snapshot, extraction):
        """Verify citations and preserve the pending-review gate.

        @param snapshot Candidate or restored semantic manifest.
        @param extraction Verified underlying layout and its original-source identity.
        @raise SemanticFailure If an identity, quote, range or review state is inconsistent.
        """
        if (snapshot.schema_version != 1 or snapshot.source_sha256 != extraction.source_sha256
                or snapshot.ready_for_reasoning is not False
                or len({item.key for item in snapshot.items}) != len(snapshot.items)):
            raise SemanticFailure("invalid_semantic_draft", "Source identity or review gate differs")
        for item in snapshot.items:
            if (not item.sources or item.status not in ("needs_review", "blocked")
                    or item.category not in ("model", "analysis", "goal")
                    or item.proof_status != ("unproved" if item.category == "goal" else "not_applicable")):
                raise SemanticFailure("invalid_semantic_draft", item.key)
            for evidence in item.sources:
                if not evidence.anchors:
                    raise SemanticFailure("source_reference_mismatch", evidence.selector)
                for anchor in evidence.anchors:
                    if (anchor.extraction_id != snapshot.extraction_id or
                            anchor.source_sha256 != snapshot.source_sha256 or
                            type(anchor.page) is not int or not 1 <= anchor.page <= len(extraction.pages)):
                        raise SemanticFailure("source_reference_mismatch", item.key)
                    # Page text is immutable; no normalized formula may substitute for its exact quote.
                    page = extraction.pages[anchor.page - 1]
                    if (type(anchor.start) is not int or type(anchor.end) is not int or
                            not 0 <= anchor.start < anchor.end <= len(page.text) or
                            page.text[anchor.start:anchor.end] != anchor.quote or
                            not any(word.start < anchor.end and word.end > anchor.start for word in page.words)):
                        raise SemanticFailure("source_reference_mismatch", evidence.selector)

    def open(self, identity):
        """Restore a draft and revalidate its configuration, PDF and source ranges.

        @param identity Semantic snapshot identity returned by extract().
        @return Typed snapshot retaining the original extraction profile.
        @raise SemanticFailure If its index, manifest or citations disagree.
        @raise Rejected If a required input object is missing or damaged.
        """
        # The database row binds the content address to its PDF extraction and profile identities.
        rows = self.ledger.rows("SELECT * FROM semantic_snapshots WHERE id=%s", (identity,))
        if not rows:
            raise SemanticFailure("unknown_semantic_snapshot", str(identity))
        snapshot = SemanticSnapshot.from_dict(json.loads(self.ledger.objects.get(identity)))
        row = rows[0]
        if (row["extraction_id"] != snapshot.extraction_id or row["source_sha256"] != snapshot.source_sha256
                or row["profile_sha256"] != sha(encoded(snapshot.profile))):
            raise SemanticFailure("semantic_metadata_mismatch", identity)
        for digest in snapshot.profile["files"].values():
            self.ledger.objects.get(digest)
        self._validate(snapshot, self.importer.open(snapshot.extraction_id))
        return snapshot


def review_markdown(snapshot):
    """Render an inspectable review list with quotations and interpretation labels.

    @param snapshot Verified semantic snapshot to present to developers.
    @return Markdown containing categories, sources, normalization and pending questions.
    """
    # Build fences from their character code to keep embedded JSON unambiguous.
    fence = chr(96) * 3
    # lines preserves category order and prints each disjoint original quote independently.
    lines = ["# case_11 语义抽取草稿", "", "抽取方式：" + snapshot.profile["mode"],
             "", "所有条目等待来源与数学语义核对。", ""]
    for category, title in (("model", "模型条件与范围"), ("analysis", "分析方法"), ("goal", "候选目标")):
        lines.extend(["## " + title, ""])
        for item in (item for item in snapshot.items if item.category == category):
            lines.extend(["### " + item.title, "", f"- 标识 {item.key}，状态 {item.status}。",
                          "- " + item.summary, "- 材料角色 " + item.material_role + "。"])
            if item.normalized:
                lines.extend(["- 规范化来源 " + item.normalization_origin + "。", "",
                              fence + "json", json.dumps(item.normalized, ensure_ascii=False, indent=2), fence])
            for source in item.sources:
                lines.extend(["", "- 来源选择 " + source.selector + "。"])
                for anchor in source.anchors:
                    lines.extend([f"  - PDF 第 {anchor.page} 页，文本范围 [{anchor.start}, {anchor.end})。", "",
                                  "> " + anchor.quote.replace("\n", "\n> "), ""])
            lines.extend("- 待核对：" + issue for issue in item.review_issues)
            lines.append("")
    lines.extend(["## 既有项目范围选择", "", "这些选择引用独立的项目合同。", ""])
    for choice in snapshot.project_choices["choices"]:
        lines.append("- " + choice["statement"] + "（" + "、".join(choice["decisions"]) + "）")
    if snapshot.issues:
        lines.extend(["", "## 缺口", "", fence + "json", json.dumps(snapshot.issues, ensure_ascii=False, indent=2), fence])
    return "\n".join(lines) + "\n"
