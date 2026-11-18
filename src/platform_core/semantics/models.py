"""Reviewable semantic candidates with explicit provenance and interpretation status."""

from dataclasses import asdict, dataclass

from platform_core.paper_ingestion.models import SourceAnchor


class SemanticFailure(ValueError):
    """Carry a stable semantic-extraction diagnostic.

    @ivar code Machine-readable failure identity for callers and saved reports.
    """

    def __init__(self, code, message):
        """Record a diagnostic code and explanation.

        @param code Stable error identifier.
        @param message Human-readable explanation of the failed operation.
        """
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SourceEvidence:
    """Bind one matching rule to exact, potentially disjoint PDF text ranges.

    @ivar selector Named text or formula selector in the extraction profile.
    @ivar kind Either prose or formula_region, retaining the interpretation distinction.
    @ivar anchors Ordered source references containing the original extracted characters.
    """

    selector: str
    kind: str
    anchors: tuple[SourceAnchor, ...]


@dataclass(frozen=True)
class SemanticItem:
    """Describe a paper-derived candidate awaiting mathematical and source review.

    @ivar key Stable rule identity within this semantic snapshot.
    @ivar category One of model, analysis or goal.
    @ivar title Short label for the review list.
    @ivar summary Rule-derived interpretation shown alongside exact quotations.
    @ivar normalized Captured operators or a clearly labeled interpretation template.
    @ivar normalization_origin How the normalized fields were produced.
    @ivar material_role Model definition, analysis definition, guarantee, background or scope limit.
    @ivar sources Source selections supporting every emitted candidate.
    @ivar requires Other item keys needed to interpret the candidate within its scope.
    @ivar status Needs review, or blocked when a required item is missing.
    @ivar review_issues Specific questions and semantic limitations requiring review.
    @ivar proof_status Unproved for candidate goals, otherwise not_applicable.
    """

    key: str
    category: str
    title: str
    summary: str
    normalized: dict
    normalization_origin: str
    material_role: str
    sources: tuple[SourceEvidence, ...]
    requires: tuple[str, ...]
    status: str
    review_issues: tuple[str, ...]
    proof_status: str


@dataclass(frozen=True)
class SemanticSnapshot:
    """Freeze an extraction draft without promoting it to a mathematical context.

    @ivar schema_version Serialization version for semantic snapshots.
    @ivar extraction_id Identity of the frozen PDF layout used for all citations.
    @ivar source_sha256 Original PDF content identity.
    @ivar profile Extraction mode, implementation hashes and rule/config object addresses.
    @ivar items Model, analysis and guarantee candidates actually matched to the input.
    @ivar issues Missing or ambiguous source selectors and dependency gaps.
    @ivar project_choices Previously confirmed scope choices pinned to their separate contract.
    @ivar ready_for_reasoning False while semantic review and material-role confirmation remain pending.
    """

    schema_version: int
    extraction_id: str
    source_sha256: str
    profile: dict
    items: tuple[SemanticItem, ...]
    issues: tuple[dict, ...]
    project_choices: dict
    ready_for_reasoning: bool = False

    def to_dict(self):
        """Serialize the draft with all source references and interpretation labels.

        @return JSON-compatible dictionary for immutable storage and inspection.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, payload):
        """Restore supported semantic records from a verified manifest.

        @param payload Dictionary loaded from a content-addressed object.
        @return Typed semantic snapshot.
        @raise SemanticFailure If the stored schema version is unsupported.
        """
        if payload["schema_version"] != 1:
            raise SemanticFailure("unsupported_semantic_schema", str(payload["schema_version"]))
        # items rebuilds typed references while preserving serialized quote and dependency order.
        items = []
        for item in payload["items"]:
            sources = tuple(SourceEvidence(source["selector"], source["kind"],
                            tuple(SourceAnchor(**anchor) for anchor in source["anchors"]))
                            for source in item["sources"])
            items.append(SemanticItem(**{**item, "sources": sources, "requires": tuple(item["requires"]),
                                        "review_issues": tuple(item["review_issues"])}))
        return cls(**{**payload, "items": tuple(items), "issues": tuple(payload["issues"])})
