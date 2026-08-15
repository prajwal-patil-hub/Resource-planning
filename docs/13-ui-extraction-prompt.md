# UI Component Extraction — the prompt, and its output

Two parts. **Part 1** is a reusable prompt for replicating a reference interface
at high fidelity. **Part 2** is that prompt applied to the three reference images
supplied for this project, producing the spec `glass.css` is built from.

Written this way on purpose: the prompt is reusable for the next reference you
send, and the spec is auditable — you can check whether the implementation
matches what was extracted, instead of taking "it looks about right" on trust.

---

# Part 1 — The extraction prompt

> You are a senior product designer specialising in high-fidelity visual
> replication. You reproduce interfaces by **measuring** them, not by
> impressions. "Frosted glass card" is not a specification; a fill opacity, a
> blur radius and three named inset shadows are.
>
> Given one or more reference images, produce a component specification in the
> order below. Where a value cannot be measured directly, state the inferred
> value **and mark it inferred**. Never silently invent a number.
>
> **1. Ground.** What sits behind everything: photograph, gradient, or solid.
> Note its luminance range and how much variation it carries — a surface that
> refracts needs something varied behind it, or the effect is invisible.
>
> **2. Surface stack.** For every distinct elevation, in order from ground up:
> fill colour and alpha; backdrop blur radius; backdrop saturation; border
> colour, width and whether it varies by edge; corner radius; every inset
> shadow (offset-x, offset-y, blur, spread, colour, alpha) in paint order; every
> outer shadow, same parameters.
>
> **3. Optical treatment.** Refraction, depth, dispersion and frost, where the
> reference exposes them. Translate each into what CSS can actually do, and say
> plainly where CSS cannot reach the reference — an honest gap beats a bad
> approximation shipped as a match.
>
> **4. Typography.** Family class (grotesque / geometric / humanist / serif /
> mono), weights in use, approximate sizes as a ratio to body text,
> letter-spacing on uppercase labels, line-height for body and headings.
>
> **5. Colour roles.** Separate *chrome* colours (the surface system) from
> *semantic* colours (status, priority, risk). These must be independent — a
> semantic colour that only reads on one background is a bug waiting for a
> theme change.
>
> **6. Geometry and rhythm.** Spacing scale, corner radius scale, control
> heights, icon sizes, grid or column widths.
>
> **7. Motion.** Durations, easing curves, what animates on entrance, hover,
> and state change. If the reference is static, propose motion consistent with
> its material — heavy glass moves differently from paper.
>
> **8. Behaviour under stress.** What happens with no data, long strings,
> many items, a light background, a viewer with reduced transparency, a browser
> without `backdrop-filter`. A spec that only describes the happy screenshot is
> half a spec.
>
> **9. Fidelity ledger.** Three lists: what is reproduced exactly, what is
> approximated and by how much, what is deliberately rejected and why. This is
> the most important section — it is what makes the result reviewable.
>
> Constraints: assume a strict CSP (no external fonts, no CDN). Express the
> system as CSS custom properties, so a later change of ground is one edit.
> Never let decoration reduce legibility of data.

---

# Part 2 — The prompt applied to the supplied references

**Sources:** (A) dark loan-pipeline kanban over a coastal photograph;
(B) "Liquid Glass" tutorial, step 02, three inner shadows with stated values;
(C) same tutorial, step 03, glass parameters with stated values.

## 1. Ground

Reference A places every surface over a **photograph** with a wide luminance
range — bright sky, dark water, mid-tone concrete. That variation is what makes
the glass read as glass: the blur has something to distort.

**Consequence for us:** the previous default background was a near-flat dark
gradient. Glass over a flat ground looks like a grey box, which is exactly the
"not glassy enough" symptom reported. The placeholder ground is therefore
rebuilt with high-contrast, multi-hue radial pools, so the material is visible
before a final image is chosen.

## 2. Surface stack

Reference B states its values outright, so these are **measured, not inferred**:

| Layer | Values as stated in the reference |
|---|---|
| Inner shadow 1 | X 4, Y 4, blur 12, spread 2, `#FFFFFF` at 20% |
| Inner shadow 2 | X −2, Y −2, blur 15, spread 1, `#FFFFFF` at 20% |
| Inner shadow 3 | X 0, Y 0, blur 15, spread 2, `#FFFFFF` at 20% |

Three **white** inner shadows, all at 20%, all with real blur and spread. This is
the single most important finding: the previous implementation used 1px hairline
insets, which read as a *border*, not as a thick refracting edge. Soft, spread,
overlapping white glows are what produce the sense of depth.

Applied directly:

