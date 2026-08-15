# ADR-004 — Frosted-glass UI over a swappable background

**Status:** ACCEPTED
**Date:** 2026-08-15 — visual direction supplied by the stakeholder as reference images
**Related:** D-005, BR-002, BR-021

---

## Context

The stakeholder supplied three reference images: a kanban-style application with
dark translucent panels floating over a photographic background, and two "liquid
glass" studies showing the technique — layered inner shadows on a translucent
surface, plus blur and frost.

They also stated: **the background will be chosen later.**

That last point is the actual architectural requirement hiding inside a visual
one. A design where the background is decided late must not have that decision
smeared across dozens of components.

---

## Decision

**Build the interface as translucent surfaces over a single background layer
controlled by one CSS custom property.**

```css
--app-background: <chosen later>;   /* image, gradient, or solid */
```

Everything else reads from a small token set and never references the background
directly.

### The glass recipe

Derived from the reference images, expressed as tokens so it stays consistent:

| Token | Purpose |
|---|---|
| `--glass-bg` | Surface tint — a translucent dark or light wash |
| `--glass-blur` | `backdrop-filter: blur()` radius |
| `--glass-border` | Hairline edge, brighter than the fill |
| `--glass-inner-top` | Inner shadow, light from above — the top bevel |
| `--glass-inner-bottom` | Inner shadow, opposing — the bottom bevel |
| `--glass-inner-glow` | Soft inner spread — the frost |
| `--glass-shadow` | Outer drop shadow, lifting the panel off the background |

The reference tutorial's three inner shadows map directly onto the three
`--glass-inner-*` tokens. Using `inset` box-shadows rather than images means the
effect scales, recolours, and costs nothing to load.

### Three rules that keep it usable

Frosted glass is a legibility risk, and this product's core job is reading
information quickly. Three constraints apply:

1. **Text never sits directly on the background.** Every text-bearing element sits
   on a glass surface with a defined minimum opacity, so contrast is guaranteed
   regardless of which background is eventually chosen.
2. **Blur is decoration, never information.** The state of a work item is carried
   by text, shape and semantic colour — never by translucency alone. A viewer with
   `backdrop-filter` unsupported, or reduced transparency enabled, must lose
   beauty and nothing else.
3. **Semantic colour is separate from the glass palette.** At risk, stalled,
   blocked and overloaded are meaning, and must read against any background.

### Accessibility fallback

```css
@media (prefers-reduced-transparency: reduce) {
  /* opaque surfaces, blur removed */
}
```

`backdrop-filter` is also feature-detected; where it is missing, surfaces fall back
to a solid tint at the same contrast.

---

## Options considered

**A — Glass effects written per component.** Fastest for one screen; guarantees
divergence by the fifth. Changing the background later would mean touching every
component. Rejected.

**B — Token set with a single background layer *(chosen)*.** One place to change
the background, one place to tune the glass. Costs an hour of setup.

**C — A component library themed to look like glass.** Heavier dependency,
and the reference look is specific enough that most of it would be overridden
anyway. Rejected for a first vertical slice.

---

## Consequences

**Positive**

- The background decision stays genuinely deferred — one property, changed once.
- The look stays consistent because it is defined once, not re-derived per screen.
- Reduced-transparency and unsupported-browser paths are handled by construction.

**Negative**

- `backdrop-filter` is GPU-work; many large blurred surfaces on a low-end laptop
  can cost frames. Mitigation: blur the panels, not every small element.
- Translucency reduces contrast by nature. The minimum-opacity rule is what keeps
  this the right side of legible, and it constrains how transparent the design can
  become.

**Neutral**

- Dark and light variants are both supported through the same tokens; the eventual
  background choice may effectively settle which one is primary.
