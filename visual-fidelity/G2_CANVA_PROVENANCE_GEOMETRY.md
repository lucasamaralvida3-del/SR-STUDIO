# G2 Canva provenance and page geometry

Scope: Novo Studio de Encartes G2 / SR Graphics Engine 2 only.

## Direct Canva dimension evidence

The direct Canva connector confirmed the native canvas as `1080 x 1350` for all 11 measured pages:

- `DAHMLMj6EH8` — OFERTAS QUINTA FILÉ NOVO — pages 12, 13, 14, 15.
- `DAHMAeLZD3Q` — OFERTAS TERÇA VERDE NOVO — pages 5, 6, 8.
- `DAHMFY898gM` — OFERTAS QUARTA CAFÉ COM PÃO NOVO — pages 7, 8, 9, 10.

Official direct PNG references remain `0/11`. Canva thumbnails are provenance evidence only and are not Fidelity Lab references. `acceptance_thresholds` remains `null`.

## PPTX provenance

The three hash-locked source PPTX packages carry the Canva design ID in `docProps/core.xml` as `dc:identifier`, matching the design IDs above. They also share a multi-field package fingerprint:

- core created `2006-08-16T00:00:00Z`;
- core modified `2011-08-01T06:04:30Z`;
- core revision `1`;
- Application `Microsoft Office PowerPoint`;
- AppVersion `14.0000`;
- Slides `0` despite the real deck containing slides;
- PresentationFormat `On-screen Show (4:3)` despite the actual physical page being portrait 4:5-like.

No single marker or aspect ratio is sufficient. G2 classifies Canva as `reliable` only when a Canva-shaped design identifier and at least six independent fingerprint markers agree. Identifier-only or partial fingerprint evidence is `partial` and does not activate a canvas override.

## Geometry contract

The physical OOXML page remains immutable evidence:

```text
physical_page_size:
  width_emu: 10287000
  height_emu: 12852400
  width_pt: 810
  height_pt: 1012
```

For the reliable Canva 4:5 export profile, G2 layers the upstream native canvas on top:

```text
intended_canvas_size:
  width: 1080
  height: 1350
source_profile:
  name: canva
  confidence: reliable
```

The shared PPTX importer is not changed. Its physical-ratio scene is converted only at the G2 import bridge seam, before G2 fidelity, artwork, fillRect and group enrichment. Existing G2 node coordinates are scaled into the intended coordinate system. Generic Office PPTX and arbitrary page sizes retain their physical aspect ratio.

At `target_width=1229`, a 1080 x 1350 semantic page scales to 1229 x 1536 after the existing renderer rounding. The renderer itself is unchanged.

## custGeom / fillRect diagnostic

G2 already parses DrawingML `custGeom` in `pptx_fidelity.py` and can attach a non-rectangular `clip_path` to an IMAGE that exists when the fidelity pass runs. The Qt renderer already intersects that path with the rectangular fillRect clip.

The current loss point is pass ordering for late artwork recovery:

1. `enhance_pptx_document()` runs and attaches custGeom only to images already in SR Scene 2;
2. `recover_pptx_fill_rects()` then invokes artwork recovery and may create missing IMAGE nodes;
3. fillRect semantics are attached to those recovered images;
4. there is no second custGeom enrichment pass, so a late image can have `fill_rect` but no `clip_path`.

A minimal regression fixture now pins: picture fill + triangular non-rectangular custGeom + negative fillRect. No MASK correction is applied in this round.

## Group stacking diagnostic

PPTX groups are rebuilt with `parent_id` / `children` in OOXML order, but production rendering currently iterates `GraphicsPage.ordered_nodes()` globally by `(z_index, id)` and skips GROUP nodes instead of recursively rendering group children. Therefore group-local stacking order is not yet the authoritative render traversal. No stacking correction is applied in this round.

## Gate state

- Functional Beta remains the baseline gate.
- Official PNG: 0/11.
- Visual gate: pending direct PNG corpus.
- Acceptance thresholds: null.
- Legacy Gerador de Cartazes gates and thresholds are out of scope.
