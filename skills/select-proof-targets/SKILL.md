---
name: select-proof-targets
description: Select source-grounded, independently provable claims for the Proof target field when extracting a research paper into AutoVISA.
---

# Select proof targets

Identify what would have to be true for the paper's principal contribution to work as claimed. Use the stated research objective, the method specification and the scope of its argument together. A theorem number, a section heading or a high benchmark score does not establish centrality.

## Shape the proposition

For a decision test, connect acceptance under its actual premises to the promised property for the specified instances or behaviors. For a bound, identify the quantity, direction, domain and conditions. For a construction, identify its input contract and what its output satisfies. Use the paper's own claim for other kinds of contribution, including impossibility, optimality or a comparison when that is the central result.

Keep the object, method, quantifiers, hypotheses and conclusion together. Combine a correctness definition with the sufficient criterion that establishes it. Cases belonging to one guarantee stay in that guarantee. Independently applicable methods with separate correctness arguments get separate candidates, even when their conclusions use the same definition. Preserve the distinction between sufficiency, necessity and equivalence. A target is a proposition to check, not a certification that it has already been proved.

## Route each item

- **primary_target**: an independently selectable proposition central to the authors' stated objective. Give a short title identifying the method and property. Order peers by the paper's presentation. Include only as many as the paper supports.
- **secondary_target**: an independent formal result beyond the primary claim, such as dominance or search cost when ancillary. Split a conjunction if its parts have different roles. A comparison of acceptance sets alone cannot establish the accepting methods' correctness.
- **model**, **assumptions**, **analysis**: put definitions, scope, test equations and necessary supporting arguments here as applicable. Omit proof narration and routine intermediate obligations from the target list.
- **evaluation**, **example**: keep reported measurements, parameter sweeps and worked numerical instances here. A counterexample may witness a general separation; keep the instance distinct from the quantified claim.
- Omit prior work mentioned only as background. For empirical-only or ambiguous contributions, leave the target list empty rather than inventing a theorem. When a formal target synthesizes several passages, quote the paper's ownership statement and a passage supporting the guarantee; preserve qualifications in the proposition.

Return each statement in exactly one category. Supply a concise title for targets and an empty title for other rows. Before returning, ask whether proving the selected proposition alone would establish the advertised guarantee of that particular method or result for every instance in its stated scope. Reject targets that silently strengthen a result or merely restate a test procedure.
