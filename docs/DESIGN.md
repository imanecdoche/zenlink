# PhoneLink design system

A tool, not a showcase. The picture from the phone is the product; the chrome
around it stays quiet, dense and predictable, like OBS or a Windows 11 system
utility. No gradients, glows, emoji, glass blur or decorative illustration.

## Tokens

All values live as CSS custom properties in `ui/styles.css` (`:root` for dark,
`[data-theme="light"]` for light).

### Color

| Token | Dark | Light | Use |
|---|---|---|---|
| `--bg-app` | `#0f1012` | `#f3f4f6` | Window background |
| `--bg-panel` | `#16171a` | `#ffffff` | Sidebar, status bar |
| `--bg-raised` | `#1d1e22` | `#ffffff` | Controls, list rows on hover |
| `--bg-stage` | `#000000` | `#0f1012` | Behind the cast picture (always dark) |
| `--border` | `#26282d` | `#e2e4e8` | Dividers, control outlines |
| `--border-strong` | `#34373d` | `#cfd2d8` | Focused/hovered outlines |
| `--text` | `#e8e9eb` | `#15171b` | Primary text |
| `--text-2` | `#a2a6ad` | `#555a63` | Secondary text, labels |
| `--text-3` | `#6d7179` | `#868b94` | Hints, disabled |
| `--accent` | `#4a8bff` | `#2563eb` | Primary action, selection, focus ring |
| `--accent-text` | `#ffffff` | `#ffffff` | Text on accent |
| `--ok` | `#3fb27f` | `#16855a` | Live / ready |
| `--warn` | `#d9a441` | `#a86b00` | Needs attention |
| `--bad` | `#e5534b` | `#c4302b` | Errors, stop |

Status is never color-only: every dot has a text label next to it.

### Type

- Family: `"Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif`
- Numbers (metrics): `"Cascadia Mono", Consolas, monospace` with `tabular-nums`
- Scale: 11 (meta), 12 (labels), 13 (body, default), 15 (section titles), 20 (empty-state title)
- Weights: 400 body, 600 titles and buttons. Nothing heavier.

### Spacing, radius, elevation, motion

- Spacing scale (4 px base): 4, 8, 12, 16, 24, 32
- Radius: 4 controls, 6 rows and cards, 8 dialogs
- Elevation: flat surfaces separated by borders; only dialogs get
  `0 12px 32px rgba(0,0,0,.4)`
- Motion: 120 ms ease-out for hover/press; no motion on the cast picture

## Layout

```
┌─────────────┬──────────────────────────────────────────┐
│ Sources     │ Stage header: device · Start/Stop · ...  │
│  USB device │                                          │
│  …          │            cast picture / setup          │
│             │                                          │
├─────────────┴──────────────────────────────────────────┤
│ Status bar: state · 1206×2622 · 60 fps · 18 ms · audio │
└────────────────────────────────────────────────────────┘
```

- Sidebar 248 px, collapses below 720 px window width.
- The picture keeps its aspect ratio, centered on `--bg-stage`.

## Components

**Button**: `primary` (accent fill) for the one main action on screen,
`secondary` (raised fill + border) for the rest, `ghost` for icon buttons.
Height 28 px, padding 0 12 px, radius 4. States: hover lightens fill 6 %,
active darkens, disabled uses `--text-3` and no pointer. Focus ring is
2 px `--accent` with 2 px offset.

**Device row**: 40 px tall, status dot + name + one-line state. Selected row
gets `--bg-raised` and a 2 px accent bar on the left.

**Checklist (USB setup)**: numbered steps; each is `todo`, `current` or `done`.
Only the current step shows its action button.

**Metric**: label in `--text-3` 11 px, value in mono 12 px. Unknown values show
an en dash, never a fake zero.

**Toast**: bottom-right, panel background, border, 6 px radius, auto-dismiss 5 s,
errors stay until dismissed.

## Copy

Plain and specific: say what happened and what to do next ("Unlock the iPad
to start casting"), sentence case, no exclamation marks.
