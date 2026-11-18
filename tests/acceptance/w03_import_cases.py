"""Exercise source fidelity, layout geometry and persistence through the PDF import interface."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import struct

from platform_core.evidence.storage import Ledger
from platform_core.evidence.terms import Rejected
from platform_core.paper_ingestion.models import ImportFailure
from platform_core.paper_ingestion.service import PaperImporter
from platform_core.paper_ingestion.pdf import Poppler


def fixture_pdf(rotation=0, cropped=False, text=True, second_page=False):
    """Construct a small deterministic PDF for geometry and empty-page cases.

    @param rotation Page rotation in degrees.
    @param cropped Whether to inset the visible page box from its media box.
    @param text Whether to draw selectable words or just a rectangle.
    @param second_page Whether to append a second page without text.
    @return Valid PDF bytes with explicit cross-reference offsets.
    """
    content = (b"BT /F1 12 Tf 100 200 Td (LEFT caf\\351) Tj 140 0 Td (RIGHT) Tj ET\n"
               b"BT /F1 12 Tf 100 160 Td (C_i <= D_i <= T_i) Tj ET\n"
               if text else b"0.5 g 90 90 60 30 re f\n")
    crop = b"/CropBox [50 40 350 260]" if cropped else b""
    kids = b"[3 0 R 6 0 R]" if second_page else b"[3 0 R]"
    # Object IDs are fixed so tests can vary geometry without relying on a second PDF library.
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids " + kids + b" /Count " + str(2 if second_page else 1).encode() + b" >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 300] " + crop +
        b" /Rotate " + str(rotation).encode() +
        b" /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
    ]
    if second_page:
        objects += [b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 300] /Resources << >> >>"]
    data, offsets = bytearray(b"%PDF-1.4\n"), [0]
    for index, item in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(str(index).encode() + b" 0 obj\n" + item + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(data)


def exercise(importer, source, directory, dsn, report):
    """Check real paper imports and deliberate failures with the installed PDF tools.

    @param importer PaperImporter backed by a disposable database and object directory.
    @param source Path to the reviewed case_11 PDF.
    @param directory Output directory for the report, fixture files and review images.
    @param dsn Connection string for independent concurrent writers.
    @param report Mutable output retaining completed checks even when a later case fails.
    @return Report containing checks and a source anchor to verify after database restore.
    @raise AssertionError If any observation violates the import contract.
    """
    report["checks"] = {}
    def expect(name, actual, expected):
        """Record one checked observation.

        @param name Stable acceptance check name.
        @param actual Observed value.
        @param expected Value required by the contract.
        @raise AssertionError If the values differ.
        """
        if actual != expected:
            raise AssertionError(f"{name}: {actual!r} != {expected!r}")
        report["checks"][name] = "passed"

    def reject(name, code, operation):
        """Require an operation to fail with a specific diagnostic.

        @param name Acceptance check name.
        @param code Expected stable error code.
        @param operation Zero-argument operation to invoke.
        @raise AssertionError If the operation succeeds or uses another diagnostic.
        """
        try:
            operation()
        except (ImportFailure, Rejected) as error:
            expect(name, error.code, code)
        else:
            raise AssertionError(name + " unexpectedly succeeded")

    extraction_id = importer.import_pdf(source)
    extraction = importer.open(extraction_id)
    expect("source_digest", extraction.source_sha256,
           "d5d16b999822e16220102521cf23c56e6b88b2e4b9b40b0e26ec344a676a2f41")
    expect("six_physical_pages", len(extraction.pages), 6)
    expect("every_page_has_words", all(page.words for page in extraction.pages), True)
    expect("raw_material_requires_classification", extraction.material_role, "unclassified")
    expect("mathematical_review_explicit", any(i.code == "semantic_review_required" for i in extraction.issues), True)
    expect("all_offsets_match_text", all(page.text[word.start:word.end] == word.text
           for page in extraction.pages for word in page.words), True)
    expect("all_boxes_within_pages", all(0 <= w.box.x0 < w.box.x1 <= page.width and
           0 <= w.box.y0 < w.box.y1 <= page.height for page in extraction.pages for w in page.words), True)
    expect("same_pdf_same_extraction", importer.import_pdf(source), extraction_id)
    alias = directory / "renamed.pdf"
    alias.write_bytes(source.read_bytes())
    expect("filename_is_not_identity", importer.import_pdf(alias), extraction_id)

    def concurrent_import(ordinal):
        """Repeat one import on an independent ledger connection.

        @param ordinal Worker identifier retained for executor argument order.
        @return Immutable extraction ID produced by this worker.
        """
        ledger = Ledger(dsn, importer.ledger.objects.root)
        try:
            return PaperImporter(ledger, importer.parser).import_pdf(source)
        finally:
            ledger.close()

    with ThreadPoolExecutor(2) as executor:
        expect("concurrent_imports_converge", list(executor.map(concurrent_import, (0, 1))), [extraction_id] * 2)
    expect("single_extraction_row", importer.ledger.rows("SELECT count(*) AS count FROM paper_extractions")[0]["count"], 1)
    # The Fig. 3 caption lies on physical page four in this fixed source.
    page = extraction.pages[3]
    phrase = "Schedulability Algorithm"
    start = page.text.index(phrase)
    located = importer.locate(extraction_id, 4, start, start + len(phrase))
    expect("caption_quote", located.anchor.quote, phrase)
    expect("saved_reference_resolves", importer.resolve(located.anchor), located)
    reject("changed_quote", "source_reference_mismatch",
           lambda: importer.resolve(replace(located.anchor, quote="a different theorem")))
    reject("changed_source", "source_reference_mismatch",
           lambda: importer.resolve(replace(located.anchor, source_sha256="0" * 64)))
    reject("invalid_page", "invalid_page", lambda: importer.locate(extraction_id, 0, 0, 1))
    reject("invalid_range", "invalid_source_range", lambda: importer.locate(extraction_id, 4, -1, 2))
    reject("cross_page_preview", "source_reference_mismatch",
           lambda: importer.render(extraction_id, 3, located.anchor))
    (directory / "case11-page4.png").write_bytes(importer.render(extraction_id, 4))
    (directory / "case11-caption.png").write_bytes(importer.render(extraction_id, 4, located.anchor))
    report["anchor"] = located.anchor.__dict__
    report["extraction_id"] = extraction_id
    report["source_sha256"] = extraction.source_sha256
    report["pages"] = len(extraction.pages)
    report["words"] = sum(len(page.words) for page in extraction.pages)

    # Every geometry case crosses the normal importer and renderer entry points.
    for rotation in (0, 90, 180, 270):
        fixture = directory / f"geometry-{rotation}.pdf"
        fixture.write_bytes(fixture_pdf(rotation, cropped=True))
        identity = importer.import_pdf(fixture)
        page = importer.open(identity).pages[0]
        expected = (220.0, 300.0) if rotation % 180 else (300.0, 220.0)
        expect(f"crop_rotation_{rotation}_dimensions", (page.width, page.height), expected)
        left = next(word for word in page.words if word.text == "LEFT")
        anchor = importer.locate(identity, 1, left.start, left.end).anchor
        image = importer.render(identity, 1)
        expect(f"crop_rotation_{rotation}_pixels", struct.unpack(">II", image[16:24]),
               tuple(int(size * 2) for size in expected))
        (directory / f"geometry-{rotation}.png").write_bytes(image)
        (directory / f"geometry-{rotation}-crop.png").write_bytes(importer.render(identity, 1, anchor))
        if rotation == 0:
            expect("crop_origin_translation", round(left.box.x0), 50)
            expect("unicode_offsets", "café" in page.text, True)
        if rotation == 90:
            expect("rotated_origin_translation", round(left.box.y0), 50)

    mixed = directory / "mixed.pdf"
    mixed.write_bytes(fixture_pdf(second_page=True))
    mixed_id = importer.import_pdf(mixed)
    expect("blank_page_retained", len(importer.open(mixed_id).pages), 2)
    expect("blank_page_issue", any(i.code == "page_without_text" and i.page == 2
                                for i in importer.open(mixed_id).issues), True)
    scanned = directory / "scan.pdf"
    scanned.write_bytes(fixture_pdf(text=False))
    limited = PaperImporter(importer.ledger, Poppler(max_pages=1))
    reject("page_limit", "too_many_pages", lambda: limited.import_pdf(mixed))
    small = PaperImporter(importer.ledger, Poppler(max_bytes=16))
    reject("byte_limit", "source_too_large", lambda: small.import_pdf(source))
    count_before = importer.ledger.rows("SELECT count(*) AS count FROM paper_extractions")[0]["count"]
    reject("scan_requires_ocr", "no_text_layer", lambda: importer.import_pdf(scanned))
    invalid = directory / "bad.pdf"
    invalid.write_bytes(b"This is not a PDF.")
    reject("invalid_pdf", "invalid_pdf", lambda: importer.import_pdf(invalid))
    invalid.write_bytes(b"%PDF-1.4\ntruncated object data")
    reject("truncated_pdf", "parser_error", lambda: importer.import_pdf(invalid))
    expect("failed_import_is_not_published",
           importer.ledger.rows("SELECT count(*) AS count FROM paper_extractions")[0]["count"], count_before)
    # Damage only this disposable object and restore it before publishing the test archive.
    object_path = importer.ledger.objects.root / extraction.source_sha256
    original = object_path.read_bytes()
    try:
        object_path.write_bytes(b"tampered")
        reject("corrupt_source_rejected", "artifact_mismatch", lambda: importer.open(extraction_id))
        object_path.unlink()
        reject("missing_source_rejected", "missing_artifact", lambda: importer.open(extraction_id))
    finally:
        object_path.write_bytes(original)
    return report
