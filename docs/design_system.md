---
name: Integrated Intelligence
colors:
  surface: '#faf9fd'
  surface-dim: '#dbd9dd'
  surface-bright: '#faf9fd'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f4f3f7'
  surface-container: '#efedf1'
  surface-container-high: '#e9e7eb'
  surface-container-highest: '#e3e2e6'
  on-surface: '#1a1b1e'
  on-surface-variant: '#424753'
  inverse-surface: '#2f3033'
  inverse-on-surface: '#f1f0f4'
  outline: '#727785'
  outline-variant: '#c2c6d5'
  surface-tint: '#005ac1'
  primary: '#0058bd'
  on-primary: '#ffffff'
  primary-container: '#2771df'
  on-primary-container: '#fefcff'
  inverse-primary: '#adc6ff'
  secondary: '#006a61'
  on-secondary: '#ffffff'
  secondary-container: '#7af4e3'
  on-secondary-container: '#006f65'
  tertiary: '#0058bb'
  on-tertiary: '#ffffff'
  tertiary-container: '#1471e6'
  on-tertiary-container: '#fefcff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d8e2ff'
  primary-fixed-dim: '#adc6ff'
  on-primary-fixed: '#001a41'
  on-primary-fixed-variant: '#004494'
  secondary-fixed: '#7df6e6'
  secondary-fixed-dim: '#5edaca'
  on-secondary-fixed: '#00201c'
  on-secondary-fixed-variant: '#005049'
  tertiary-fixed: '#d8e2ff'
  tertiary-fixed-dim: '#adc7ff'
  on-tertiary-fixed: '#001a41'
  on-tertiary-fixed-variant: '#004493'
  background: '#faf9fd'
  on-background: '#1a1b1e'
  surface-variant: '#e3e2e6'
typography:
  display-lg:
    fontFamily: DM Sans
    fontSize: 28px
    fontWeight: '500'
    lineHeight: 36px
    letterSpacing: -0.5px
  headline-md:
    fontFamily: DM Sans
    fontSize: 22px
    fontWeight: '500'
    lineHeight: 28px
  title-lg:
    fontFamily: DM Sans
    fontSize: 18px
    fontWeight: '500'
    lineHeight: 24px
  body-lg:
    fontFamily: DM Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: DM Sans
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: DM Sans
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.5px
  label-sm:
    fontFamily: DM Sans
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 16px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  container-margin: 16px
  gutter: 12px
  sheet-top-padding: 24px
  element-gap-sm: 8px
  element-gap-md: 16px
  bottom-nav-height: 80px
---

## Brand & Style

This design system shifts away from a rigid, clinical instrument aesthetic toward an **Integrated & Adaptive** mobile experience. It prioritizes fluid utility and organic layering, drawing inspiration from high-utility Google interfaces (Maps/Gemini). 

The style is defined by **Soft Modernism**:
- **Layered Sheet Architecture:** Content lives on expansive, rounded sheets that physically "dock" at the bottom of the viewport, grounding the user.
- **Ambient Utility:** The UI feels like an overlay on the real world (via maps), using floating elements to maintain a sense of lightness and transparency.
- **Dynamic Adaptability:** Transitions between light map-centric views and deep-black intelligence components (Gemini-style) are seamless, using shared border-radius and iconography styles to maintain cohesion.
- **Approachability:** Friendly, rounded shapes and a balanced color palette evoke reliability and ease of use for high-frequency interaction.

## Colors

The palette is anchored by a flagship **Google Blue (#4285F4)**, used for primary actions and brand presence. 

- **Primary & Secondary:** The blue is supported by a vibrant teal and a deeper utilitarian blue for interactive states.
- **Dark Mode / AI States:** For deep-intelligence features, the system switches to a "True Black" (#000000) background with "Off-Black" (#1E1F20) containers to create depth without losing the premium feel.
- **Semantic Colors:** Traffic light colors (Red/Yellow/Green) are tuned to be highly saturated and "clean," ensuring high legibility on both light map tiles and dark sheets.
- **Neutrals:** Uses a scale of cool greys for secondary text, while headers use a near-black (#202124) for maximum contrast on white sheets.

## Typography

Typography is clean, modern, and highly legible, utilizing **DM Sans** across all levels to ensure a consistent, friendly voice.

- **Headlines:** Use Medium weights (500) with tighter letter spacing for a compact, professional look in bottom sheets.
- **Body Text:** Standardized on 16px and 14px for maximum readability. 
- **Labels:** Used for navigation and category pills; these use a slightly increased letter spacing and a "Semi-Bold" optical feel (500 weight) to stand out at small scales.
- **Mobile Hierarchy:** Sizes are capped at 28px for "Display" styles to ensure headlines never wrap excessively on standard mobile devices.

## Layout & Spacing

The layout is a **Sheet-Based Mobile System** that prioritizes thumb-reachability and clarity.

- **Floating UI:** Search bars and category filters float above the map with a 16px margin from the screen edges.
- **The Bottom Sheet:** This is the primary content container. It features a minimum 28px top corner radius. When pulled up, it maintains a 16px side margin or can snap to full-width depending on the context.
- **Rhythm:** An 8px base grid is used. Elements within cards or lists are typically separated by 12px or 16px to maintain a spacious, "uncluttered" feel.
- **Safe Areas:** Significant bottom padding is reserved for the navigation bar (80px), ensuring content is never obscured by the system's home indicator.

## Elevation & Depth

Visual hierarchy is managed through **Tonal Sheets** and **Floating Elevation**:

- **Level 0 (Map):** The base layer.
- **Level 1 (Floating Elements):** Search bars and pill buttons use a subtle "Ambient Shadow"—a soft, 4-8px blur with very low opacity (10-15%) to appear as if hovering just above the map.
- **Level 2 (The Sheet):** The main content sheet uses a slightly higher elevation or is differentiated by its sheer white surface against the map.
- **Level 3 (Overlays/Modals):** Gemini-style dark containers use a subtle 1px border (#3C4043) instead of heavy shadows to define edges against pure black backgrounds.
- **Interactions:** When an element is pressed, it does not "lift"; instead, a subtle grey or colored fill (State Overlay) appears.

## Shapes

The shape language is dominated by **Extremely Rounded & Pill-Shaped** geometries.

- **Bottom Sheets:** Top corners have a `28px` radius to feel soft and integrated.
- **Buttons & Chips:** All primary buttons and category filters are "Pill-shaped" (Full Radius), promoting a friendly and touchable interface.
- **Containers:** Internal cards (e.g., contribution tasks) use a `16px` radius (`rounded-lg`).
- **Active Indicators:** Navigation bar active states use a "Pill" background behind the icon, signaling the current selection with a soft, rounded shape.

## Components

- **Floating Search Bar:** A white, rounded-rect container (24px radius) with a 16px margin. It includes a brand-colored logo, text prompt, and profile avatar.
- **Pill Category Buttons:** Horizontal scrolling list of buttons. White background, 1px light border, with a leading icon. 
- **Bottom Navigation:** A clean bar with a subtle top border. Active states are indicated by a colored pill-shaped background behind the icon (e.g., Light Blue background for a Blue icon).
- **Content Sheets:** Feature a "Handle" (Drag Indicator) at the top—a small, grey rounded bar.
- **Gemini-Style Quick Actions:** For intelligence features, use large, dark-grey square-ish cards with a high border radius (24px) and thin, outlined icons.
- **Progress Bars:** Thin, rounded tracks with a vibrant primary color fill and a small "dot" indicator at the current progress point.
- **List Items:** Simple, clean rows with a 40x40px rounded-rect icon container (light grey background) on the left.
