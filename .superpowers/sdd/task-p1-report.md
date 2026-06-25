## Summary

Completed Phase 1 design token upgrade for WMSRAGV2 frontend. The existing blue-gray (slate) palette has been replaced with a warm, neutral palette centered on `#FAF9F7` paper background, `#2C241E` sidebar, and `#C75B2A` accent orange. Fonts updated from Inter to Plus Jakarta Sans with Space Grotesk for headings. CSS custom properties introduced for all tokens (colors, shadows, radii, easing functions) to enable runtime theme consistency.

## Modified Files

1. **`frontend/vue-app/index.html`** — Replaced Google Fonts CDN links: swapped Inter for Plus Jakarta Sans, added JetBrains Mono weight variants, updated Space Grotesk weights.

2. **`frontend/vue-app/tailwind.config.js`** — Replaced theme section with new warm palette colors (paper, sidebar, primary, secondary, tertiary, accent-orange, accent-gold, accent-green, danger), new font families (display, body, mono), complete borderRadius scale, boxShadow scale (sm, card, raised, modal, glow), and custom easing functions (spring, out-expo, in-out).

3. **`frontend/vue-app/src/style.css`** — Replaced entirely. Now defines CSS custom properties on `:root` for all design tokens, uses `var()` references in global body styles, introduces refined animations (pulse-dot, fade-in, fade-up, shimmer), updated scrollbar styling, updated sidebar-texture with `::after` pseudo-element approach, and hairline utility classes referencing `--color-grid`.

4. **`frontend/vue-app/src/App.vue`** — No changes needed. The root `<div>` had no old `bg-`/`text-` classes to replace. The `<main>` element already used `bg-paper` (will resolve to new warm value from updated config automatically).

## Design Notes

- **Color rationale**: The shift from slate-50 (#F8FAFC) to paper (#FAF9F7) and from navy sidebar (#1E293B) to warm dark brown (#2C241E) creates a warmer, more tactile feel appropriate for a warehouse management system.
- **CSS Variables**: All tokens are available both as Tailwind utility classes and as CSS custom properties, giving component authors two paths to consistency.
- **Animation tokens**: Custom easing functions (spring, out-expo) added for future interaction design use.
- **Semantic naming**: Color tokens named by function (paper, surface, primary, secondary, tertiary, danger) rather than by raw hue, making theme swaps easier.

## Tests

`npm run build` — **PASSED** (1.58s, 149 modules, no errors). Only pre-existing warning about `INEFFECTIVE_DYNAMIC_IMPORT` in knowledge store, unrelated to this change.

## Risks

- Components referencing old color tokens (e.g., `accent-orange` was `#EA580C` now `#C75B2A`, `accent-green` was `#059669` now `#3D7A6E`) will visually shift. These are intentional redesign choices.
- Old font family tokens (`font-sans`, `font-space`) are no longer in config. Components using `font-sans` will fall back to Tailwind's default sans stack. Components using `font-space` will need migration to `font-display`.
- The old `borderWidth.hairline` token is removed; components using `border-hairline` will fall back to default `border`. The `.hairline-b` etc. CSS utilities still work via CSS variables.
- The old `.hairline` class (all sides) was removed — only directional variants (.hairline-b, .hairline-t, .hairline-r) remain.

## Tech Debt

- Existing components may reference the old `font-sans` and `font-space` Tailwind classes. Audit needed in a later phase to migrate to `font-body` and `font-display`.
- The `sidebar-texture` approach changed from `background-image` on the element to a `::after` pseudo-element — any component overriding `sidebar-texture` positioning may need adjustment.
- `.hairline` (all sides) removed — if any component used it, needs migration to directional variants.
