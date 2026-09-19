### v0.app front-end specifications

Build a frontend for "hub platform" — a personal platform to capture, organize, and triage project ideas, from small to big, where ideas can be parked, held, or graduated into standalone builds. Full spec below.

[link text](./specs.md)

Requirements:

- Use React with Vite, Tailwind, and shadcn/ui. Do NOT use Next.js — this is a standalone SPA that will be exported and built out separately.
- Centralize every backend call in a single services/api layer, with a mock implementation (in-memory, using the seed projects from the spec) so the whole app runs with no real backend. All components import from this layer, never call fetch directly.
- Make it interactive: I should be able to use the main features from the spec (dashboard with filter/sort, quick capture, project detail with editing, notes, status changes).
- Design: beautiful, sleek, minimalist, simple by default. Responsive for phone and desktop.
- Seed the mock data with the project list from the spec so the dashboard isn't empty on first load.

### For Claude to complete V0.app's work

There is a hub-platform-frontend.zip file in the base project folder. First, extract it so its contents are in the project root (it unzips to loose files: package.json, src/, components/, services/, etc.). This is a Vite + React + TypeScript frontend that was started in v0 and left incomplete.

  Read the spec at _docs/specs.md first for the full context. Then:

  1. Get it running: pnpm install then pnpm dev. Fix any install or build errors (dependencies are React 19 / Tailwind v4 / @base-ui, watch for version issues).
  2. There's a missing file: App.tsx imports pages/project-detail.tsx which doesn't exist. Build that project-detail page to match the spec (all fields editable, status, scores, notes log, links, next action shown at top), using the existing components and the services/api layer.
  3. Clean up leftover v0/Next.js cruft: fix components.json (rsc should be false, css path is wrong), remove unused public/ placeholder files.
  4. Confirm the whole app runs against the mock API with the seeded projects showing on the dashboard, and every data call goes through services/api, never direct fetch.

  Don't restructure what's already working. The services/api mock layer and the existing components are good, build on them.

### Refining the frontend

Do a read-only review of this codebase and report your findings without changing any files yet. Cover:

Correctness: run pnpm build and tsc and report any type errors or build warnings. Check for any runtime errors in the components.
Consistency: look for inconsistencies in naming, formatting, casing of user-visible text, component patterns, and how data flows through the store and services/api layer. Flag anything that deviates from the patterns used elsewhere.
Dead code and cruft: unused imports, unused components, leftover v0/Next.js artifacts, unreferenced files, commented-out blocks.
Spec alignment: compare the app against _docs/specs.md and note anything missing, incomplete, or diverging from the spec.
Anything risky or fragile you'd want to fix before building further.

Give me a categorized list, ordered by severity, with the file and line for each item. Don't fix anything yet, I want to review the list and decide what to act on.

### Clean-up pass 1

This is batch one of a cleanup pass, from the review you did earlier. Work only on the items below, then stop. Don't touch anything not listed here.

1. Set up ESLint + Prettier for this Vite + React 19 + TypeScript project, using current standard configs for this stack. Add the config files, add the needed devDependencies, and add lint and format scripts to package.json. Configure them to agree with the existing code style (2-space indent, single quotes, no semicolons, as the codebase already uses) so this doesn't reformat everything into a huge diff. Run the linter and report what it finds, but only auto-fix formatting/style, do not make behavioral changes.

2. Remove dead code (from the review):

- components/ui/badge.tsx (Badge, never used)
- components/score-meter.tsx (ScoreMeter export, never rendered, but ScorePicker in the same file IS used, keep ScorePicker)
- lib/project-utils.ts isActionable (never called)
- the "hooks": "@/hooks" alias in components.json (points at a non-existent dir)
- Do NOT remove components/ui/card.tsx, I'm keeping it for a later consistency fix.
- Before removing each item, grep to confirm it's truly unreferenced. If anything is actually used, leave it and tell me.

3. Add a favicon. The public/ folder was removed earlier so the tab has no icon. Add a simple favicon (an SVG favicon is fine) and reference it in index.html. Keep it minimal and theme-neutral.

When done: run pnpm build and tsc to confirm everything still passes, run the new linter to confirm it's clean, and give me a short summary of what changed. Don't commit, I'll review and commit myself.