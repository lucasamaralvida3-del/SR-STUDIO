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

## Why the first quantitative baseline is not fabricated

A case is promoted to `approved_cases` only when the same source slide has a **direct PNG export from Canva or PowerPoint**, with an explicit slide mapping, width/height and SHA-256. The available Canva images with UI chrome are screenshots and are therefore rejected as references. Clean JPG artwork `7.jpg` through `10.jpg` is also not promoted because its source PPTX/slide pairing is not proven and corpus v1 requires direct PNG references.

The previous `quinta-file-13-08-2026.json` cannot be silently reused: its expected PPTX SHA-256 is not present in the currently accessible corpus.

## Immutability

Once a case is approved, its source/reference hashes are immutable. A changed artwork or reference must create a new case/version. A hash mismatch is a hard validation failure.

## Baseline state

**VISUAL READINESS: UNMEASURED.**

This means the official G2 reference pair is incomplete, not that the G2 renderer failed a visual score. Functional Beta evidence remains separate and unchanged.

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
