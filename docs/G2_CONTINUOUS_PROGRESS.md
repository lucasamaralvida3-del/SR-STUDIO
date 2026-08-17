# SR Graphics Engine 2 — Continuous Progress

## Mission
This log tracks work on **Studio de Encartes / SR Graphics Engine 2 only**.

### Source baseline
- Source commit: `94a5f8ec7f624e87186cd53facb7c90b3d4fd51b`
- Operational release carrying this source: Beta 7.36
- Graphics2 level preserved in that source: alpha.43
- Working branch: `g2/chatgpt-professional-usable`

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

### Cycle C1 — branch isolation and durable handoff
- Baseline selected: `94a5f8ec7f624e87186cd53facb7c90b3d4fd51b` (Graphics2 alpha.43 preserved).
- Created dedicated branch `g2/chatgpt-professional-usable` so experimental G2 work cannot alter the operational Beta/Stable branches.
- Scope locked to Studio de Encartes / G2 only.
- Commit: `d50c67db80ddf18401e9ac18def327b41e85cd2a`.

### Cycle C2 — `.srscene` persistence/recovery safety
Problem:
- `load_package()` trusted ZIP member uniqueness and manifest identity too loosely. A truncated archive, duplicate mandatory member, path traversal member, or manifest/scene identity mismatch could enter the recovery path before a clear failure.

Change:
- Hardened `src/srstudio/graphics2/package.py`.
- Reject corrupt/truncated ZIPs with domain-specific `ValueError`.
- Require unique `manifest.json` and `scene.json`.
- Reject unsafe archive paths before extraction.
- Bound manifest/scene payload sizes.
- Verify scene SHA before deserialization.
- Verify manifest schema/document ID against the restored scene.
- Run structural integrity before extracting assets.

Tests added:
- clean round-trip;
- corrupt/non-ZIP package;
- missing required member;
- document ID mismatch;
- schema mismatch;
- duplicate required members;
- unsafe member paths.

Commits:
- implementation `1b7495241c8eb7aa8f0994d8878dd34569520716`
- tests `a55a843952c86796d5e43a31b25b734750655141`

### Cycle C3 — autosave recovery safety
Problem:
- retention was based on raw files, so a corrupt recent generation could consume a retention slot and cause an older valid recovery to be deleted.
- `recover()` did not assert that a supplied RecoveryPoint actually belonged to the restored document.

Change:
- Reopen and validate a freshly written autosave before promoting it to `latest`.
- Recovery verifies document identity.
- Only valid generations count toward retention.
- Corrupt generations are skipped but preserved for diagnostics instead of silently replacing a valid point.
- File stat is read once per valid point.

Tests:
- generation retention and recovery;
- corrupt generation does not consume a valid retention slot;
- cross-document RecoveryPoint rejected;
- latest valid generation survives a corrupt newer file.

Commits:
- implementation `032ad949cff0766a4e20878d4816039f043cfe65`
- tests `017003a7d09ab71f6e4f6db685204ce5d1f5b717`

### Cycle C4 — Professional Usable document gate
Problem:
- Production Gate focuses structural/import/visual release quality, but there was no separate diagnostic for the actual human Studio de Encartes workflow.

Change:
- Added `src/srstudio/graphics2/usability_gate.py`.
- It does not replace or weaken Production Gate / Golden Masters.
- Checks structural integrity, unique page IDs, valid active page, visible/editable content, text/image presence, SmartSlot page ownership, semantic member integrity, ProductCard, PriceBlock, SmartSlot, and optionally at least one bound product.
- Exposes metrics useful to UI/diagnostics and future Codex cycles.

Tests:
- blank document fails;
- realistic semantic product page passes;
- wrong slot page fails;
- orphan semantic member fails;
- duplicate page ID fails.

Commits:
- implementation `24ee73635f0057e9a0974e2df17a9c539de913ee`
- tests `d5011be73ca85c05240a7f6405130755cd1dde36`

### Cycle C5 — real edit/persist/multipage workflow contract
Added `tests/test_graphics2_professional_workflow.py` covering a practical encarte flow:
1. create semantic product fields;
2. bind product name/price/unit/limit;
3. build ProductCard + PriceBlock semantics;
4. move a field;
5. undo;
6. redo;
7. duplicate page;
8. verify SmartSlot page ownership;
9. run Professional Usable gate;
10. save `.srscene`;
11. reopen;
12. validate multipage persistence and semantic counts.