```css
--glass-inner-1: inset 4px 4px 12px 2px rgba(255, 255, 255, 0.20);
--glass-inner-2: inset -2px -2px 15px 1px rgba(255, 255, 255, 0.20);
--glass-inner-3: inset 0 0 15px 2px rgba(255, 255, 255, 0.20);
```

| Property | Extracted | Note |
|---|---|---|
| Panel fill | ~6–10% white over ground | *Inferred* from A. Far more transparent than the previous 52% dark tint |
| Backdrop blur | 40px panels, 24px cards | *Inferred* from A's degree of background smearing |
| Backdrop saturation | ~1.4 | *Inferred*; A's background stays colourful through the glass |
| Border | 1px, ~22% white, brighter on the top edge | Visible in both A and B |
| Radius | 20px panels, 14px cards | *Inferred* from A |
| Outer shadow | Large, soft, downward, ~55% black | Present in A; lifts panels off the photograph |

## 3. Optical treatment

Reference C states: **refraction 100, depth 78, dispersion 65, frost 2.**

These are native macOS/Figma material parameters with no direct CSS equivalent.
Honest translation:

| Reference parameter | CSS translation | Fidelity |
|---|---|---|
| Refraction 100 | `backdrop-filter: blur()` — smears rather than bends light | **Approximate.** CSS cannot refract |
| Depth 78 | The three inset shadows above, plus a top-edge highlight | **Close** |
| Dispersion 65 | Faint warm/cool tint at opposing edges, via a gradient overlay | **Approximate.** No true chromatic split |
| Frost 2 | Fine SVG noise overlay at very low opacity | **Close** |

> Stated plainly: CSS blurs what is behind an element; it does not bend light
> through it. Everything here is a convincing impression of refraction, not
> refraction. Claiming otherwise would be the kind of "looks about right" that
> this document exists to avoid.

## 4. Typography

Reference A uses a **neutral grotesque** (Inter-like) — no external fonts are
permitted, so `system-ui` is the closest available and is used throughout.

| Role | Extracted |
|---|---|
| Card title | ~0.88rem, weight 450–500, line-height ~1.35 |
| Column label | ~0.75rem, weight 600, uppercase, letter-spacing ~0.05em |
| Metadata | ~0.72rem, weight 400, at reduced opacity |
| Numerals | Tabular in all data positions |

## 5. Colour roles

Reference A keeps chrome monochrome and reserves colour for meaning — status
pills and the single blue accent on the assistant control. Adopted directly:
the glass palette carries no meaning, and semantic colours (P0, at risk,
overloaded, waiting-on-client) are defined separately so they survive the ground
being swapped.

## 6. Geometry

4px base unit. Column width 268px. Control height 36px. Card padding 12–14px.
Panel padding 18–20px. Gap between columns 13px.

## 7. Motion

Reference A is static, so motion is proposed from the material. Glass is heavy
and damped: it settles, it does not bounce.

| Moment | Treatment |
|---|---|
| Page entrance | Panels rise 8px and fade, staggered ~40ms |
| Card entrance | Rise 10px, fade, staggered ~30ms within a column |
| Hover | 1px lift, border brightens, 140ms |
| View change | Crossfade with a small scale settle, 260ms |
| Composer focus | Glow expands, 200ms |
| New item | Brief highlight sweep so the eye finds what just appeared |
| Easing | `cubic-bezier(0.22, 0.7, 0.28, 1)` — quick out, soft landing |

No bouncing, no springs. Overshoot would contradict the material.

## 8. Behaviour under stress

- Long titles clamp to two lines with an ellipsis; the full text is the tooltip.
- Empty columns state so in muted italics rather than collapsing.
- `prefers-reduced-transparency` → opaque surfaces, blur removed.
- No `backdrop-filter` support → solid tint at equivalent contrast.
- `prefers-reduced-motion` → all animation removed, no layout change.
- Text never sits directly on the ground; every text-bearing element has a
  surface beneath it with a minimum fill, so a bright future background cannot
  destroy contrast.

## 9. Fidelity ledger

**Reproduced exactly** — the three inner shadow values from reference B;
monochrome chrome with isolated semantic colour; radius and spacing scale;
tabular numerals; the top-edge highlight.

**Approximated** — refraction (blur substitutes for bending); dispersion (edge
tint substitutes for chromatic split); frost (SVG noise substitutes for a
material grain); typeface (`system-ui` substitutes for a licensed grotesque).

**Deliberately rejected** — the photographic ground is *not* baked in, since
ADR-004 keeps it a single swappable property; reference A's left icon rail,
which has no function in this product yet; its floating assistant button,
because the AI layer is deferred until the deterministic system works
(ADR-001).
