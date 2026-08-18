# G2 Official Visual Corpus v1 — Status

## Scope

This registry belongs exclusively to the **SR Studio de Encartes G2**. The legacy Gerador de Cartazes is a different product and its Golden Masters are out of scope.

## Current registry

- Registry: `visual-fidelity/g2-official-corpus-v1.json`
- Policy: measure first; no visual acceptance threshold is inherited from another product.
- Approved cases: **0**
- Real source candidates: **1 document / 3 slides**
- Candidate source: `OFERTAS QUINTA FILÉ NOVO.pptx`
- Exact source SHA-256: `0353b8e2848eb6019c970ae6c83610ecb821d66d29a2f8faff80ee416b1f76f8`
- Source lineage: Canva PPTX export, with Canva UI capture retained only as provenance evidence, never as a visual baseline.

## Structural G2 audit of the candidate

The candidate was imported using the G2 `GraphicsImportService` from the validated functional code line before any fidelity correction work.

Observed result:

- imported pages: **3/3**;
- observed import time: **~307.8 ms**;
- page node counts: **119 / 76 / 27**;
- page 1: 58 text, 20 rect, 20 group, 17 image, 4 line nodes;
- page 2: 38 text, 13 image, 11 rect, 11 group, 3 line nodes;
- page 3: 11 image, 8 text, 4 rect, 4 group nodes;
- fonts observed: **Anton** and **High Cruiser**.

Coverage demonstrated by this candidate: multipage, text, prices, images, groups, shapes, layers, fonts and multiple layouts.

Coverage still missing from corpus v1: crop, transparency, masks and ProductCards. These must be supplied by additional real G2 projects rather than inferred from this file.

This structural audit is **not** a visual score and must never be substituted for a direct-reference comparison.

## Why the first quantitative baseline is not fabricated

A case is promoted to `approved_cases` only when the same source slide has a **direct PNG export from Canva or PowerPoint**, with an explicit slide mapping, width/height and SHA-256. The available Canva images with UI chrome are screenshots and are therefore rejected as references. Clean JPG artwork `7.jpg` through `10.jpg` is also not promoted because its source PPTX/slide pairing is not proven and corpus v1 requires direct PNG references.

The previous `quinta-file-13-08-2026.json` cannot be silently reused: its expected PPTX SHA-256 is not present in the currently accessible corpus.

## Immutability

Once a case is approved, its source/reference hashes are immutable. A changed artwork or reference must create a new case/version. A hash mismatch is a hard validation failure.

## CI validation

Validation-only PR #44 ran the G2 gates against the corpus registry/provenance tests without merging the probe marker.

Results:

- G2 Global Integration — **PASS**;
- Windows/Qt full Graphics2 suite — **519 passed**, 229 deselected, 2 deprecation warnings;
- Linux full Graphics2 suite — **517 passed, 2 skipped**, 229 deselected, 2 deprecation warnings;
- G2 QA Integration — **PASS**;
- G2 Export Integration — **PASS**;
- G2 Release Engineering — **PASS**;
- functional regressions introduced by corpus work: **0 known**.

The two Linux skips are environment-conditioned tests already allowed by the suite; no failed G2 test was hidden or deleted.

## Baseline state

**VISUAL READINESS: UNMEASURED.**

This means the official G2 reference pair is incomplete, not that the G2 renderer failed a visual score. Functional Beta evidence remains separate and unchanged.

There is currently no legitimate min/max/mean/median, no diff ranking and no category attribution for the official G2 corpus because there are **0 approved reference pairs**. Publishing numerical scores now would require using a screenshot, an unpaired artwork, a G2-generated image or a hash-mismatched source, all of which are forbidden by the corpus contract.

## Promotion checklist

For each case to become official:

1. direct Canva/PowerPoint PNG export;
2. explicit source slide number;
3. PPTX SHA-256;
4. PNG SHA-256;
5. PNG width/height;
6. source type (`canva` or `powerpoint`);
7. notes/provenance;
8. run G2 importer → SR Scene 2 → `qt_renderer` → Fidelity Lab;
9. store raw score, pixel pass, changed area, render time, diff and heatmap;
10. only after the first real distribution, propose a G2-specific acceptance threshold.

## Next corpus acquisition

Promote this candidate only after direct PNG exports for its exact source version are recovered, or add new real Studio de Encartes projects with their official exports. Prefer the next 2–4 documents to close the current coverage gaps: crop, transparency/mask and ProductCard-heavy layouts.
