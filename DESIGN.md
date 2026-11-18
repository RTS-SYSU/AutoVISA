---
name: autoRTA Research Workbench Prototype
description: Source-linked research surfaces with clear actions and inspectable decisions.
colors:
  ink: "#19283f"
  muted: "#637187"
  line: "#dce3ed"
  canvas: "#f5f7fb"
  paper: "#fff"
  rail: "#edf1f8"
  blue: "#2945af"
  blue-soft: "#e8edff"
  teal: "#14675b"
  teal-soft: "#e8f5ef"
  amber: "#855616"
  amber-soft: "#fff4dd"
  red: "#a33535"
typography:
  body:
    fontFamily: '"Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
  control:
    fontFamily: '"Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif'
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.6
  label:
    fontFamily: '"Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif'
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.6
  formula:
    fontFamily: 'Cambria, "Times New Roman", serif'
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.6
rounded:
  badge: "6px"
  icon: "7px"
  field: "8px"
  control: "9px"
  node: "11px"
  panel: "12px"
  feature: "14px"
  dialog: "16px"
spacing:
  compact: "8px"
  content: "12px"
  standard: "16px"
  section: "24px"
  page: "32px"
components:
  button-primary:
    backgroundColor: "{colors.blue}"
    textColor: "{colors.paper}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "8px 16px"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "8px 16px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "8px 16px"
  text-button:
    backgroundColor: "transparent"
    textColor: "{colors.blue}"
    typography: "{typography.label}"
    padding: "2px 0"
  icon-button:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.icon}"
    width: "34px"
    height: "34px"
  input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    padding: "10px 12px"
  navigation:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.blue}"
    rounded: "{rounded.control}"
    padding: "11px 13px"
  badge:
    backgroundColor: "{colors.teal-soft}"
    textColor: "{colors.teal}"
    typography: "{typography.label}"
    rounded: "{rounded.badge}"
    padding: "3px 9px"
  inspector:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
  derivation-node:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.node}"
    padding: "13px 14px"
---

# Design System: autoRTA Research Workbench Prototype

## Overview

**Creative North Star: "Research Workbench"**

Cool white work surfaces, a pale blue navigation rail, and restrained state colors support reading source material and inspecting mathematical decisions. Concise Chinese labels and nearby actions keep the work approachable.

This record covers only the clickable prototype in `web/prototype.html`, `web/prototype.css`, and `web/prototype.js`. It does not define the legacy application's design system. Tokens describe the implemented artifact; the confirmed direction is recorded in `docs/prototype-direction.md`.

**Key Characteristics:**

- Quiet navigation and clearly ranked actions.
- White, bordered work surfaces with restrained depth.
- Source-linked content and inspectable reasoning nodes.
- Color states accompanied by readable labels.

## Colors

Ink and cool neutrals carry the reading surface; blue actions, teal confirmations, and amber decisions provide the semantic accents.

### Primary

- **Ink Blue** (`blue`): primary actions, active tabs, selected nodes, and source links.
- **Pale Blue** (`blue-soft`): informative badges and counts.

### Secondary

- **Confirmed Teal** (`teal`, `teal-soft`): reviewed input, confirmation badges, and progress.
- **Decision Amber** (`amber`, `amber-soft`): scope choices and unresolved decisions.
- **Error Red** (`red`): form validation messages.

### Neutral

- **Reading Ink / Muted Slate** (`ink`, `muted`): main content and supporting information.
- **Canvas / Paper / Rail** (`canvas`, `paper`, `rail`): page, work surface, and navigation backgrounds.
- **Divider** (`line`): panel outlines and separators.

**The Labeled State Rule.** Pair status color with words; confirmation of input must not visually imply a checked proof.

## Typography

**Body Font:** Segoe UI, Microsoft YaHei UI, Microsoft YaHei, sans-serif.  
**Label/Mono Font:** The body stack for labels; Consolas, monospace for code-like values.  
**Formula Font:** Cambria, Times New Roman, serif.

Body text uses a compact reading scale (14px, line-height 1.6); controls use semibold weight, and labels use 12px. Content fields retain 14px text with line-height 1.7; inspector explanations use 13px with line-height 1.8. Formula text drops to 16px between 1181px and 1370px.

