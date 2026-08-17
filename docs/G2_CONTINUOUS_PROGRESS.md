# SR Graphics Engine 2 — Continuous Progress

## Mission
This log tracks work on **Studio de Encartes / SR Graphics Engine 2 only**.

### Source baseline
- Source commit: `94a5f8ec7f624e87186cd53facb7c90b3d4fd51b`
- Operational release carrying this source: Beta 7.36
- Graphics2 level preserved in that source: alpha.43

### Hard scope boundary
Allowed:
- `src/srstudio/graphics2/**`
- G2-specific QML
- G2-specific tests/fixtures/docs
- PPTX/Canva fidelity work used by Studio de Encartes
- ProductCard / PriceBlock / SmartSlot semantics in G2
- `.srscene`, autosave, multi-page, PNG/PDF, preview/export parity

Do not modify as part of this mission:
- Gerador de Cartazes / Cartazes Pro
- Promoções
- Atacado
- Stable/Beta release manifests
- launcher/updater/installer
- unrelated SR Studio modules

## Product definition
Studio de Encartes means **complete supermarket flyer pages**, not single price posters. A real page may contain campaign header, themed background, multiple product images, multiple ProductCards, PriceBlocks, highlighted and secondary products, footer, and multiple pages.

## Gates
### G2 PROFESSIONAL USABLE
Required before declaring the editor usable for real experimental work:
- no known P0
- no P1 blocking the main flow
- real PPTX import works
- full page appears
- multiple products appear
- text/image/price editing works
- ProductCard and PriceBlock are usable
- SmartSlots are useful and conservative
- move/resize works
- undo/redo works
- multi-page works
- save/open works
- autosave is safe
- PNG/PDF work
- preview/export are coherent
- interactive performance is acceptable
- required G2 tests are green
- one real full-encarte workflow passes end to end

### G2 PRODUCTION CANDIDATE
After Professional Usable, continue toward high fidelity across the real corpus, stable preview/export parity, no known data-loss path, controlled regressions, strong content-aware fidelity diagnostics, and reusable architecture.

## Fidelity policy
Official Golden Master thresholds must not be weakened.

Global similarity is not sufficient when a renderer can score well by leaving large white regions empty. Keep content-aware diagnostics alongside the official gate, including where possible: reference/render bbox, IoU, x/y delta, width/height error, baseline delta, foreground changed pixels, ink coverage, and mask overlap.

Priority fidelity blockers remain:
1. DrawingML transforms / off-slide objects / groups
2. WordArt geometry
3. Office line-box behavior
4. vertical anchor
5. transformed margins / anchorCtr
6. autofit and run inheritance
7. preview/export parity

Avoid template-specific offsets.

## Working loop
For each meaningful cycle:
1. identify the highest P0/P1/P2 blocker
2. measure current behavior
3. find root cause
4. implement the smallest architectural fix
5. test
6. measure again
7. revert if objectively worse
8. keep and commit if better
9. record the result here
10. continue to the next blocker

## Handoff rule
When Codex capacity returns, it should read this file first, inspect the latest G2-only branch/commit, and continue from the last recorded cycle without repeating completed work.

## Progress
### ChatGPT continuation — initialization
- Baseline selected: `94a5f8ec7f624e87186cd53facb7c90b3d4fd51b` (Graphics2 alpha.43 preserved)
- Working branch: `g2/chatgpt-professional-usable`
- Scope locked to Studio de Encartes / G2 only
- Initial audit targets: semantic blocks, model/operations, command router, drop target, smart layout, autosave/package persistence, GraphicsEditor QML, and core G2 tests.
- Initial product priority: strengthen the real encarte workflow from ProductCard/PriceBlock semantics through editing, persistence and export, without touching poster modules.
