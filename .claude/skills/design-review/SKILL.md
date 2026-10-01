---
name: design-review
description: Audit current UI/UX against best practices; review component library, layout efficiency, and data presentation; research emerging tools; recommend improvements
---

# Design Review

Perform a comprehensive audit of the user interface and design system. Validate the current state against modern best practices, evaluate component choices, identify layout and data visualization inefficiencies, research emerging tools, and propose targeted improvements.

## When to run

- Quarterly (standing audit of design freshness)
- On demand when evaluating new features
- When considering UI framework or tool upgrades
- After shipping a major feature (to review design execution)

## Prerequisites

- Frontend dev server running: `pnpm dev` from `frontend/`
- Time to thoroughly evaluate the app (30-60 minutes recommended)
- Access to design research tools (Figma, design systems, articles)
- Current stack knowledge: Vite 6, React 19, Tailwind 4.3, shadcn/ui (base-nova), @base-ui/react 1.5

## Steps

### 1. Review current UI/UX against modern standards

Open the app and evaluate:

**Visual hierarchy:**
- Are headings, labels, and data clearly differentiated in size and weight?
- Is there a consistent depth/spacing system (Tailwind spacing scale)?
- Do buttons and interactive elements stand out sufficiently?

**Navigation:**
- Is the information architecture intuitive? (sidebar, breadcrumbs, navigation flow)
- Can users easily get back (browser back, explicit back button)?
- Are there any "lost" states where users don't know where they are?

**Forms and input:**
- Are form fields clearly labeled with visible help text?
- Are validation errors prominent and actionable?
- Are required fields marked clearly?
- Is there visual feedback on focus, hover, and submission?

**Data presentation:**
- Tables: are columns sortable, filterable, scannable? Are dense tables overwhelming?
- Lists: are items easy to scan? Do they have enough visual separation?
- Empty states: are they helpful and not just blank?
- Modals/dialogs: are they appropriately sized, not overwhelming the page?

**Accessibility:**
- Are buttons and interactive elements keyboard-accessible?
- Are colors sufficient contrast for WCAG AA (text ≥ 4.5:1)?
- Are form labels associated with inputs?
- Are interactive elements properly announced to screen readers?

