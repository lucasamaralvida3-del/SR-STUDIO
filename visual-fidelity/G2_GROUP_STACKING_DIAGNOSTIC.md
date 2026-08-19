# G2 GROUP STACKING / LAYERS — diagnostic only

Scope: **new Studio de Encartes G2 only**. No renderer or traversal change is part of this investigation.

Base integration SHA: `3e568f7717bb86978c58f50a5162fe44e27c4bd8`.

## Frozen corpus

- Quinta Filé: slides 12, 13, 14, 15
- Terça Verde: slides 5, 6, 8
- Quarta Café com Pão: slides 7, 8, 9, 10
- Source top-level shapes: 751
- Groups: 146

The three source PPTX files are the previously hash-locked Canva packages. No thumbnail or visual-score reference was used.

## Result

The hypothesized real-corpus failure — an external painted node occurring between two children of the same OOXML group because `GraphicsPage.ordered_nodes()` is global — was **not reproduced in the 11 frozen slides**.

The PPTX reader flattens each `p:grpSp` depth-first and assigns sequential `z_index` values while extending the slide element list. In this corpus every group has exactly two direct primitive children and no nested groups. Their flattened positions are contiguous.

Group reconstruction restores `parent_id` and `children` in OOXML child order. It creates the GROUP node at the minimum child z-index but does not rewrite the child z-index values. The selected slides also contain no compound-text or text-shape visual companion creation that could split a group span. The effective renderer therefore sees the same visible primitive order as the OOXML depth-first flattening for these groups.

The renderer still paints globally from `page.ordered_nodes()` and skips GROUP nodes rather than traversing `group.children`. This is an architectural susceptibility, not a proven loss source for this corpus.

## Metrics

| Metric | Count |
|---|---:|
| GROUPS TOTAL | 146 |
| GROUP CHILD RELATIONSHIPS | 292 |
| GROUPS WITH OVERLAP | 146 |
| GROUPS WITH GLOBAL INTERLEAVING | 0 |
| INTERLEAVED CHILD RELATIONSHIPS | 0 |
| NESTED GROUPS | 0 |
| POTENTIALLY VISUALLY AFFECTED | 0 |

Per slide:

| Corpus | Slide | Top-level | Groups | Child rels | Groups with overlap | Interleaved | Visually relevant |
|---|---:|---:|---:|---:|---:|---:|---:|
| Quinta Filé | 12 | 105 | 21 | 42 | 21 | 0 | 0 |
| Quinta Filé | 13 | 60 | 8 | 16 | 8 | 0 | 0 |
| Quinta Filé | 14 | 105 | 21 | 42 | 21 | 0 | 0 |
| Quinta Filé | 15 | 23 | 4 | 8 | 4 | 0 | 0 |
| Terça Verde | 5 | 103 | 22 | 44 | 22 | 0 | 0 |
| Terça Verde | 6 | 69 | 15 | 30 | 15 | 0 | 0 |
| Terça Verde | 8 | 22 | 8 | 16 | 8 | 0 | 0 |
| Quarta Café com Pão | 7 | 104 | 21 | 42 | 21 | 0 | 0 |
| Quarta Café com Pão | 8 | 69 | 11 | 22 | 11 | 0 | 0 |
| Quarta Café com Pão | 9 | 69 | 11 | 22 | 11 | 0 | 0 |
| Quarta Café com Pão | 10 | 22 | 4 | 8 | 4 | 0 | 0 |

All 146 groups have real overlap between their two direct child bounds. Overlap alone is therefore not evidence of a stacking bug; the missing condition is an external paint-eligible node interleaved between those children, and that count is zero.

### Quinta Filé slide 12

This slide has the previously known 105 top-level objects and 21 groups. Every group is a two-child pair such as `Group 8 = Freeform 9 + TextBox 10`. The pair occupies consecutive flattened z positions (for Group 8: 6 and 7), the child bounds overlap, and there is no external node between them. The same holds for all 21 groups on the slide. Detailed group data is persisted in `visual-fidelity/g2-group-stacking-diagnostic-v1.json`.

## Minimal fixture

`tests/test_graphics2_group_stacking_diagnostic.py` intentionally constructs:

- GROUP G with child A at z=10 and child B at z=12;
- external visible C at z=11;
- all three rectangles overlapping.

Expected group/composite traversal is `A -> B -> C`, while the current global paint selection resolves `A -> C -> B`.

This fixture **detects the architectural susceptibility without changing the renderer and without asserting that the frozen corpus contains it**.

## Classification

**GROUP STACKING ROOT CAUSE: NOT CONFIRMED for the frozen 11-slide corpus.**

The architecture can reproduce global interleaving when group-child z-index continuity is broken, but the real corpus contains zero such paint interleavings. Therefore this hypothesis should not be promoted to a visual correction without new evidence (preferably official lossless PNG or a real PPTX whose final Scene actually contains an interleaved visible node).

## Visual gate

- OFFICIAL LOSSLESS PNG: 0/11
- VISUAL SCORE: NOT MEASURED
- acceptance thresholds: unchanged / NULL

No Canva thumbnail was used as fidelity proof.