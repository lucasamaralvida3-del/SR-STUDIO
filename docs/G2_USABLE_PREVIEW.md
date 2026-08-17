# SR Graphics Engine 2 — G2 Usable Preview

**Status:** ACHIEVED  
**Date:** 2026-08-17  
**Branch:** `g2/chatgpt-professional-usable`

This milestone certifies that the **Studio de Encartes / SR Graphics Engine 2** main experimental workflow is usable for Preview testing. It does **not** declare Production Ready, change Golden Master thresholds, publish a release, modify installer/launcher, or merge to `main`.

## Final validation

Dedicated workflow:

- Workflow: `G2 Professional Usable`
- Run: `32068031581`
- Platform: Windows / Python 3.11
- Result: **PASS**
- Focused suite: **61 passed in 6.47s**
- Compile: PASS
- Ruff: PASS
- Professional usability contracts: PASS
- Real Qt/QML host smoke: PASS

## Real PPTX corpus

All eight preserved SR PPTX models pass the Graphics and Semantic Preview gates:

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

- no duplicate page IDs;
- no duplicate node IDs;
- no duplicate SmartSlot IDs;
- no orphan semantic members;
- no SmartSlots referencing missing nodes;
- no Preview preflight errors;
- visible editable content in all eight models.

## Real operator end-to-end gate

`tests/test_graphics2_usable_preview_e2e.py` starts from a real SR PPTX and validates one continuous operator session:

1. import real PPTX through the editor import path;
2. resolve a SmartSlot;
3. drag/drop a product through `drop_product`;
4. populate name, normal price, Club/app price and CPF limit;
5. edit text;
6. select and move;
7. resize;
8. undo/redo;
9. replace an imported image while preserving its frame;
10. undo/redo image replacement;
11. duplicate the page with fresh/remapped identities;
12. autosave and recover;
13. save portable `.srscene`;
14. reopen the project;
15. verify product and edit persistence;
16. export PNG;
17. compare page PNG before/after save-open — pixel-identical;
18. export a two-page PDF.

## Real Qt/QML host gate

`tests/test_graphics2_real_qml_host_preview.py` launches the actual Qt Quick host with a real SR PPTX using the software/offscreen backend. The smoke covers:

- `GraphicsEditor.qml`;
- real `SceneBridge`;
- live scene image provider;
- `ImageInspector.qml`;
- `QualityInspector.qml`;
- `ProjectActions.qml`;
- QQuick window creation;
- Qt event processing and controlled shutdown.

## Preview capabilities proven

The current branch has a green contract for:

- real PPTX import;
- editable text and imported images;
- safe template structure locking;
- complete Brazilian prices (`R$` + `92,77` + commercial unit);
- one product with normal + Club/app price;
- Club-only templates;
- `SR_LIMITE` / `SR_CLUBE_LIMITE` and `LIMITE DE [valor] POR CPF`;
- hide limit when empty;
- conservative product-image semantics (footer/logo images are not promoted as product photos);
- product drag/drop into SmartSlots;
- move/resize;
- undo/redo;
- image replacement;
- multipage duplication with identity remapping;
- safe autosave/recovery;
- portable `.srscene` save/open;
- PNG/PDF export;
- preview/save-open pixel coherence on the E2E page;
- complete Qt/QML host startup.

## Not declared

### Production Ready

Not declared.

### Final PowerPoint fidelity

Not declared. Alpha 32–35 showed that Office text/WordArt geometry remains the dominant fidelity problem. The Usable Preview work does not lower, replace, or reinterpret the official Golden Master thresholds.

### Release / installer / main

No Preview release was published, no installer was promoted, and this branch was not merged to `main` or operational Beta/Stable branches.

## Recommended next phase — Production Hardening

If work continues beyond the Usable Preview milestone, prioritize:

1. DrawingML transforms, groups and off-slide content;
2. WordArt and Office text geometry;
3. Office line-box, vertical anchor, transformed margins and autofit;
4. content-aware diagnostics alongside the unchanged official Golden Master gate;
5. additional human tests with real Canva/PPTX flyers;
6. performance on larger and multipage documents;
7. final editor UX polish;
8. only then evaluate a distributable Preview build and promotion path.