Observed headings are 29px on standard pages, 24px in the workbench, and 19px for general sections; individual functional sections use 15–16px. These are contextual sizes rather than a fixed modular ratio. **Not canonized:** headings currently inherit the system body font. No display-font token is established by this prototype, and that limitation should not become a rule for future display typography.

## Layout

The desktop shell has a 208px navigation rail and a fluid main column. The top bar is 66px tall; page content is capped at 1540px with 32px padding. The workbench uses 24px padding and a graph plus 288px inspector, reduced to 260px at intermediate desktop widths.

Panels commonly use 16–20px gaps. Review places source and editable interpretation side by side; its viewport adapts to laptop height using `clamp(260px, calc(100dvh - 430px), 480px)`. These page arrangements are prototype-specific, not requirements for every future screen.

At 1180px the rail narrows to 178px and the inspector moves below the graph. At 900px the rail becomes 74px with icon navigation. At 680px navigation becomes a top row, content stacks, page padding becomes 23px 16px, and the review action bar becomes sticky. Graph content remains scrollable with a list-view alternative. At 1450px the graph viewport grows to 510px.

## Elevation & Depth

White surfaces and fine borders provide most separation. Small shadows identify active navigation, selected nodes, document paper, and the mobile review footer. Dialogs use the strongest soft shadow (`0 18px 60px #16233c24`) and a translucent, blurred backdrop. The sidecar records the full shadow vocabulary.

**The Bordered Surface Rule.** Use borders and tonal separation for ordinary work panels; reserve stronger depth for overlays and lifted document material.

## Shapes

Controls have gently rounded corners, with smaller badge and icon radii and broader panel and dialog corners. Pills are not the default. Dots, avatars, and step counters remain circular. The graph uses rounded rectangular nodes, thin directional connectors, and dashed lines for unresolved links. Authored inline SVG line icons share rounded caps and joins.

## Components

### Buttons

Primary buttons pair ink blue with white text; secondary buttons use white and a fine border; quiet buttons remove the visible border and use muted text. Standard controls have a 40px minimum height and compact variants 32px. Hover changes background and border over 160ms. Text actions underline on hover; icon buttons use a quiet tinted hover surface.

Keyboard focus is a 3px blue outline with 3px offset. Disabled buttons retain their shape with opacity 0.48 and an unavailable cursor. Reduced-motion preference removes transitions and animation.

### Chips

Small rectangular status badges use a 6px radius and semibold labels. Teal, amber, and blue variants communicate confirmation, decisions, and information. Badges do not act as buttons.

### Cards / Containers

Document, review, graph, and inspector panels share white backgrounds, fine borders, and 12px corners. Toolbars separate content with a divider. Larger continuation panels use 14px corners. Inspector headers use 16px 18px padding; their bodies use 18px.

### Inputs / Fields

Text inputs and textareas use white fill, a fine cool border, 8px corners, and 10px 12px padding. Visible labels precede the field; errors are readable red text. Textareas resize vertically. Fields share the keyboard focus outline.

### Navigation

The navigation rail uses muted labels and inline SVG icons. Active destinations become white with blue text and a subtle shadow; hover uses a pale tinted background. Responsive changes preserve text labels on the narrow-screen top navigation.

### Derivation Nodes

A selected node gains a 2px blue border and compensating padding, preserving its outer dimensions. Each node keeps a status line, title, and hint. Decision nodes use pale amber; selection is separate from confirmation. Selecting a node updates the adjacent inspector. Source-linked review fields expose source, edit, and confirmation actions.

## Do's and Don'ts

### Do:

- **Do** keep primary actions beside the work they advance.
- **Do** retain readable status labels alongside color.
- **Do** preserve visible keyboard focus and reduced-motion behavior.
- **Do** keep source references and decision consequences accessible.

### Don't:

- **Don't** present demonstration states as real proof-check evidence.
- **Don't** replace source content with decorative metrics.
- **Don't** flatten confirmation, selection, and pending decisions into one visual state.

