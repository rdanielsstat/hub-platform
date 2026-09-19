# Prompts

## v0.app front-end specification

This prompt was given to v0 to scaffold the initial site. It is not part of the Claude Code session.

```
Build a frontend for "hub platform" — a personal platform to capture, organize, and triage project ideas, from small to big, where ideas can be parked, held, or graduated into standalone builds. Full spec below.

[link text](./specs.md)

Requirements:

- Use React with Vite, Tailwind, and shadcn/ui. Do NOT use Next.js — this is a standalone SPA that will be exported and built out separately.
- Centralize every backend call in a single services/api layer, with a mock implementation (in-memory, using the seed projects from the spec) so the whole app runs with no real backend. All components import from this layer, never call fetch directly.
- Make it interactive: I should be able to use the main features from the spec (dashboard with filter/sort, quick capture, project detail with editing, notes, status changes).
- Design: beautiful, sleek, minimalist, simple by default. Responsive for phone and desktop.
- Seed the mock data with the project list from the spec so the dashboard isn't empty on first load.
```

---

## Claude Code prompts

### 1

```
There is a hub-platform-frontend.zip file in the base project folder. First, extract it so its contents are in the project root (it unzips to loose files: package.json, src/, components/, services/, etc.). This is a Vite + React + TypeScript frontend that was started in v0 and left incomplete.

Read the spec at _docs/specs.md first for the full context. Then:

1. Get it running: pnpm install then pnpm dev. Fix any install or build errors (dependencies are React 19 / Tailwind v4 / @base-ui, watch for version issues).
2. There's a missing file: App.tsx imports pages/project-detail.tsx which doesn't exist. Build that project-detail page to match the spec (all fields editable, status, scores, notes log, links, next action shown at top), using the existing components and the services/api layer.
3. Clean up leftover v0/Next.js cruft: fix components.json (rsc should be false, css path is wrong), remove unused public/ placeholder files.
4. Confirm the whole app runs against the mock API with the seeded projects showing on the dashboard, and every data call goes through services/api, never direct fetch.

Don't restructure what's already working. The services/api mock layer and the existing components are good, build on them.
```

### 2

```
find and remove every em dash across the whole project, replacing each with a colon, period, or comma as reads best in context, and check index.html, all components, and pages
```

### 3

```
great, i changed a couple back but mostly left these, it's great. now

In the app header (likely components/layout/app-header.tsx), remove the "h" avatar tile and put a single small filled dot to the left of the "hub" wordmark as an accent mark. Use the existing purple/primary theme token for the dot so it stays theme-aware in light and dark mode. Keep the lowercase "hub" wordmark and the "capture · triage · graduate" tagline. Don't change anything else.
```

### 4

```
In the app header (components/layout/app-header.tsx), remove the accent dot to the left of the wordmark entirely, so there's no mark or tile, just the wordmark and tagline. Change the wordmark from lowercase "hub" to capitalized "Hub". Keep the "capture · triage · graduate" tagline beneath it, and adjust spacing so the text sits cleanly without the dot. Don't change anything else in the header.
```

### 5

```
In the app header (components/layout/app-header.tsx), capitalize the tagline to "Capture · Triage · Graduate" (all three words). Don't change anything else.
```

### 6

```
In the app header (components/layout/app-header.tsx), change the wordmark "Hub" to lowercase "hub" and the tagline to lowercase "capture · triage · graduate". Don't change anything else.
```

### 7

```
Do a read-only review of this codebase and report your findings without changing any files yet. Cover:

Correctness: run pnpm build and tsc and report any type errors or build warnings. Check for any runtime errors in the components.
Consistency: look for inconsistencies in naming, formatting, casing of user-visible text, component patterns, and how data flows through the store and services/api layer. Flag anything that deviates from the patterns used elsewhere.
Dead code and cruft: unused imports, unused components, leftover v0/Next.js artifacts, unreferenced files, commented-out blocks.
Spec alignment: compare the app against _docs/specs.md and note anything missing, incomplete, or diverging from the spec.
Anything risky or fragile you'd want to fix before building further.

Give me a categorized list, ordered by severity, with the file and line for each item. Don't fix anything yet, I want to review the list and decide what to act on.
```

### 8

```
This is batch one of a cleanup pass, from the review you did earlier. Work only on the items below, then stop. Don't touch anything not listed here.

1. Set up ESLint + Prettier for this Vite + React 19 + TypeScript project, using current standard configs for this stack. Add the config files, add the needed devDependencies, and add lint and format scripts to package.json. Configure them to agree with the existing code style (2-space indent, single quotes, no semicolons, as the codebase already uses) so this doesn't reformat everything into a huge diff. Run the linter and report what it finds, but only auto-fix formatting/style, do not make behavioral changes.

2. Remove dead code (from the review):

components/ui/badge.tsx (Badge, never used)
components/score-meter.tsx (ScoreMeter export, never rendered, but ScorePicker in the same file IS used, keep ScorePicker)
lib/project-utils.ts isActionable (never called)
the "hooks": "@/hooks" alias in components.json (points at a non-existent dir)
Do NOT remove components/ui/card.tsx, I'm keeping it for a later consistency fix.
Before removing each item, grep to confirm it's truly unreferenced. If anything is actually used, leave it and tell me.

3. Add a favicon. The public/ folder was removed earlier so the tab has no icon. Add a simple favicon (an SVG favicon is fine) and reference it in index.html. Keep it minimal and theme-neutral.

When done: run pnpm build and tsc to confirm everything still passes, run the new linter to confirm it's clean, and give me a short summary of what changed. Don't commit, I'll review and commit myself.
```