Commit: `193f6ff9eaf81f46045b0751c6d6d891ce8b1544`.

### Cycle C6 — safe page duplication, dedicated CI and headless export
Problem:
- the old page clone only refreshed the page ID, which could leave node, SmartSlot and semantic identities duplicated;
- G2 lacked a short dedicated Windows gate;
- direct PNG/PDF calls outside the editor could run without a `QGuiApplication`.

Change:
- added safe page duplication with fresh/remapped page/node/slot/semantic IDs and internal references;
- added `.github/workflows/g2-professional-usable.yml` with Windows/Python 3.11, compile, Ruff, pytest, JUnit and diagnostic artifacts;
- added a headless Qt render runtime guard.

Result:
- multipage clones no longer collide;
- G2 has a dedicated CI source of truth;
- CLI/probe/tests can export PNG/PDF without a Qt process crash.

### Cycle C7 — recovered SmartSlot identity and persisted image replacement
Problem:
- recovered slots could collide between pages and lose bound product state during semantic rebuild;
- imported images could be cropped/moved but not safely replaced as a persistent `.srscene` asset.

Change:
- `semantic_runtime.py` scopes recovered identities only when collisions exist and restores product/lock/snapshot on rebuild;
- image replacement now embeds/updates the asset, preserves the frame and participates in undo/redo;
- page add/duplicate controls were exposed in the G2 QML UI.

Result:
- recovered semantic state is stable across rebuild/multipage;
- image replacement persists after save/open.

### Cycle C8 — real PPTX editability
Problem:
- the historical import bridge intentionally locked nodes outside SmartSlots, so a real PPTX could open visually but remain effectively read-only.

Change:
- added `import_edit_runtime.py` policy `content-v1`:
  - visible imported TEXT => editable;
  - visible imported IMAGE => editable;
  - structural shapes remain protected;
  - hidden/template-hidden nodes remain protected.

Result:
- `CARTAZ_VENDA.pptx` opens through the real editor import path with editable text and passes save/open + PNG/PDF.

### Cycle C9 — complete Brazilian price recovery
Problem:
- the historical fallback recognized split prices such as `R$` + `92` + `,77` + unit;
- real SR PPTX files also use `R$` + `92,77` + `CADA`.

Change:
- added `semantic_price_runtime.py` as a conservative secondary path;
- associates currency/unit by rectangle gap instead of center distance;
- keeps the historical split-price algorithm intact;
- rejects isolated decimal text without currency+unit evidence.

Result:
- complete Brazilian price tokens become valid PriceBlocks without filename-specific rules.

### Cycle C10 — explicit named semantics: one product, two prices
Problem:
- a real two-price template initially produced two fake ProductCards/SmartSlots because each price was recovered independently.

Change:
- added `semantic_named_slot_runtime.py`, prioritizing explicit PPTX names such as:
  - `SR_PRODUTO`;
  - `SR_PRECO_PROMO`;
  - `SR_PRECO_CLUBE`;
  - `SR_UNIDADE_PROMO`;
  - `SR_UNIDADE_CLUBE`.
- added template-aware binding so a separate `R$` box stays separate and numeric boxes receive only `12,34`;
- preserves `CADA` for unit-sold products;
- product-image binding is deliberately conservative: footer/banner/logo images are not promoted as product photos without explicit image semantics.

Result on the real two-price template:
- 1 ProductCard;
- 1 SmartSlot;
- 1 normal PriceBlock;
- 1 Club/app PriceBlock;
- binding, undo/redo, save/open and export all pass.

### Cycle C11 — Club Exclusive and CPF limits
Problem:
- Club-only templates still depended on spatial fallback;
- `SR_LIMITE` / `SR_CLUBE_LIMITE` were not part of the explicit product slot.

Change:
- explicit named recovery now supports `SR_CLUBE_PRODUTO`, `SR_CLUBE_PRECO`, `SR_LIMITE` and `SR_CLUBE_LIMITE`;
- Club-only price is represented as app/Club price when no base price exists;
- limit binding supports `limit` and `cpf_limit`, renders `LIMITE DE [valor] POR CPF`, and hides the field when empty.

Result:
- Club Exclusive is no longer dependent on spatial fallback;
- limit and price behavior passes real-template tests and undo/redo.

### Cycle C12 — eight-model real PPTX corpus audit
Added `tests/test_graphics2_real_corpus_audit.py` and audited the eight preserved SR PPTX models.

