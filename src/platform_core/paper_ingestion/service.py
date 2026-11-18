"""Persist PDF imports and resolve their sources through the evidence ledger."""

import json
from pathlib import Path

from platform_core.evidence.storage import encoded, sha
from .models import Extraction, ImportFailure, LocatedText, SourceAnchor


class PaperImporter:
    """Publish extraction snapshots and resolve their original source locations.

    @ivar ledger PostgreSQL ledger and content-addressed store shared with evidence.
    @ivar parser Configured Poppler extractor and renderer.
    """

    def __init__(self, ledger, parser):
        """Bind persistence and PDF processing.

        @param ledger Installed W02 ledger with its own connection.
        @param parser Poppler instance controlling limits and tool identities.
        """
        self.ledger, self.parser = ledger, parser

    def install(self):
        """Create import tables using W02's append-only trigger function.

        @raise psycopg2.Error If the schema or trigger function is unavailable.
        """
        with self.ledger.db, self.ledger.db.cursor() as cursor:
            cursor.execute(Path(__file__).with_name("schema.sql").read_text())

    def import_pdf(self, path):
        """Freeze PDF bytes and publish a complete extraction transactionally.

        @param path Local digital PDF path whose filename is display metadata.
        @return Extraction content address, stable for identical bytes and parser output.
        @raise ImportFailure If the input violates format, size or parser requirements.
        @raise OSError If the source cannot be read or artifacts cannot be written.
        """
        source_path = Path(path)
        # Bound the read even when the file grows after opening.
        with source_path.open("rb") as stream:
            data = stream.read(self.parser.max_bytes + 1)
        pages, issues, raw_outputs = self.parser.extract(data)
        source_sha256 = self.ledger.objects.put(data)
        files = {name: self.ledger.objects.put(output) for name, output in raw_outputs.items()}
        extraction = Extraction(1, source_sha256, len(data), self.parser.profile, pages, issues, files)
        extraction_id = self.ledger.objects.put(encoded(extraction.to_dict()))
        # Objects are durable before their metadata becomes visible. Equal imports converge by ID.
        with self.ledger.db, self.ledger.db.cursor() as cursor:
            cursor.execute("INSERT INTO paper_sources(sha256,byte_count,first_filename) VALUES (%s,%s,%s) "
                           "ON CONFLICT DO NOTHING", (source_sha256, len(data), source_path.name))
            cursor.execute("INSERT INTO paper_extractions(id,source_sha256,profile_sha256,page_count) "
                           "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                           (extraction_id, source_sha256, sha(encoded(self.parser.profile)), len(pages)))
        return extraction_id

    def open(self, extraction_id):
        """Restore a saved extraction and verify its original PDF and diagnostic files.

        @param extraction_id Content address returned by import_pdf().
        @return Extraction with immutable page and word records.
        @raise ImportFailure If metadata is missing or inconsistent.
        @raise Rejected If a referenced object is missing or its digest differs.
        """
        records = self.ledger.rows("SELECT * FROM paper_extractions WHERE id=%s", (extraction_id,))
        if not records:
            raise ImportFailure("unknown_extraction", str(extraction_id))
        record = records[0]
        extraction = Extraction.from_dict(json.loads(self.ledger.objects.get(extraction_id)))
        data = self.ledger.objects.get(extraction.source_sha256)
        if (record["source_sha256"] != extraction.source_sha256 or len(data) != extraction.byte_count
                or record["page_count"] != len(extraction.pages)
                or record["profile_sha256"] != sha(encoded(extraction.profile))):
            raise ImportFailure("metadata_mismatch", extraction_id)
        for digest in set(extraction.files.values()):
            self.ledger.objects.get(digest)
        return extraction

    def _page(self, extraction, number):
        """Resolve a physical page index with strict type and range checking.

        @param extraction Verified extraction containing ordered pages.
        @param number One-based physical page index.
        @return Page record at that index.
        @raise ImportFailure If the index is invalid.
        """
        if type(number) is not int or not 1 <= number <= len(extraction.pages):
            raise ImportFailure("invalid_page", str(number))
        return extraction.pages[number - 1]

    def locate(self, extraction_id, page, start, end):
        """Bind a text selection to its PDF, extraction and visible word rectangles.

        @param extraction_id Immutable layout snapshot containing the selected text.
        @param page One-based physical page number.
        @param start Inclusive Unicode code-point offset into Page.text.
        @param end Exclusive Unicode code-point offset into Page.text.
        @return LocatedText containing the quote and intersecting word boxes.
        @raise ImportFailure If the range is invalid or contains only separators.
        """
        extraction = self.open(extraction_id)
        record = self._page(extraction, page)
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(record.text):
            raise ImportFailure("invalid_source_range", f"{page}/{start}/{end}")
        boxes = tuple(word.box for word in record.words if word.end > start and word.start < end)
        if not boxes:
            raise ImportFailure("empty_source_range", "The selection contains no extracted word")
        anchor = SourceAnchor(extraction_id, extraction.source_sha256, page, start, end, record.text[start:end])
        return LocatedText(anchor, boxes, record.width, record.height)

    def resolve(self, anchor):
        """Check the identities and exact quote of a saved source reference.

        @param anchor SourceAnchor attached to a saved field or supplied by a caller.
        @return Verified source reference and highlighting rectangles.
        @raise ImportFailure If the original PDF identity or quote differs.
        """
        located = self.locate(anchor.extraction_id, anchor.page, anchor.start, anchor.end)
        if located.anchor != anchor:
            raise ImportFailure("source_reference_mismatch", "PDF identity or quote differs from the extraction")
        return located

    def render(self, extraction_id, page, anchor=None):
        """Render an original page or a verified quote crop for manual review.

        @param extraction_id Layout snapshot whose original PDF should be rendered.
        @param page One-based physical page index.
        @param anchor Optional SourceAnchor identifying this same extraction and page.
        @return PNG bytes at 144 DPI.
        @raise ImportFailure If the reference, renderer profile or page size is unsuitable.
        """
        extraction = self.open(extraction_id)
        record = self._page(extraction, page)
        # A renderer must share the recorded coordinate convention and implementation.
        if extraction.profile != self.parser.profile:
            raise ImportFailure("renderer_profile_mismatch", "Use the recorded profile or create a new extraction")
        if record.width * record.height * 4 > 16_000_000:
            raise ImportFailure("preview_too_large", "The page would exceed 16 million pixels")
        boxes = ()
        if anchor is not None:
            if anchor.extraction_id != extraction_id or anchor.page != page:
                raise ImportFailure("source_reference_mismatch", "Preview and reference identify different pages")
            boxes = self.resolve(anchor).boxes
        return self.parser.render(self.ledger.objects.get(extraction.source_sha256), page, boxes)