**Responsive design:**
- Does the layout work on mobile, tablet, and desktop?
- Is text readable on small screens (font size, line length)?
- Are touch targets >= 44x44 pixels on mobile?
- Do modals/sidebars adapt to mobile (don't push content off-screen)?

Report findings in each area: ✓ (good), ⚠ (needs review), or ✗ (problem).

### 2. Evaluate the component library

Review the current stack:

**Tailwind 4.3:**
- Are tokens (colors, spacing, typography) used consistently?
- Are custom components extending Tailwind, or is raw CSS mixing in?
- Are animations/transitions using tw-animate-css effectively?

Report: Do tokens cover the current design needs, or are hard-coded colors creeping in?

**shadcn/ui (base-nova style):**
- Are components visually cohesive? (base-nova is the style choice)
- Are all needed components available (buttons, forms, dialogs, dropdowns, etc.)?
- Are there missing components that require custom work?

List any custom components not covered by shadcn/ui.

**@base-ui/react 1.5:**
- Are accessible primitives (Dialog, Combobox, etc.) used appropriately?
- Is state management clear (controlled vs. uncontrolled)?

**lucide-react icons:**
- Are icons well-chosen for their actions?
- Is icon sizing consistent across the app?

Report overall: Is the component library meeting the design needs, or are there gaps?

### 3. Review data presentation and layout

Evaluate how data is displayed:

**Interview list / project list:**
- Is the card layout efficient? (is space wasted, or too cramped?)
- Are the most important fields visible at a glance?
- Would a table view be better for certain contexts?
- Are actions (edit, delete, etc.) easily discoverable?

**Interview detail view:**
- Is the information organized logically? (chronology, categories, priority?)
- Is there too much information on one page, or should some be in tabs/collapsibles?
- Are status transitions clear? (can users understand the triage flow?)

**Search and filtering:**
- Are filters easy to find and use?
- Can users clear filters easily?
- Is the search performance acceptable?
- Should results be grouped or sorted differently?

**Empty states:**
- Do they explain what to do next, or just say "no results"?
- Do they include helpful actions (create new project, etc.)?

Report findings: What layout or data organization improvements would reduce cognitive load?

### 4. Research emerging design tools and frameworks

Evaluate alternatives to current stack:

**UI Component libraries:**
- shadcn/ui alternatives: Radix UI (what shadcn is built on), Headless UI, Chakra UI
  - Pros/cons vs. current choice
  - Migration effort if switching
- Tailwind alternatives: UnoCSS, Panda CSS, v0 by Vercel (for rapid prototyping)
  - Do they offer advantages over Tailwind 4?

**Design system tools:**
- Storybook (if not in use): for documenting components and testing UI in isolation
- Chromatic: for visual regression testing
- Design tokens: Token.studio, Figma Tokens (to keep design in sync with code)

**Rapid prototyping / low-code design:**
- Loveable (current): is it still the best fit, or are alternatives worth trying?
  - v0 by Vercel: React component generation from natural language
  - Cursor with Claude: direct code generation
  - UI.joyride: web app builder
- Pros/cons: speed vs. customization, cost, learning curve

**Data visualization:**
- Recharts (not currently used): lightweight charting if data viz is added later
- Plotly, D3: for complex visualizations (heavier)

**Accessibility tools:**
- axe DevTools: automated a11y testing (browser extension)
- WAVE: visual feedback on accessibility issues
- Lighthouse: built into Chrome DevTools

**Performance tools:**
- WebPageTest: detailed performance analysis
- Speedcurve: continuous performance monitoring

Research these and report:
- Which tools could improve the design workflow?
- Which could improve user experience (performance, accessibility)?
- Effort to integrate or switch (low/medium/high)?

### 5. Identify improvement opportunities

Based on the audit, propose specific, actionable improvements:

**Quick wins (low effort, high value):**
- Missing affordances: (e.g., "add a 'copy' button on project ID", "add hover states to list items")
- Layout tweaks: (e.g., "sidebar is too wide on mobile; collapse it by default")
- Accessibility fixes: (e.g., "form labels need better association", "button contrast is below WCAG AA")
- Performance: (e.g., "images should be lazy-loaded", "bundle size is large")

**Medium efforts (worth planning):**
- Component gaps: (e.g., "need a date picker for filtering", "need a multi-select for tagging")
- Layout reorganization: (e.g., "move filters from sidebar to a dedicated panel", "use tabs for project views")
- Data viz: (e.g., "add charts for project status trends", "visualize interview timeline")

**Larger initiatives (future roadmap):**
- Design system formalization (tokens, components, design doc)
- Dark mode support
- Mobile app (if warranted)
- Accessibility audit + WCAG AA compliance initiative
- Performance optimization (code splitting, lazy loading)

Report each improvement with:
- **What**: the specific change
- **Why**: user benefit or design principle it addresses
- **Effort**: estimate (low/medium/high)
- **Priority**: must-have, nice-to-have, or future consideration

### 6. Evaluate tool swap opportunities

If research identified better alternatives, propose swaps:

**Example: Loveable → v0 or Claude Code**
- Current: Loveable for rapid prototyping
- Alternative: v0.dev (React components from text) or direct Claude Code (more control)
- Pros: faster iteration, no vendor lock-in, better IDE integration, cheaper
- Cons: less visual preview, more technical
- Recommendation: [worth trying | stick with current | needs more research]

**Example: Tailwind → UnoCSS**
- Current: Tailwind 4.3
- Alternative: UnoCSS (attribute-based, instant mode)
- Pros: faster build, more flexible
- Cons: smaller community, less documentation
- Recommendation: [not necessary | explore for next major version]

Only propose swaps if there's a clear benefit and the cost is justified.

### 7. Summarize and report

Produce a design audit report:

```
Design Audit Report
===================

Date: <date>
Reviewer: <agent name>

Current Stack:
  - Frontend: React 19 + Vite 6
  - Styling: Tailwind 4.3
  - Components: shadcn/ui (base-nova), @base-ui/react 1.5
  - Icons: lucide-react
  - Prototyping: Loveable

UI/UX Review:
  Visual hierarchy:  [✓ Good | ⚠ Needs work | ✗ Problem]
  Navigation:        [✓ Good | ⚠ Needs work | ✗ Problem]
  Forms & input:     [✓ Good | ⚠ Needs work | ✗ Problem]
  Data presentation: [✓ Good | ⚠ Needs work | ✗ Problem]
  Accessibility:     [✓ Good | ⚠ Needs work | ✗ Problem]
  Responsive design: [✓ Good | ⚠ Needs work | ✗ Problem]

Component Library Assessment:
  Tailwind coverage:    [Sufficient | Needs custom CSS]
  shadcn/ui gaps:       [None | List any missing components]
  Base-ui usage:        [Appropriate | Over/under-utilized]
  Overall cohesion:     [✓ Good | ⚠ Some inconsistency]

Data Presentation Audit:
  Current views:
    - Project list: [card | table] - [efficient | needs redesign]
    - Interview detail: [organized | overwhelming]
    - Search/filters: [discoverable | needs improvement]
  Recommendation: [no changes | targeted tweaks | redesign area X]

Tool Research:
  Emerging alternatives explored:
    - <tool>: <brief assessment>
    - <tool>: <brief assessment>
  Recommendation: [stick with current | worth trying | switch to X]

Quick wins (effort: low, value: high):
  1. <improvement>: [why] → estimated effort: <hours>
  2. <improvement>: [why] → estimated effort: <hours>

Medium efforts (plan for next cycle):
  1. <improvement>: [why] → estimated effort: <hours>
  2. <improvement>: [why] → estimated effort: <hours>

Future roadmap items:
  - <initiative>
  - <initiative>

Overall assessment:
  [✓ Design is solid; incremental improvements sufficient]
  [⚠ Some usability issues; medium refactoring recommended]
  [✗ Design needs significant work before scaling]

Next steps:
  1. <action>
  2. <action>
```

## Reference: Design best practices

When evaluating, use these principles:

- **Clarity**: Users should understand what they can do without ambiguity
- **Consistency**: Repeated patterns (button styles, spacing, color use) build familiarity
- **Feedback**: Actions should have clear visual confirmation (loading states, success messages)
- **Efficiency**: Minimize clicks and cognitive load to achieve common tasks
- **Accessibility**: Design for all users (keyboard, screen readers, color contrast, motion)
- **Responsiveness**: Layouts adapt gracefully to all screen sizes
- **Performance**: Visual design shouldn't compromise load times or responsiveness

## Troubleshooting

**Can't evaluate certain features:**
- If a feature is behind auth, use the demo account (login first)
- If a feature is missing, note it as "not yet implemented" in the audit

**Accessibility testing feels subjective:**
- Use axe DevTools or Lighthouse for objective checks
- Validate contrast ratios at: contrast-ratio.com

**Can't decide on a tool swap:**
- Pros/cons are often context-dependent
- Recommend a trial period or prototype with the new tool
- Involve the human in the decision

**Research feels incomplete:**
- Set a time limit (e.g., 30 min) to stay focused
- Focus on tools most likely to impact your workflow
- Document "defer to next cycle" if research is still ongoing
