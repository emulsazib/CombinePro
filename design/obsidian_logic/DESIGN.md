---
name: Obsidian Logic
colors:
  surface: '#111317'
  surface-dim: '#111317'
  surface-bright: '#37393e'
  surface-container-lowest: '#0c0e12'
  surface-container-low: '#1a1c20'
  surface-container: '#1e2024'
  surface-container-high: '#282a2e'
  surface-container-highest: '#333539'
  on-surface: '#e2e2e8'
  on-surface-variant: '#b9cbbc'
  inverse-surface: '#e2e2e8'
  inverse-on-surface: '#2f3035'
  outline: '#849587'
  outline-variant: '#3b4b3f'
  surface-tint: '#00e38a'
  primary: '#f3fff3'
  on-primary: '#00391f'
  primary-container: '#00ff9c'
  on-primary-container: '#007142'
  inverse-primary: '#006d40'
  secondary: '#adc6ff'
  on-secondary: '#002e6a'
  secondary-container: '#0566d9'
  on-secondary-container: '#e6ecff'
  tertiary: '#fffaff'
  on-tertiary: '#3b2f00'
  tertiary-container: '#ffdd65'
  on-tertiary-container: '#766000'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#56ffa7'
  primary-fixed-dim: '#00e38a'
  on-primary-fixed: '#002110'
  on-primary-fixed-variant: '#00522f'
  secondary-fixed: '#d8e2ff'
  secondary-fixed-dim: '#adc6ff'
  on-secondary-fixed: '#001a42'
  on-secondary-fixed-variant: '#004395'
  tertiary-fixed: '#ffe17a'
  tertiary-fixed-dim: '#e4c44f'
  on-tertiary-fixed: '#231b00'
  on-tertiary-fixed-variant: '#554500'
  background: '#111317'
  on-background: '#e2e2e8'
  surface-variant: '#333539'
typography:
  h1:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  h2:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
  code-md:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '450'
    lineHeight: 20px
  code-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 16px
  label-caps:
    fontFamily: Inter
    fontSize: 10px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.05em
spacing:
  unit: 4px
  panel-gap: 1px
  sidebar-width: 260px
  gutter: 8px
  container-padding: 12px
---

## Brand & Style
This design system is engineered for deep focus and technical precision, catering to developers and system architects. The brand personality is clinical, efficient, and authoritative. It prioritizes information density and logical grouping over decorative elements.

The aesthetic leans heavily into **High-Density Minimalism** with a **Corporate/Modern** backbone. It utilizes sharp edges, subtle tonal shifts for depth, and high-contrast accents to guide the user through complex workflows. The UI is designed to disappear, keeping the user's code and data at the forefront of the experience.

## Colors
The palette is built on a "Deep Dark" foundation to reduce eye strain during long sessions. 

- **Primary (Terminal Green):** Reserved for high-priority actions, success states, and the primary "Execution" flow.
- **Secondary (Logic Blue):** Used for selection states, focus indicators, and active links.
- **Neutral (Grayscale):** A range of obsidian and slate tones are used to create structural hierarchy without relying on shadows.
- **Semantic Accents:** Immediate visual feedback for agent states (Running, Idle, Error) ensures system status is glanceable.

## Typography
Typography is divided between functional UI navigation and data consumption. 

- **Inter** is the primary workhorse for the interface, providing high legibility at small sizes. 
- **JetBrains Mono** is utilized for all code blocks, logs, terminal outputs, and metadata labels to maintain a technical "Developer" feel.
- **Scale:** Font sizes are intentionally small to allow for maximum data density (13px for code is the default).

## Layout & Spacing
The layout follows a **Fixed-Grid / Modular** approach inspired by IDEs. The primary structure relies on `1px` borders (gutters) rather than whitespace to separate functional zones.

- **Panels:** Use a flexible splitter system (QSplitter style). Minimum panel width is 40px (collapsed) to 260px (standard).
- **Density:** Padding is tight. Standard button padding is `4px 12px`. List items use a `24px` fixed height.
- **Breakpoints:** This system is optimized for Desktop use. Tablet and Mobile views reflow into a single-column stacked view with hidden sidebars accessible via a drawer.

## Elevation & Depth
This design system avoids traditional drop shadows to maintain a "flat but layered" look. 

- **Tonal Layering:** Depth is communicated by color. Backgrounds get lighter as they move "closer" to the user. (Obsidian for main editor → Charcoal for sidebars → Slate for floating tooltips).
- **Active States:** Focus is indicated by a `1px` solid border of the Secondary color or a subtle inner-glow.
- **Borders:** Every panel is separated by a 1px solid border (`#2D333B`).

## Shapes
The shape language is strictly **Sharp (0px)**. All containers, buttons, and input fields feature 90-degree corners to emphasize the technical, structural nature of the tool.

The only exception is for status indicators (dots) or specific toggle switches which may use a circular form to differentiate from actionable UI buttons.

## Components
- **Buttons:** Sharp corners. Primary buttons use the Terminal Green background with black text. Ghost buttons use a 1px border.
- **Tree Views:** High-density, 16px indent per level. Use chevron-down/right for folder states. Active files get a Logic Blue left-accent bar (2px).
- **Tabs:** "Folder-ear" style or underline style. Active tabs have a top-border of Logic Blue.
- **Input Fields:** Obsidian background with a Slate border. On focus, the border changes to Logic Blue. Use Monospace font for input.
- **Chips/Badges:** Small, caps-heavy text. Backgrounds reflect the "Agent States" (e.g., a green glowing dot for 'Running').
- **QSplitter Panels:** 1px resize handles that change color to Logic Blue on hover.