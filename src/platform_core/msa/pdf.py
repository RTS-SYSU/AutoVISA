"""Digital-paper import adapter with explicit handling of invalid XML glyph codes."""

from pathlib import Path
import re
from platform_core.paper_ingestion.pdf import Poppler
from platform_core.paper_ingestion.models import Issue, ImportFailure
from platform_core.evidence.storage import sha

#: XML 1.0 excludes these code points even when a PDF font maps glyphs to them.
INVALID_XML = re.compile("[^\u0009\u000a\u000d\u0020-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")


class MsaPoppler(Poppler):
    """Import general papers while preserving legacy extraction profiles.

    @ivar profile Distinct implementation identity and explicit glyph-replacement policy.
    """

    def __init__(self):
        """Fingerprint the generic adapter without changing the legacy case parser."""
        super().__init__()
        self.profile["name"]="msa-poppler-bbox-layout"
        self.profile["implementation"]["msa_pdf.py"]=sha(Path(__file__).read_bytes())
        self.profile["invalid_xml_glyphs"]="replace-with-U+FFFD-and-issue; raw-layout-retained"

    def _layout(self, raw, rotations):
        """Replace XML-inexpressible code points visibly instead of dropping mathematical symbols.

        @param raw Original tool bytes; the parent importer retains these exact bytes as an artifact.
        @param rotations Original page orientation information.
        @return Pages with explicit replacement glyphs and per-page review warnings.
        """
        try:
            # @var decoded, cleaned, count Lossless UTF-8 decoding and explicit replacement statistics.
            decoded = raw.decode("utf-8")
            cleaned,count = INVALID_XML.subn("\ufffd",decoded)
        except UnicodeDecodeError:
            raise ImportFailure("invalid_layout","PDF 提取结果不是有效 UTF-8，请检查原始页图。") from None
        # @var pages, issues Existing geometry/offset logic remains authoritative after normalization.
        pages,issues = super()._layout(cleaned.encode("utf-8"),rotations)
        if count:
            issues.append(Issue("invalid_xml_glyphs",
                f"{count} XML-inexpressible glyph codes were replaced with U+FFFD; inspect page images. Original layout bytes are retained."))
        return pages,issues
