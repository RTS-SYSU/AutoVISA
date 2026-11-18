"""Immutable PDF layout records and provenance references for semantic extraction."""

from dataclasses import asdict, dataclass
import math


class ImportFailure(ValueError):
    """Expose a stable import diagnostic to CLI and future workbench callers.

    @ivar code Machine-readable reason such as invalid_pdf or invalid_source_range.
    """

    def __init__(self, code: str, message: str):
        """Attach a readable diagnostic to a stable failure code.

        @param code Import or provenance error identifier.
        @param message Explanation suitable for a development log.
        """
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Box:
    """Locate visible page content in PDF points from the top-left corner.

    @ivar x0 Left edge in points, where one point equals 1/72 inch.
    @ivar y0 Top edge in points after applying page rotation and the crop box.
    @ivar x1 Right edge in the same coordinate system.
    @ivar y1 Bottom edge in the same coordinate system.
    """

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self):
        """Reject reversed rectangles and non-finite coordinates.

        @raise ImportFailure If the rectangle cannot represent a visible area.
        """
        coordinates = (self.x0, self.y0, self.x1, self.y1)
        if not all(math.isfinite(value) for value in coordinates) or self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ImportFailure("invalid_geometry", repr(coordinates))


@dataclass(frozen=True)
class Word:
    """Preserve one extractor word and its place in both text and page layout.

    @ivar id Stable identifier within an extraction, including its one-based page number.
    @ivar text Extracted Unicode text without normalization or symbol substitution.
    @ivar start Inclusive Python Unicode code-point offset in Page.text.
    @ivar end Exclusive Python Unicode code-point offset in Page.text.
    @ivar box Word rectangle on the displayed, cropped and rotated page.
    @ivar flow Zero-based Poppler flow ordinal, retained as a reading-order hint.
    @ivar block Zero-based block ordinal within this flow.
    @ivar line Zero-based line ordinal within this block.
    """

    id: str
    text: str
    start: int
    end: int
    box: Box
    flow: int
    block: int
    line: int


@dataclass(frozen=True)
class Page:
    """Hold text and layout for one displayed PDF page.

    @ivar number One-based physical page index, independent of printed page labels.
    @ivar width Displayed crop-box width in PDF points.
    @ivar height Displayed crop-box height in PDF points.
    @ivar rotation Clockwise PDF page rotation, normalized to 0, 90, 180 or 270 degrees.
    @ivar text Words joined by spaces and lines by newlines in extractor order.
    @ivar words Ordered word records whose offsets refer to this exact text.
    """

    number: int
    width: float
    height: float
    rotation: int
    text: str
    words: tuple[Word, ...]


@dataclass(frozen=True)
class Issue:
    """Keep extraction limitations visible to downstream reviewers.

    @ivar code Stable reason for review, such as page_without_text or parser_warning.
    @ivar message Description of what the extractor observed or still requires.
    @ivar page One-based page number when localized, otherwise None.
    """

    code: str
    message: str
    page: int | None = None


@dataclass(frozen=True)
class Extraction:
    """Snapshot one PDF's raw layout extraction before semantic interpretation.

    @ivar schema_version Serialization contract version.
    @ivar source_sha256 Digest and object-store address of the original PDF bytes.
    @ivar byte_count Original PDF size in bytes.
    @ivar profile Identity, versions and settings of the extraction implementation.
    @ivar pages Ordered physical pages, including pages with no extracted words.
    @ivar issues Parser diagnostics and pending review requirements.
    @ivar files Raw extraction and diagnostic artifacts mapped to their object digests.
    @ivar material_role Classification gate for downstream reasoning, initially unclassified.
    """

    schema_version: int
    source_sha256: str
    byte_count: int
    profile: dict
    pages: tuple[Page, ...]
    issues: tuple[Issue, ...]
    files: dict[str, str]
    material_role: str = "unclassified"

    def to_dict(self) -> dict:
        """Return the JSON-compatible manifest used for storage and content addressing.

        @return Deep dictionary representation of this extraction.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict):
        """Restore a verified extraction manifest without discarding page geometry.

        @param payload Decoded manifest obtained from the content-addressed store.
        @return Extraction containing immutable page, word and issue records.
        @raise ImportFailure If the serialization contract is unsupported.
        """
        if payload["schema_version"] != 1:
            raise ImportFailure("unsupported_schema", str(payload["schema_version"]))
        # Nested dictionaries become records so source resolution uses the same model after reopening.
        pages = []
        for record in payload["pages"]:
            words = tuple(Word(**{**word, "box": Box(**word["box"])}) for word in record["words"])
            pages.append(Page(**{**record, "words": words}))
        return cls(**{**payload, "pages": tuple(pages),
                      "issues": tuple(Issue(**issue) for issue in payload["issues"])})


@dataclass(frozen=True)
class SourceAnchor:
    """Bind a quote to a particular source and extraction snapshot.

    @ivar extraction_id Content address of the exact extraction manifest.
    @ivar source_sha256 Digest of the original PDF, checked independently on resolution.
    @ivar page One-based physical page number.
    @ivar start Inclusive Unicode code-point offset into the extracted page text.
    @ivar end Exclusive Unicode code-point offset into the extracted page text.
    @ivar quote Exact extracted substring, used to detect incorrectly assembled references.
    """

    extraction_id: str
    source_sha256: str
    page: int
    start: int
    end: int
    quote: str


@dataclass(frozen=True)
class LocatedText:
    """Connect a verified source reference to rectangles suitable for highlighting.

    @ivar anchor Reference containing both content identities and the exact quote.
    @ivar boxes Word rectangles intersecting the quote, including partial-word selections.
    @ivar page_width Displayed page width in points.
    @ivar page_height Displayed page height in points.
    """

    anchor: SourceAnchor
    boxes: tuple[Box, ...]
    page_width: float
    page_height: float
