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

## Validation status
- GitHub is receiving the branch commits.
- A repository workflow named `upgrade-installer-1.2-retry.yml` is automatically firing on pushes and reports failure with zero jobs; it is an unrelated installer workflow and is outside this G2 mission.
- No G2 test workflow/status has been produced for the latest commits through the available connector, so the newly added tests must still be executed in a Python test environment before merge or release.
- Do not merge this branch to operational Beta/Stable until the G2-focused tests are executed and green.

## Next priorities
1. Execute the focused G2 test suite when a runnable environment becomes available; fix any failures before expanding scope.
2. Audit page duplication identity remapping (node/slot/semantic IDs) because the current implementation deep-copies the active page and only refreshes the page ID/slot page ownership.
3. Audit ProductCard/PriceBlock unit recognition and real SR encarte variants without importing Cartazes rules into G2.
4. Continue real PPTX/Canva fidelity blockers: transform stack, WordArt, Office line-box, vertical anchor, margins/autofit.
5. Verify preview/PNG/PDF parity on a real multi-product encarte.
