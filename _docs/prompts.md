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