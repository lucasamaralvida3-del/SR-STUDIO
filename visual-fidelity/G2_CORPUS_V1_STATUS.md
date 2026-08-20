# G2 Official Visual Corpus v1 — Status

## Scope

This registry belongs exclusively to the **SR Studio de Encartes G2**. The legacy Gerador de Cartazes is a different product and its Golden Masters are out of scope.

## Current registry

- Registry: `visual-fidelity/g2-official-corpus-v1.json`
- Measured provisional manifest: `visual-fidelity/g2-studio-corpus-v1.json`
- Measured baseline results: `visual-fidelity/g2-studio-corpus-v1-baseline.json`
- Policy: **measure first**; no visual acceptance threshold is inherited from another product.
- Approved PNG cases: **0**
- Provisional measured cases: **3 documents / 11 pages**
- Reference conformance: **pending direct PNG exports**

The recovered reference artwork is direct Canva **JPEG**, hash-pinned and provenance-checked. It is valid evidence for establishing a provisional visual distribution, but it does not satisfy the current official-corpus requirement that approved references be direct PNG exports. No JPEG was renamed or converted to pretend compliance.

## Measured documents

1. `OFERTAS QUINTA FILÉ NOVO (1).pptx`
   - SHA-256: `7c45cfa205c7e14af69e41c8d63b1c6a9d1a06df3cf9d0131ed612029884e536`
   - slides 12–15
2. `OFERTAS TERÇA VERDE NOVO.pptx`
   - SHA-256: `6e186a90c5591da2801d9049d5357755ab323f8d76b373104cbf757b0bc9c920`
   - slides 5, 6 and 8
3. `OFERTAS QUARTA CAFÉ COM PÃO NOVO.pptx`
   - SHA-256: `df20e5650711755cd9655b33eab2f72f0d7588f95c06bb34dca161dee2eae395`
   - slides 7–10

All measurements were produced from the frozen functional G2 head `d14dc5bed4bf4f7402f4668eb66a63823f48a35a` before fidelity corrections.

## Hash and provenance validation

- PPTX identity: **PASS** for all three measured documents.
- Provisional Canva JPEG identity: **PASS** for all 11 references.
- Wrong-name/hash substitution: forbidden and detected by the manifest/reference tooling.
- Direct-PNG requirement: **PENDING**; therefore `approved_cases` remains empty.

Screenshots with Canva/Studio UI chrome remain rejected as baselines.

## Baseline distribution — 11 provisional cases

- score min: **94.4183%**
- score max: **97.7681%**
- score mean: **95.9754%**
- score median: **96.3717%**
- mean pixel pass: **87.0328%**
- mean changed area: **12.9672%**
- mean render time: **~601.9 ms/case**
- acceptance thresholds: **UNSET**

These values are a G2-specific baseline distribution, not a production PASS/FAIL gate. No threshold from the legacy Gerador de Cartazes has been reused.

### Per-page baseline

| Case | Score | Pixel pass | Changed area | Render |
|---|---:|---:|---:|---:|
| Quinta s12 | 94.5157% | 82.4941% | 17.5059% | 2054.5 ms |
| Quinta s13 | 94.9060% | 84.3516% | 15.6484% | 453.9 ms |
| Quinta s14 | 94.4183% | 81.8881% | 18.1119% | 469.8 ms |
| Quinta s15 | 96.4772% | 89.6350% | 10.3650% | 496.4 ms |
| Terça Verde s05 | 95.5706% | 84.7350% | 15.2650% | 396.8 ms |
| Terça Verde s06 | 96.3717% | 86.9997% | 13.0003% | 391.9 ms |
| Terça Verde s08 | 97.7422% | 93.5986% | 6.4014% | 443.0 ms |
| Quarta Café s07 | 95.0775% | 84.7337% | 15.2663% | 368.7 ms |
| Quarta Café s08 | 96.4502% | 87.6683% | 12.3317% | 317.0 ms |
| Quarta Café s09 | 96.4323% | 88.4553% | 11.5447% | 631.2 ms |
| Quarta Café s10 | 97.7681% | 92.8016% | 7.1984% | 597.1 ms |

## Systemic findings

All 11 candidates render at the same width as the reference and exactly **1 pixel shorter** in height. The original dimension mismatch is retained in the baseline records. For content measurement only, the lab normalized the missing canvas pixel without rescaling.

Refined approximate attribution of measured visual gap:

- LAYERS: **53.18%**
- CROP: **30.13%**
- MASK: **12.45%**
- TEXT: **4.23%**

`WORDART`, `PRICE`, `PRODUCT` and `IMPORT` are not independently isolated by the current scene-aware classifier; this must not be interpreted as zero contribution. `IMPORT/RENDER` have a separate cross-cutting geometry signal from the 1-pixel height mismatch in 11/11 cases.

## CI validation

Corpus/provenance contracts have passed G2 Global Integration on Linux and Windows/Qt. The preceding validation probe also passed QA, Export and Release Engineering. No product code was changed to obtain these measurements.

Functional regressions introduced by corpus work: **0 known**.

## Baseline state

**VISUAL READINESS: BASELINE ESTABLISHED.**

**OFFICIAL PNG CORPUS APPROVAL: PENDING.**

This distinction is intentional: the visual truth has been measured from direct Canva JPEG evidence, while the stricter immutable official-v1 contract still waits for direct PNG references.

## Next actions

1. recover/export the 11 direct Canva/PowerPoint PNG references for these exact source versions and append their SHA-256 values without overwriting the provisional JPEG evidence;
2. rerun the same 11 cases and confirm whether PNG-vs-JPEG materially changes the distribution;
3. isolate the 1-pixel page-height discrepancy between imported page geometry and renderer output sizing;
4. only after that baseline is frozen, prioritize systemic LAYERS → CROP → MASK issues;
5. add real G2 documents that cover ProductCards and a dedicated transparency case;
6. keep the legacy Gerador de Cartazes entirely outside this corpus and acceptance process.
