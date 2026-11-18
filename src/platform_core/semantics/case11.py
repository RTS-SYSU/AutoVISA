"""Case-specific, source-driven rules for a reproducible semantic extraction draft."""

from dataclasses import replace
import re

from platform_core.paper_ingestion.models import SourceAnchor
from .models import SemanticFailure, SemanticItem, SemanticSnapshot, SourceEvidence


class Case11Extractor:
    """Match reviewed rules against actual layout words and retain exact source anchors.

    @ivar rules Decoded case-specific selector and interpretation configuration.
    @ivar choices Separately confirmed project choices with their contract identity.
    @ivar profile Frozen implementation and configuration identities for the result.
    """

    def __init__(self, rules, choices, profile):
        """Bind the configurations used for a single semantic extraction version.

        @param rules Matching rules, source selectors and labeled interpretation templates.
        @param choices Existing project decisions, kept separate from PDF-derived candidates.
        @param profile Content identities of code, rules and decision records.
        """
        self.rules, self.choices, self.profile = rules, choices, profile

    def _view(self, page, selector):
        """Build a search string while mapping every character back to a source word.

        @param page Frozen physical page and its raw words.
        @param selector Column filter or normalized rectangular source region.
        @return Pair of searchable text and original word indices per character.
        @raise SemanticFailure If a word disagrees with its recorded source offsets.
        """
        # characters holds normalized search text; indices maps each character to its raw word.
        characters, indices = [], []
        # previous is the last included word, used only to normalize a line-end hyphen.
        previous = None
        for index, word in enumerate(page.words):
            if page.text[word.start:word.end] != word.text:
                raise SemanticFailure("inconsistent_layout", word.id)
            # Coordinates are normalized to page dimensions for the reviewed six-page layout.
            x = (word.box.x0 + word.box.x1) / (2 * page.width)
            y = (word.box.y0 + word.box.y1) / (2 * page.height)
            column = selector.get("column")
            if (column == "left" and x >= 0.49) or (column == "right" and x < 0.49):
                continue
            if "box" in selector:
                left, top, right, bottom = selector["box"]
                if not (left <= x <= right and top <= y <= bottom):
                    continue
            if previous is not None:
                # Only a lowercase word split across a line is dehyphenated for matching.
                # Original quotes and their offsets always retain the PDF-extracted characters.
                line_break = "\n" in page.text[previous.end:word.start]
                if (previous.text.endswith("-") and len(previous.text) > 1
                        and previous.text[-2].islower() and word.text[0].islower() and line_break):
                    characters.pop()
                    indices.pop()
                else:
                    characters.append(" ")
                    indices.append(-1)
            characters.extend(word.text)
            indices.extend([index] * len(word.text))
            previous = word
        return "".join(characters), indices

    def _anchors(self, extraction_id, extraction, page, indices):
        """Create exact ranges without including intervening words from another column.

        @param extraction_id Frozen layout manifest identity.
        @param extraction Source document and page metadata.
        @param page Physical page containing the matched words.
        @param indices Original word indices touched by the selected match.
        @return Ordered source references covering the selected source words.
        """
        # selected contains original word positions; runs separates physically interleaved columns.
        selected = sorted(set(index for index in indices if index >= 0))
        runs = []
        for index in selected:
            if runs and index == runs[-1][-1] + 1:
                runs[-1].append(index)
            else:
                runs.append([index])
        # anchors stores verbatim ranges; start/end are Unicode codepoint offsets in one physical page.
        anchors = []
        for run in runs:
            start, end = page.words[run[0]].start, page.words[run[-1]].end
            anchors.append(SourceAnchor(extraction_id, extraction.source_sha256, page.number,
                                        start, end, page.text[start:end]))
        return tuple(anchors)

    def _match(self, extraction_id, extraction, selector):
        """Find one unambiguous source passage or a formula region satisfying all guards.

        @param extraction_id Frozen layout identity for generated citations.
        @param extraction Verified imported PDF snapshot.
        @param selector Named page, column and pattern or formula-region guard set.
        @return Pair of source evidence and captured operators for normalization.
        @raise SemanticFailure If a selector is absent, ambiguous or loses required formula markers.
        """
        # text and indices are a searchable view; captures contains only observed named regex groups.
        page = extraction.pages[selector["page"] - 1]
        text, indices = self._view(page, selector)
        captures = {}
        if "pattern" in selector:
            # A unique match is required; selected retains the original word indices behind that match.
            matches = list(re.finditer(selector["pattern"], text, re.IGNORECASE))
            if len(matches) != 1:
                code = "source_missing" if not matches else "source_ambiguous"
                raise SemanticFailure(code, selector["id"])
            match = matches[0]
            selected = indices[match.start():match.end()]
            captures = match.groupdict()
            kind = "prose"
        else:
            # Region guards check recognizable formula tokens without claiming complete mathematical parsing.
            missing = [guard for guard in selector["guards"] if re.search(guard, text) is None]
            if missing:
                raise SemanticFailure("formula_markers_missing", selector["id"] + ": " + repr(missing))
            selected, kind = indices, "formula_region"
        anchors = self._anchors(extraction_id, extraction, page, selected)
        if not anchors:
            raise SemanticFailure("source_missing", selector["id"])
        return SourceEvidence(selector["id"], kind, anchors), captures

    def build(self, extraction_id, extraction):
        """Extract a review draft from actual input matches, preserving missing-rule diagnostics.

        @param extraction_id Immutable layout manifest identity.
        @param extraction Verified six-page case_11 layout supplied by the import module.
        @return SemanticSnapshot with supported candidates and separate project choices.
        @raise SemanticFailure If the input does not match the supported paper/layout family.
        """
        # Supported layout checks restrict this profile to the reviewed case_11 paper family.
        title = extraction.pages[0].text if extraction.pages else ""
        if (len(extraction.pages) != 6 or
                "HARD REAL-TIME SCHEDULING: THE DEADLINE-MONOTONIC APPROACH" not in title or
                any((page.width, page.height, page.rotation) != (612.0, 792.0, 0) for page in extraction.pages)):
            raise SemanticFailure("unsupported_paper", self.rules["scope"])
        # items contains supported candidates; issues records omissions rather than fabricated replacements.
        items, issues = [], []
        for rule in self.rules["rules"]:
            # Each rule is emitted only after all of its required source selectors match.
            sources, captures, failed = [], {}, False
            for selector in rule["sources"]:
                try:
                    evidence, values = self._match(extraction_id, extraction, selector)
                    sources.append(evidence)
                    captures.update(values)
                except SemanticFailure as error:
                    issues.append({"item": rule["id"], "selector": selector["id"],
                                   "code": error.code, "message": str(error)})
                    failed = True
            if failed:
                continue
            # Literal formula templates are explicitly distinguished from operators read from the input.
            normalized = rule.get("normalized", {}).copy()
            if rule.get("normalization_origin") == "captured_operators":
                normalized["expression"] = normalized["expression"].format(**captures)
                normalized["captures"] = captures
            # Changed comparison operators remain visible but block dependent claims until reviewed.
            mismatches = [name for name, allowed in rule.get("expected_captures", {}).items()
                          if captures.get(name) not in allowed]
            review_issues = tuple(rule.get("review_issues", ())) + ("原文对应与数学语义需人工核对。",)
            if mismatches:
                review_issues += ("实际关系符与已审核适用范围不同：" + ", ".join(mismatches),)
                issues.append({"item": rule["id"], "code": "scope_relation_changed", "captures": captures})
            # role describes the material, separately from status and proof_status.
            role = {"model": "model_definition", "analysis": "analysis_definition", "goal": "guarantee_statement"}
            items.append(SemanticItem(rule["id"], rule["category"], rule["title"], rule["summary"], normalized,
                         rule.get("normalization_origin", "rule_interpretation"),
                         rule.get("material_role", role[rule["category"]]), tuple(sources),
                         tuple(rule.get("requires", ())), "blocked" if mismatches else "needs_review",
                         review_issues,
                         "unproved" if rule["category"] == "goal" else "not_applicable"))
        # Propagate missing support without discarding a candidate's independently found guarantee quote.
        # present and blocked track available support and propagate gaps through declared dependencies.
        present = {item.key for item in items}
        blocked = ({rule["id"] for rule in self.rules["rules"]} - present) | {item.key for item in items if item.status == "blocked"}
        while True:
            expanded = blocked | {item.key for item in items if any(key in blocked for key in item.requires)}
            if expanded == blocked:
                break
            blocked = expanded
        for index, item in enumerate(items):
            if item.key in blocked and any(key in blocked for key in item.requires):
                missing = [key for key in item.requires if key in blocked]
                message = "需要补齐或复核的依赖项：" + ", ".join(missing)
                items[index] = replace(item, status="blocked", review_issues=(*item.review_issues, message))
                issues.append({"item": item.key, "code": "missing_dependency", "dependencies": missing})
        return SemanticSnapshot(1, extraction_id, extraction.source_sha256, self.profile,
                                tuple(items), tuple(issues), self.choices)