Final result:

| Model | Graphics Ready | Semantic Ready | SmartSlots | ProductCards | PriceBlocks |
|---|---:|---:|---:|---:|---:|
| `ATACADO.pptx` | yes | yes | 1 | 1 | 1 |
| `CARTAZ_VENDA.pptx` | yes | yes | 1 | 1 | 1 |
| `CLUBE_EXCLUSIVO.pptx` | yes | yes | 1 | 1 | 1 |
| `CLUBE_EXCLUSIVO_COM_LIMITE.pptx` | yes | yes | 1 | 1 | 1 |
| `SEGUNDA_DA_LIMPEZA_1_PRECO.pptx` | yes | yes | 1 | 1 | 1 |
| `SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.pptx` | yes | yes | 1 | 1 | 1 |
| `SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx` | yes | yes | 1 | 1 | 2 |
| `SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx` | yes | yes | 1 | 1 | 2 |

Corpus invariants:
- no duplicate page/node/slot IDs;
- no orphan semantic members;
- no missing SmartSlot nodes;
- no Preview preflight errors;
- visible editable content in all eight models.

### Cycle C13 — real Professional Usable Preview end-to-end gate
Added `tests/test_graphics2_usable_preview_e2e.py`, which executes one continuous real operator workflow from `SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx`:
1. import the real PPTX;
2. resolve SmartSlot;
3. drag/drop a product through the real `drop_product` Command Router path;
4. update product name, normal price, Club/app price and CPF limit;
5. edit text;
6. select and move;
7. resize;
8. undo/redo;
9. replace an imported image while preserving its frame;
10. undo/redo image replacement;
11. duplicate the page with safe identities;
12. autosave and recover;
13. save portable `.srscene`;
14. reopen;
15. verify edits/product persistence;
16. render PNG;
17. compare PNG before/after save-open — pixel-identical;
18. export two-page PDF.

Result: PASS.

### Cycle C14 — complete real Qt/QML host gate
Added `tests/test_graphics2_real_qml_host_preview.py`.

The test loads a real PPTX and starts the actual Qt Quick host with software/offscreen rendering, covering:
- `GraphicsEditor.qml`;
- real `SceneBridge`;
- live scene image provider;
- `ImageInspector.qml`;
- `QualityInspector.qml`;
- `ProjectActions.qml`;
- QQuick window creation;
- Qt event processing and controlled shutdown.

Result: PASS.

### Cycle C15 — G2 USABLE PREVIEW milestone
Final dedicated validation:
- workflow: `G2 Professional Usable`;
- run: `32068031581`;
- Windows / Python 3.11;
- **61 passed in 6.47s**;
- compile: PASS;
- Ruff: PASS;
- Professional usability contracts: PASS;
- real Qt/QML host: PASS.

Decision:

**G2 USABLE PREVIEW ACHIEVED — 2026-08-17.**

The original continuous mission to reach a usable Preview has reached its defined safe stop condition.

Detailed evidence: `docs/G2_USABLE_PREVIEW.md`.

## Validation status
- Dedicated G2 workflow is green at run `32068031581`.
- Eight of eight preserved SR PPTX models are Graphics Ready and Semantic Ready for the Preview gate.
- The real one-session operator E2E passes through import, product drop, editing, move/resize, image replacement, undo/redo, multipage, autosave/recovery, save/open, PNG and PDF.
- The Qt/QML host starts successfully with a real PPTX.
- The unrelated `upgrade-installer-1.2-retry.yml` workflow remains outside this G2 mission and is not used as the G2 acceptance signal.
- No operational Beta/Stable branch, launcher, installer or release manifest was modified by the Preview milestone work.

## Not declared
- **Production Ready:** not declared.
- **Final PowerPoint fidelity:** not declared.
- **Golden Master pass:** not declared and thresholds were not lowered.
- **Release/installer/main merge:** not performed.

## Next priorities if the mission is extended to Production Hardening
1. DrawingML transforms, groups and off-slide content.
2. WordArt and Office text geometry.
3. Office line-box, vertical anchor, transformed margins and autofit/run inheritance.
4. Continue content-aware diagnostics alongside the unchanged official Golden Master gate.
5. Human tests with additional real Canva/PPTX flyers.
6. Performance testing on larger and multi-page documents.
7. Final editor UX polish.
8. Only then evaluate a distributable Preview build and promotion path.
