"""Extract and render PDF layout with a bounded, fingerprinted Poppler toolchain."""

import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET

from platform_core.evidence.storage import sha
from .models import Box, ImportFailure, Issue, Page, Word

#: XHTML namespace emitted by pdftotext -bbox-layout.
NS = {"x": "http://www.w3.org/1999/xhtml"}


class Poppler:
    """Own PDF tool execution and the shared extraction/rendering coordinate convention.

    @ivar commands Absolute executable paths for metadata, layout extraction and rendering.
    @ivar profile Fingerprinted tools, source files and coordinate settings for this build.
    @ivar timeout Maximum wall-clock seconds allowed for each tool invocation.
    @ivar max_bytes Maximum supported original PDF byte count.
    @ivar max_pages Maximum supported physical page count.
    """

    def __init__(self, timeout=30, max_bytes=20 * 1024 * 1024, max_pages=100):
        """Locate the PDF tools and capture their actual versions and binary digests.

        @param timeout Positive per-command timeout in seconds.
        @param max_bytes Positive maximum source size in bytes.
        @param max_pages Positive maximum page count.
        @raise ImportFailure If limits are invalid or a required executable is unavailable.
        """
        if any(type(value) is not int or value <= 0 for value in (timeout, max_bytes, max_pages)):
            raise ImportFailure("invalid_limits", "PDF limits must be positive integers")
        self.timeout, self.max_bytes, self.max_pages = timeout, max_bytes, max_pages
        self.commands = {}
        identities = {}
        for name in ("pdfinfo", "pdftotext", "pdftoppm"):
            executable = shutil.which(name)
            if executable is None:
                raise ImportFailure("missing_tool", name)
            self.commands[name] = executable
            output, diagnostic = self._command(name, ["-v"], None)
            identities[name] = {"version": (output + diagnostic).decode(errors="replace").splitlines()[0],
                                "sha256": sha(Path(executable).read_bytes())}
        # Shared-library bytes affect parsing even when the small executable itself has not changed.
        linked = subprocess.run(["ldd", self.commands["pdftotext"]], capture_output=True,
                                timeout=self.timeout, check=True).stdout.decode()
        libraries = {Path(path).name: sha(Path(path).read_bytes())
                     for path in re.findall(r"=>\s+(/[^\s]+)", linked)}
        sources = {name: sha(Path(__file__).with_name(name).read_bytes())
                   for name in ("models.py", "pdf.py", "service.py", "schema.sql")}
        self.profile = {"name": "poppler-bbox-layout", "tools": identities, "libraries": libraries,
                        "implementation": sources, "coordinate_space": "rotated-cropbox-top-left-points",
                        "offset_unit": "unicode-code-point", "order": "poppler-flow-block-line-word",
                        "max_bytes": max_bytes, "max_pages": max_pages}

    def _command(self, name, arguments, directory):
        """Run a tool with a stable locale and preserve its diagnostics.

        @param name Tool basename registered by this extractor.
        @param arguments Individual command arguments, never interpreted by a shell.
        @param directory Private working directory, or None during tool identification.
        @return Pair of stdout and stderr byte strings.
        @raise ImportFailure If the process times out or returns a failing exit code.
        """
        environment = {**os.environ, "LC_ALL": "C", "TZ": "UTC"}
        try:
            result = subprocess.run([self.commands[name], *arguments], cwd=directory, env=environment,
                                    capture_output=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise ImportFailure("parser_timeout", name) from None
        if result.returncode:
            detail = result.stderr.decode("utf-8", errors="replace")[-2000:]
            raise ImportFailure("parser_error", name + ": " + detail)
        return result.stdout, result.stderr

    def extract(self, data):
        """Extract every supported page, retaining word boxes and review diagnostics.

        @param data Original PDF bytes already bounded by the importer.
        @return Tuple of pages, issues and raw tool outputs for immutable storage.
        @raise ImportFailure If the PDF is invalid, encrypted, too large or has no text layer.
        """
        if len(data) > self.max_bytes:
            raise ImportFailure("source_too_large", str(self.max_bytes))
        if b"%PDF-" not in data[:1024]:
            raise ImportFailure("invalid_pdf", "Missing PDF header")
        with TemporaryDirectory(prefix="autorta-pdf-") as temp:
            directory = Path(temp)
            (directory / "source.pdf").write_bytes(data)
            info, info_warning = self._command("pdfinfo", ["-box", "source.pdf"], directory)
            metadata = info.decode("utf-8", errors="replace")
            if re.search(r"^Encrypted:\s+yes", metadata, re.MULTILINE):
                raise ImportFailure("encrypted_pdf", "Password-protected PDFs require a separate import workflow")
            count = re.search(r"^Pages:\s+(\d+)", metadata, re.MULTILINE)
            if count is None:
                raise ImportFailure("invalid_pdf", "Could not determine the physical page count")
            if int(count[1]) > self.max_pages:
                raise ImportFailure("too_many_pages", str(self.max_pages))
            geometry, geometry_warning = self._command(
                "pdfinfo", ["-box", "-f", "1", "-l", count[1], "source.pdf"], directory)
            rotations = {int(number): int(angle) % 360 for number, angle in
                         re.findall(r"^Page\s+(\d+)\s+rot:\s+(-?\d+)", geometry.decode(), re.MULTILINE)}
            if set(rotations) != set(range(1, int(count[1]) + 1)) or any(r % 90 for r in rotations.values()):
                raise ImportFailure("invalid_geometry", "Missing or unsupported page rotations")
            info_warning += geometry_warning
            _, warning = self._command("pdftotext",
                ["-bbox-layout", "-cropbox", "-enc", "UTF-8", "source.pdf", "layout.xhtml"], directory)
            layout = directory / "layout.xhtml"
            if layout.stat().st_size > 32 * 1024 * 1024:
                raise ImportFailure("layout_too_large", "Extracted XML exceeds 32 MiB")
            raw = layout.read_bytes()
            pages, issues = self._layout(raw, rotations)
            if len(pages) != int(count[1]):
                raise ImportFailure("page_count_mismatch", "Metadata and layout disagree")
            if not any(page.words for page in pages):
                raise ImportFailure("no_text_layer", "No extractable words found; OCR is required")
            # Layout extraction preserves glyph text. Mathematical interpretation remains a reviewed operation.
            issues.append(Issue("semantic_review_required",
                                "Review formulas, tables, reading order and material roles against the page image"))
            if info_warning or warning:
                issues.append(Issue("parser_warning", (info_warning + warning).decode("utf-8", errors="replace")))
            artifacts = {"layout.xhtml": raw, "pdfinfo.txt": geometry,
                         "pdfinfo.stderr": info_warning, "pdftotext.stderr": warning}
            return tuple(pages), tuple(issues), artifacts

    def _layout(self, raw, rotations):
        """Decode XHTML words and build stable code-point offsets into each page's text.

        @param raw UTF-8 XHTML bytes produced by the configured extractor.
        @param rotations Normalized page rotations keyed by one-based physical page number.
        @return Mutable page and issue lists for the complete import result.
        @raise ImportFailure If XML or page geometry cannot be interpreted.
        """
        try:
            tree = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise ImportFailure("invalid_layout", str(exc)) from exc
        pages, issues = [], []
        for number, node in enumerate(tree.findall(".//x:page", NS), 1):
            width, height = float(node.attrib["width"]), float(node.attrib["height"])
            if not all(math.isfinite(v) and 0 < v <= 14400 for v in (width, height)):
                raise ImportFailure("invalid_geometry", "Unsupported page dimensions")
            rotation = rotations[number]
            # Poppler rotates word coordinates but reports unrotated XHTML page dimensions.
            if rotation in (90, 270):
                width, height = height, width
            words, parts, position = [], [], 0
            for flow_id, flow in enumerate(node.findall("x:flow", NS)):
                for block_id, block in enumerate(flow.findall("x:block", NS)):
                    for line_id, line in enumerate(block.findall("x:line", NS)):
                        for item in line.findall("x:word", NS):
                            text = "".join(item.itertext())
                            if not text:
                                continue
                            raw_box = tuple(float(item.attrib[key]) for key in ("xMin", "yMin", "xMax", "yMax"))
                            if not all(math.isfinite(v) for v in raw_box):
                                raise ImportFailure("invalid_geometry", "Non-finite word coordinates")
                            # Clip partly visible words to the displayed crop box while keeping their text.
                            clipped = (max(0.0, raw_box[0]), max(0.0, raw_box[1]),
                                       min(width, raw_box[2]), min(height, raw_box[3]))
                            if clipped != raw_box:
                                issues.append(Issue("clipped_word", "Word intersects the page boundary", number))
                            if clipped[0] >= clipped[2] or clipped[1] >= clipped[3]:
                                continue
                            if parts and parts[-1] != "\n":
                                parts.append(" ")
                                position += 1
                            words.append(Word(f"p{number}-w{len(words) + 1}", text, position,
                                              position + len(text), Box(*clipped), flow_id, block_id, line_id))
                            parts.append(text)
                            position += len(text)
                        if parts and parts[-1] != "\n":
                            parts.append("\n")
                            position += 1
            if not words:
                issues.append(Issue("page_without_text", "This page requires image review or OCR", number))
            if any("\ufffd" in word.text or any(ord(c) < 32 for c in word.text) for word in words):
                issues.append(Issue("suspect_glyphs", "Replacement or control characters occur in extracted text", number))
            pages.append(Page(number, width, height, rotation, "".join(parts), tuple(words)))
        return pages, issues

    def render(self, data, page, boxes=()):
        """Render a page or the union of selected word rectangles at two pixels per point.

        @param data Verified original PDF bytes.
        @param page One-based physical page number to render.
        @param boxes Word rectangles to crop around, or empty for the whole page.
        @return PNG bytes at 144 DPI in the same crop-box coordinates as extraction.
        @raise ImportFailure If rendering fails or the crop exceeds the supported raster size.
        """
        # Two pixels per point permits exact scaling of known PDF coordinates before integer rounding.
        arguments = ["-f", str(page), "-l", str(page), "-singlefile", "-cropbox", "-r", "144", "-png"]
        if boxes:
            left = max(0, math.floor(min(box.x0 for box in boxes) * 2) - 8)
            top = max(0, math.floor(min(box.y0 for box in boxes) * 2) - 8)
            right = math.ceil(max(box.x1 for box in boxes) * 2) + 8
            bottom = math.ceil(max(box.y1 for box in boxes) * 2) + 8
            arguments += ["-x", str(left), "-y", str(top), "-W", str(right - left), "-H", str(bottom - top)]
        with TemporaryDirectory(prefix="autorta-preview-") as temp:
            directory = Path(temp)
            (directory / "source.pdf").write_bytes(data)
            self._command("pdftoppm", [*arguments, "source.pdf", "page"], directory)
            return (directory / "page.png").read_bytes()