### 9

```
This is the lint-cleanup batch. Goal: get pnpm lint to pass with zero errors and zero warnings, without disabling rules wholesale or making changes that alter behavior. Work through each finding individually and stop when lint is green.

The 3 react-hooks/set-state-in-effect errors (notes-panel.tsx:16, project-detail.tsx:40, store.tsx:49): evaluate each one separately, don't treat them as identical.

For each, first decide whether the value can be derived during render instead of held in state + synced via effect (the rule's preferred fix). If a clean derivation is possible without changing behavior, do that.
If the effect is a genuine external-data synchronization (e.g. the store's initial fetch-on-mount) where the effect is correct and necessary, keep it and add a targeted // eslint-disable-next-line with a brief comment explaining why it's intentional. Do NOT disable the rule globally.
Tell me, per case, which approach you took and why.

The exhaustive-deps warning (project-detail.tsx:44): the effect intentionally depends on project?.id rather than project. Add a targeted disable-next-line with a one-line comment documenting that this is deliberate.

The 2 react-refresh/only-export-components warnings (dashboard-toolbar.tsx:14, button.tsx:58): these fire because each file exports a component plus a non-component (a constant/variant helper). Fix properly by moving the non-component export into a separate file and updating imports, so Fast Refresh works. If moving it is genuinely impractical for a given file, fall back to a targeted disable-next-line with a comment, but prefer the split.

When done: run pnpm lint (must be clean), pnpm build, and tsc (both must pass), and confirm the app still runs. Give me a per-item summary of what you did. Don't commit, I'll review and commit.
```

### 10

```
On the project-detail page, the next-action field (the pinned callout at the top) doesn't wrap long text, on narrow/mobile widths it overflows instead of wrapping to multiple lines. Fix it so the text wraps properly at all widths. Check whether it's a missing wrap/break style, a flex child that needs min-width:0, or a whitespace/nowrap issue, and fix the actual cause. Verify at 320px, 375px, and 390px widths that long next-action text wraps cleanly with no horizontal overflow. Don't change anything else.
```

### 11

```
This is batch 3, two small fixes from the earlier review. Do only these, then stop.

1. Note deletion needs a confirmation step. Currently deleting a note (components/detail/notes-panel.tsx) is instant with no confirmation, while deleting a project uses a two-step confirm (the confirmingDelete pattern in pages/project-detail.tsx). Make note deletion consistent with that: require an explicit confirm before it deletes, following the same interaction pattern already used for project deletion so it feels consistent. Don't invent a new pattern, match the existing one.

2. The Quick Capture dialog has no focus trap. The hand-rolled dialog (components/ui/dialog.tsx) doesn't trap focus, Tab currently moves focus out of the open dialog into the page behind it, and the backdrop isn't marked inert/aria-hidden. @base-ui/react is already a dependency and its dialog primitive handles this correctly. Either adopt the @base-ui dialog primitive for focus management, or add proper focus trapping + inert backdrop to the existing dialog, whichever is cleaner and less disruptive to the current dialog's look and API. Keep the dialog's current appearance and behavior otherwise.

When done: run pnpm lint (must stay 0/0), tsc, and pnpm build (both clean), verify the app runs, and confirm both fixes work (note delete now asks for confirmation; Tab stays within the open dialog). Don't commit, I'll review.
```

### 12

```
Bug: on the project-detail page, clicking into an editable field and then leaving it (blur) without changing anything still triggers a save, which updates the project's updatedAt and incorrectly bumps it to the top of the dashboard's "recently updated" sort. A no-op (unchanged) blur should not save.

Fix it so each editable field only calls save on blur when its value has actually changed from the project's currently-stored value for that field. Apply this to all the blur-saved fields on this page (name, pitch, description, next action, and any others using the same on-blur save pattern), so touching a field without editing it does nothing.

Make sure a real change still saves normally, and confirm an unchanged blur does NOT change updatedAt. Keep lint at 0/0, tsc and build clean. Only touch what's needed for this. Don't commit.
```

### 13

```
Read this project's Claude Code session transcript(s), extract every prompt I (the user) sent, in order, and write them to _docs/prompts_cc.md as a numbered list, each prompt in a code block, with nothing of your own responses, just my prompts verbatim. If there are multiple sessions, separate them with headers.
```

### 14

```
Refactor the project's folder structure to the conventional Vite layout: move all application source into src/. Currently components/, lib/, pages/, services/, store.tsx, store-context.ts, and use-store.ts live at the repo root instead of under src/, a leftover from the v0/Next.js origin. Consolidate them under src/.

Requirements:
- Move components/, lib/, pages/, services/, store.tsx, store-context.ts, and use-store.ts into src/. Use git mv so history is preserved.
- Update the @/* path alias so it resolves to src/ instead of the repo root: in tsconfig.json (the paths mapping) and in vite.config.ts (the resolve alias). After this, @/ should point at src/.
- Update tsconfig.json's include list, since the root-level entries (store.tsx, etc.) no longer exist at root.
- Update any other config that references these paths: components.json (shadcn aliases / css path), .prettierignore, eslint.config.js ignores, anything else that hardcodes the old locations.
- Because everything imports via the @/ alias, most import statements shouldn't need changing, but check for any relative imports or hardcoded paths that break, and fix them.
- Leave public/, index.html, _docs/, and the root config files where they are, those belong at root.

When done: run pnpm install (in case anything path-related needs it), pnpm lint (must stay 0/0), tsc, and pnpm build (both clean), and run the app to confirm it still works. Report exactly what moved and what config changed. Don't commit, I'll review and commit.
```