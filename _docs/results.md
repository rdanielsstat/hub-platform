# Results

Final report for each Claude Code prompt, verbatim. Numbers match the Claude Code prompts in `prompts.md`. The v0 setup prompt produced the initial code rather than a report, so it has no entry here.

---

## 1

Everything checks out cleanly. Here's a summary of what was done:

**1. Extracted & installed** — Unpacked the zip to project root, installed `pnpm` (wasn't present), ran `pnpm install`. No dependency issues — React 19/Tailwind v4/`@base-ui/react` versions in `package.json` are all real, current releases; install and `tsc -b && vite build` both succeed cleanly.

**2. Built `pages/project-detail.tsx`** — Uses only existing components/api layer: next action pinned in a highlighted callout at the top, inline-editable name/pitch/description/next-action (save on blur), status `<Select>`, the pre-existing-but-unused `RatingInput` for excitement/potential/effort, target date, tag add/remove, link add/remove, and the existing `NotesPanel` for the notes log. Verified via headless Chrome that edits (status change, adding a note) round-trip through `useStore()` → `services/api` and correctly reset on reload (expected, since the mock backend is in-memory).

**3. Cleaned up v0/Next.js cruft**:
- `components.json`: `rsc: true → false`, css path `app/globals.css` → `src/index.css`
- Removed all of `public/` — every file in it (v0's own logo assets + generic Next.js placeholders) was unreferenced anywhere in the code
- `.gitignore`: removed stale `.next/`, added `dist` and `*.tsbuildinfo`

**4. Confirmed end-to-end** — Dashboard renders all 10 seeded projects with working filters/sort/search/tags; mobile layout (verified via true 390px device emulation, not just a resized window) reflows correctly with no overflow; `grep` confirms zero direct `fetch()` calls anywhere — every data operation goes through `services/api`.

One incidental fix: `formatDate`/`daysUntil` in `lib/project-utils.ts` parsed date-only strings as UTC midnight, causing a 1-day mismatch between the date picker and its formatted label in negative-UTC timezones — fixed to parse as local midnight.

---

## 2

Clean build. Summary:

Removed every em dash from the app source across `index.html`, `pages/`, `lib/`, and `services/api/` — components had none to begin with:

- **`index.html`** and **`pages/dashboard.tsx`**, **`pages/project-detail.tsx`**: user-facing copy, replaced with colon or comma depending on sentence structure.
- **`services/api/seed.ts`**: 9 occurrences across pitches, descriptions, notes, and a `nextAction` — mostly colons (label: elaboration pattern), one split into two sentences with a period.
- **`services/api/types.ts`**, **`services/api/index.ts`**: doc comments, colon/period/comma as appropriate.
- **`lib/project-utils.ts`** and one spot in **`pages/project-detail.tsx`**: these two were a literal `'—'` used as a "no date" placeholder character, not sentence punctuation — since neither colon, period, nor comma reads sensibly as an empty-value placeholder, and both branches are currently unreachable in the UI (callers already guard for null/undefined before rendering), I replaced them with an empty string rather than force in a comma. Flagging this deviation in case you'd rather it show something else (e.g. "None").

I left `_docs/specs.md` and `_docs/prompts.md` untouched — those are your own planning/spec documents rather than app code, so I didn't want to rewrite your prose without asking. Let me know if you want those cleaned up too.

Verified with `tsc -b` and `pnpm build` after the changes — both pass clean.

---

## 3

Done — in `components/layout/app-header.tsx`, the `h` avatar tile is gone, replaced with a small filled dot (`bg-primary`, theme-aware) sitting to the left of the "hub" wordmark. Verified in both light and dark mode via screenshot; wordmark and "capture · triage · graduate" tagline are untouched. Typecheck passes clean, nothing else in the file changed.

---

## 4

Done. `components/layout/app-header.tsx`: removed the dot entirely, capitalized the wordmark to "Hub", collapsed the wrapper back to a simple flex-column `Link` (no icon/mark, no extra gap) so the text sits flush left. Tagline and everything else in the header is untouched. Typecheck passes clean.

---

## 5

Done — tagline is now "Capture · Triage · Graduate". Nothing else in the file touched.

---

## 6

Done — wordmark is now lowercase "hub" and the tagline is "capture · triage · graduate". Nothing else in the file touched.

---

## 7 - Codebase Review — No files changed

### Correctness
Clean bill of health. `tsc -b` (with `noUnusedLocals`/`noUnusedParameters`) and `pnpm build` both pass with zero errors or warnings. I also loaded the dashboard, a valid project detail page, an invalid project id, and a bogus route in a real browser and captured the console — no exceptions, no warnings beyond the normal Vite HMR/React DevTools noise.

### Risky / Fragile
1. **No error handling on any write path.** `store.tsx` only wraps `refresh()` (line 35-46) in try/catch/finally; `createProject` (52-57), `updateProject` (58-66), and `deleteProject` (67-70) have none. Compounding this, four calls fire-and-forget with `void save(...)` in `pages/project-detail.tsx:93,98,105,110`, and `components/detail/notes-panel.tsx`'s `add()` (28-39) / `remove()` (41-44) aren't awaited by their callers either. Today the mock always resolves, so this is invisible — but `services/api/index.ts`'s own doc comment says this layer exists so it can be swapped for real HTTP calls later, and every one of these becomes a silent failure or unhandled rejection the moment a real request can fail.
2. **Dead error state.** `store.tsx:20,33,81,91` tracks `error` from `refresh()`, but no component ever reads `useStore().error` — a failed initial load currently just leaves the dashboard's loading skeleton or an empty list, with no message.
3. **Hand-rolled `Dialog` with no focus trap**, despite `@base-ui/react/dialog` already being an installed dependency (`components/ui/dialog.tsx`, whole file). Tab currently cycles a keyboard user out of the open Quick Capture dialog into the page behind it, and the backdrop isn't `inert`/`aria-hidden`.
4. **Inconsistent destructive-action safety.** Deleting a project requires an explicit two-step confirm (`pages/project-detail.tsx`, the `confirmingDelete` flow); deleting a note is instant with no confirmation at all (`components/detail/notes-panel.tsx:41-44`), even though both are equally unrecoverable in the mock.
5. **No linter/formatter configured** (no ESLint, no Prettier in `package.json`). Style is consistent today by discipline only — nothing enforces it as the codebase grows.

### Consistency
1. **API seam not actually used end-to-end.** `services/api/mock.ts:37-40` exports `getProject(id)`, and it's on the `ApiClient` interface, but nothing calls it — `pages/project-detail.tsx:28` uses the store's own synchronous `getProject`, which just filters the already-bulk-loaded `projects` array. A real backend would want a single-item GET; this breaks the "clean seam" principle from spec §1.
2. **Two different data-flow conventions.** All project CRUD is centralized through `store.tsx`, but notes bypass the store entirely and call `api.listNotes/addNote/deleteNote` directly from `components/detail/notes-panel.tsx:17,33,43`.
3. **Three separate hand-copied "empty state" layouts** instead of one shared component: `pages/not-found.tsx:7-20`, `pages/dashboard.tsx`'s `EmptyState` (124-160), and the not-found branch in `pages/project-detail.tsx:62-80`.
4. **Duplicated "back to dashboard" button, one correct, one not.** `pages/not-found.tsx:17` correctly reuses `buttonVariants({ size: 'lg' })`; `pages/project-detail.tsx:73-78` hand-rolls the same button with raw classes, missing the hover/focus-visible/transition states `buttonVariants` provides.
5. **Three implementations of the same 1–5 rating widget** with diverging a11y: `components/score-meter.tsx`'s `ScorePicker` has `aria-pressed` and the label pattern `"${label} ${n} of 5"` (line 60-61); `components/detail/rating-input.tsx`'s `RatingInput` (used in project-detail) has no `aria-pressed` and a different label pattern `"${label}: ${n}"` (line 29).
6. **Visual drift from the card primitive.** `components/project-card.tsx:19` uses `shadow-sm`; the four section cards in `pages/project-detail.tsx:220,241,254,302` reuse the same border/bg recipe but drop `shadow-sm`, and none of them use the actual `Card` component from `components/ui/card.tsx`.
7. **Two different write-optimism strategies.** Note deletion updates local state before the API call resolves (`components/detail/notes-panel.tsx:41-44`); every project field edit waits for `store.updateProject` to resolve first.
8. **Dead ternary.** `pages/project-detail.tsx:46-49` computes `due` with a `project ? ... : '-'` fallback, but by the only place it's rendered, `project` is already guaranteed non-null — the fallback branch can't fire.

### Dead code / cruft
1. `components/ui/card.tsx` — `Card`/`CardHeader`/`CardTitle`/`CardDescription`/`CardContent`/`CardFooter`, all exported, none imported anywhere.
2. `components/ui/badge.tsx` — `Badge` exported, never used (status pills use a separate hand-rolled span in `components/status-badge.tsx`).
3. `components/score-meter.tsx` — `ScoreMeter` exported, never rendered (only its sibling `ScorePicker` is used).
4. `lib/project-utils.ts:67-69` — `isActionable` exported, never called.
5. `services/api/mock.ts:37-40` — `getProject` never called (see Consistency #1).
6. `components.json:14` — `"hooks": "@/hooks"` alias points at a directory that doesn't exist in this project (default shadcn scaffold leftover).
7. `index.html` — no favicon/app icon at all. The whole `public/` folder (including its icons) was removed as v0 cruft in an earlier pass and nothing replaced it, so the browser tab currently shows no icon.

### Spec alignment (`_docs/specs.md`)
1. **Missing entirely: attachments.** §3 defines an `attachments` table and §4.3 explicitly lists it as a project-detail requirement. No type, no mock CRUD, no UI exists anywhere for this.
2. **No PWA installability.** §1, §2, §5 all call for "installable as a PWA" — there's no manifest, no service worker, and (per cruft #7) currently no icons to build one from.
3. **Dashboard's "gone stale" and "high-excitement/low-effort" surfacing (§4.2) aren't explicit.** Sorting exists (recently-updated, opportunity score, etc.) but there's no dedicated "stale" badge or a "quick win" callout distinct from the general opportunity sort.
4. **Dark mode doesn't persist and ignores system preference** (`components/layout/app-header.tsx`'s `useTheme`, lines 6-12) — resets to light on every reload. Not spec-required, but worth pairing with the PWA gap above since `<meta name="theme-color">` (`index.html:6`) is also static and won't follow the toggle.
5. **No Login screen (§4.1)** — expected at this stage, since `_docs/prompts.md`'s own instructions scoped this build to a mocked, backend-less frontend. Flagging for completeness, not as a defect.

Let me know which of these you want tackled — I'd suggest starting with the write-error-handling gap and the dead `error` state, since those are the ones that'll bite hardest once a real backend replaces the mock.

---

## 8

**1. ESLint + Prettier setup**
- Added `eslint.config.js` (flat config): `@eslint/js` recommended + `typescript-eslint` recommended + `eslint-plugin-react-hooks` (`recommended-latest`, current Vite/React 19 standard) + `eslint-plugin-react-refresh` + `eslint-config-prettier` to kill any formatting-rule overlap.
- Added `.prettierrc.json` (`semi: false, singleQuote: true` — everything else was already the codebase's existing style, which matches Prettier's defaults: 2-space indent, 80 print width, trailing commas). `.prettierignore` excludes `dist`, `pnpm-lock.yaml`, and `_docs` (your own docs, left untouched).
- Added `lint`, `format`, `format:check` scripts to `package.json`.
- Installed 8 new devDependencies. Note: `pnpm add` initially resolved `eslint@10.11.0`, published *the day before* this session, which tripped pnpm's supply-chain `minimumReleaseAge` guard and silently added an exclusion to `pnpm-workspace.yaml`. I didn't want to leave that hole open, so I reinstalled pinned to `eslint@10.10.0` instead and reverted the workspace file — no policy exception needed.
- `npx prettier --write .` reformatted 7 files — all pure mechanical line-wrap/collapse from the 80-char print width (e.g. a union type and an export statement that now fit on one line, a couple of long strings/JSX attrs that now wrap). I diffed every one; nothing behavioral changed.
- **Lint findings (reported, not fixed, per your instruction):** `pnpm lint` currently reports **3 errors, 4 warnings**:
  - 3× `react-hooks/set-state-in-effect` (in `notes-panel.tsx:16`, `project-detail.tsx:40`, `store.tsx:49`) — this is a new, stricter rule in `eslint-plugin-react-hooks` v7 that flags the common "set loading/sync state at the top of a data-fetching effect" pattern. All three are the idiomatic fetch-on-mount/sync-local-draft pattern already covered in my earlier review — real, but not urgent.
  - 1× `react-hooks/exhaustive-deps` warning (`project-detail.tsx:44`) — the effect deliberately depends on `project?.id` rather than `project`, which is intentional but undocumented.
  - 2× `react-refresh/only-export-components` warnings (`dashboard-toolbar.tsx:14`, `button.tsx:58`) — these files export a component plus a constant/variant-helper from the same module, which is fine functionally but breaks Vite Fast Refresh for that file.

  None of these are auto-fixable (confirmed via `--fix-dry-run`) — they're all judgment calls, so I left them for you to decide on.

**2. Dead code removed** (all confirmed unreferenced by grep first):
- `components/ui/badge.tsx` deleted entirely (`Badge` + `badgeVariants`, both unused).
- `components/score-meter.tsx`: removed only the `ScoreMeter` export; kept `ScorePicker` and the shared `tones` object.
- `lib/project-utils.ts`: removed `isActionable`.
- `components.json`: removed the dangling `"hooks": "@/hooks"` alias.
- `components/ui/card.tsx` left untouched as requested.

**3. Favicon added** — recreated a minimal `public/favicon.svg` (a single flat purple dot, `#6d5ffd`, transparent background — no theme-flip logic needed since a plain color reads fine on both light and dark tab bars) and wired it up with `<link rel="icon" type="image/svg+xml" href="/favicon.svg" />` in `index.html`.

**Verification:** `tsc -b` clean, `pnpm build` clean, `prettier --check .` clean, dev server serves the favicon correctly, dashboard/detail pages still render fine. Nothing committed — all yours to review.

---

## 9

**Correction to my earlier report:** last time I said there were 2 fast-refresh warnings; there were actually 3 (I missed `store.tsx:103`). Fixed all 3 below.

### `react-hooks/set-state-in-effect` (3 errors)

- **`store.tsx`** (fetch-on-mount) — **kept the effect, added a targeted disable comment.** `refresh()` calls `setLoading(true)`/`setError(null)` before its `await api.listProjects()`; this is a real external-data fetch that can't happen during render, so it's the genuine-synchronization case.
- **`components/detail/notes-panel.tsx`** (fetch-on-mount, keyed by `projectId`) — **kept the effect, added a targeted disable comment.** Same reasoning: `setLoading(true)` resets the skeleton before an async `api.listNotes(projectId)` call that must re-run when `projectId` changes (e.g. navigating between projects without unmounting).
- **`pages/project-detail.tsx`** (re-seeding draft fields when the loaded project changes) — **refactored, no disable needed.** This wasn't a real "external system" sync — it was resetting local editable draft state (`name`, `pitch`, `description`, `nextAction`) whenever `project.id` changes. Per React's own documented pattern for this exact case, I replaced the effect with a render-time adjustment: a `seededId` state tracks the last project the fields were seeded from, and the draft fields are reset conditionally in the render body itself rather than in a post-commit effect. Behavior is identical (verified live: navigating client-side from one project to another, without a full reload, correctly reset every field to the new project's values, zero console errors). Since the effect no longer exists, its dependency array is also gone — **this made the separate exhaustive-deps item at line 44 moot too**, so no disable comment was needed there either.

### `react-refresh/only-export-components` (3 warnings — see correction above)

All three fixed with proper file splits, imports updated at every call site:
- **`components/dashboard/dashboard-toolbar.tsx`**: moved `SortKey`/`SORT_LABELS` into a new `components/dashboard/sort-options.ts`. Updated `pages/dashboard.tsx`'s import.
- **`components/ui/button.tsx`**: moved `buttonVariants` into a new `components/ui/button-variants.ts`. Updated `pages/not-found.tsx`'s import.
- **`store.tsx`** (the one I missed originally): `useStore` was exported alongside the `StoreProvider` component, and cleanly splitting it also required extracting the `StoreContext`/`StoreValue` (since both files need it). Created `store-context.ts` (context + type) and `use-store.ts` (the hook); `store.tsx` now only exports `StoreProvider`. Updated the 3 importers (`pages/dashboard.tsx`, `pages/project-detail.tsx`, `components/quick-capture-dialog.tsx`).

`tsconfig.json`'s `include` list got the two new root-level files (`store-context.ts`, `use-store.ts`) added alongside the existing `store.tsx` entry.

### Verification
- `pnpm lint` → **0 errors, 0 warnings.**
- `tsc -b` → clean.
- `pnpm build` → clean.
- `prettier --check .` → clean (ran format once, only whitespace no-ops).
- Live-tested in a real browser: dashboard loads, notes still load per-project, and — most importantly — navigating between two different projects' detail pages without a full page reload correctly re-seeds every draft field, confirming the render-time-adjustment refactor didn't change behavior.

Nothing committed — all yours to review.

---

## 10

**Root cause:** the next-action callout used `<Input>` — a native single-line `<input>` element. Native inputs can never wrap their value across multiple lines regardless of CSS (no `white-space`/`min-width:0` fix can change that); they just clip/scroll internally. That's exactly what the screenshot showed at 375px: text cut off mid-word, no page-level overflow. It wasn't a flexbox or whitespace bug — the field was structurally the wrong kind of control for text that needs to wrap.

**Fix (`pages/project-detail.tsx` only):**
- Swapped the `<Input>` for a native `<textarea rows={1}>`, styled to match the original input's look exactly for short text (same padding, border, focus states).
- Added a `useLayoutEffect` that syncs the textarea's height to its `scrollHeight` whenever `nextAction` changes — this is the textbook correct use of an effect (direct DOM mutation to sync with an external system), not a React-state effect, so it doesn't trip the `set-state-in-effect` rule from the recent lint cleanup.
- This auto-grows the box to fit however many lines the text wraps to, and shrinks back down for short text, while typing.

**Verified** at 320px, 375px, and 390px with a long next-action string: `document.documentElement.scrollWidth === window.innerWidth` at all three (zero horizontal page overflow), and the textarea's `scrollHeight ≈ clientHeight` (fully expanded, no clipped/hidden lines) — confirmed visually via screenshots too. Also confirmed the normal case (short, single-line next-action text) still renders at its original compact height with no visual regression, and `pnpm lint` / `tsc` / `pnpm build` all pass clean. Nothing else was touched.

---

## 11

**1. Note deletion confirmation (`components/detail/notes-panel.tsx`)**

Matched the exact `confirmingDelete` pattern from `project-detail.tsx`: a `confirmingId` state tracks which note (if any) is pending confirmation. Clicking the trash icon no longer deletes immediately — it swaps that note's footer row for "Delete this note?" + Cancel (ghost) + Delete (destructive) buttons, same wording style and button variants as the project-delete flow. Cancel reverts to the plain state; Delete actually removes it. Verified live: clicking trash leaves the note count unchanged and shows the confirm row; Cancel dismisses without deleting; a second confirm-then-Delete actually removes it.

**2. Dialog focus trap (`components/ui/dialog.tsx`)**

Rewrote it on top of `@base-ui/react/dialog`'s public primitives (`Root`/`Portal`/`Backdrop`/`Popup`/`Close`) rather than the hand-rolled portal + manual `keydown`/body-scroll-lock effect. I deliberately avoided `@base-ui/react`'s internal `FloatingFocusManager` (it's explicitly marked `@internal` in its own source — not a stable surface to build on) and used the documented Dialog component instead. This also let me delete all the manual Escape-key and scroll-lock logic, since `Dialog.Root`'s default `modal: true` handles that internally.

- Kept `DialogHeader`/`DialogBody`/`DialogFooter` and the `Dialog` component's external API (`open`/`onClose`/`title`/`className`) completely unchanged, so `quick-capture-dialog.tsx` required zero edits.
- Set `initialFocus={false}` on the Popup specifically to avoid it fighting with the existing `autoFocus` on the Name field — verified the Name field still gets focus on open, unchanged.
- Re-derived the enter/exit animation using base-ui's `data-starting-style`/`data-ending-style` attributes in place of the old one-shot `animate-in` classes, matching the original fade/zoom/slide-up look and the mobile bottom-sheet vs. desktop-centered layout — confirmed identical visually via screenshots at both desktop and 390px widths.

Verified via real Tab-key dispatch (15 presses): focus now cycles perfectly through only the dialog's 5 focusable elements (Close, Name, Pitch, More details, Cancel — the two submit buttons are correctly excluded since they're `disabled` until a name is entered) and wraps back around, never once escaping to the header or dashboard behind it. Also confirmed: `#root` gets `aria-hidden="true"` automatically while open (satisfies the inert-background requirement), Escape closes it, clicking the backdrop closes it, and there were zero console errors throughout.

**Final checks:** `pnpm lint` → 0/0, `tsc -b` → clean, `pnpm build` → clean, app runs correctly. (Also noticed `_docs/tech-debt.md` is a new untracked file — that's yours, I didn't touch it.)

---

## 12

Fixed all 4 blur-saved fields on the project-detail page to compare the draft value against the project's currently-stored value before calling `save`, so a no-op blur (focus in, blur out, nothing typed) never persists:

- **Next action** — `nextAction !== project.nextAction && save({ nextAction })`
- **Name** — kept its existing trim/non-empty guard, added `trimmed !== project.name`
- **Pitch** — `pitch !== project.pitch && save({ pitch })`
- **Description** — `description !== project.description && save({ description })`

Confirmed these were the only 4 on-blur-save sites in the whole codebase (`grep -rn onBlur`). The status select, ratings, target date, tags, and links all already use `onChange`, which only fires on an actual user-driven value change, so they didn't need touching.

Verified live in the browser (not just by reasoning): focusing and blurring the pitch and name fields without typing anything left "Updated 2mo ago" unchanged both times, while actually editing the pitch and blurring correctly flipped it to "Updated just now" and persisted the new value — confirming both the no-op suppression and real saves work correctly.

---

## 13

Done. `_docs/prompts_cc.md` now contains all 13 prompts from this single Claude Code session (`acf69d03-8cff-41e1-b53c-0d891895c84c`), in chronological order, each as a numbered list item with the verbatim text in a code block — nothing else. Since there was only one session transcript for this project, no session headers were needed.

---

## 14

All checks pass — lint 0/0, tsc clean, pnpm build clean, and the running app was verified live (dashboard, project detail, and Quick Capture dialog all work with zero console errors). Nothing committed, as requested.

### What moved

Everything now lives under `src/`, moved with `git mv` (all tracked as renames):

- `components/` → `src/components/`
- `lib/` → `src/lib/`
- `pages/` → `src/pages/`
- `services/` → `src/services/`
- `store.tsx` → `src/store.tsx`
- `store-context.ts` → `src/store-context.ts`
- `use-store.ts` → `src/use-store.ts`

`src/App.tsx`, `src/main.tsx`, `src/index.css` were already there and didn't move. `public/`, `index.html`, `_docs/`, and the root config files stayed at root as instructed.

### What config changed

- `tsconfig.json`: `paths` alias `"@/*": ["./*"]` → `"@/*": ["./src/*"]`; `include` collapsed from the old 8-entry list (`src`, `components`, `lib`, `services`, `pages`, `store.tsx`, `store-context.ts`, `use-store.ts`) down to just `["src"]`, since everything now lives there.
- `vite.config.ts`: resolve alias `'@': path.resolve(__dirname, '.')` → `path.resolve(__dirname, './src')`.

### What didn't need changing (checked, left alone)

- `components.json`: its `css` field was already `"src/index.css"`, and its aliases (`@/components`, `@/lib`, etc.) are expressed relative to the `@/` prefix itself, so they resolve correctly automatically now that `@/` points at `src/`.
- `.prettierignore` and `eslint.config.js`: neither hardcodes any of the moved directories (glob-based `dist/**/*.{ts,tsx}` patterns already cover `src/**`).
- `index.html`: `<script src="/src/main.tsx">` was already correct.
- Relative imports: the only ones in the codebase (`services/api/*.ts` importing siblings, `src/main.tsx` → `./App`) are between files that moved together or didn't move at all, so none broke. Every cross-directory import already went through the `@/` alias, exactly as expected.

## 15

Moved the entire frontend into a `frontend/` subfolder to prepare for adding `backend/` alongside it. All moves done with `git mv` (tracked as renames, history preserved). Nothing committed.

### What moved

Every frontend file/folder moved under `frontend/`: `src/`, `public/`, `index.html`, `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`, `tsconfig.json`, `vite.config.ts`, `eslint.config.js`, `.prettierrc.json`, `.prettierignore`, `components.json`.

Left at root as instructed: `_docs/` and the root `.gitignore`.

`node_modules/` at the old root wasn't git-tracked (as expected): deleted it and ran a fresh `pnpm install` inside `frontend/`, which reinstalled cleanly. Also found and removed a stray `.vite/` cache directory that had accumulated at repo root from earlier dev-server runs (untracked debris, unrelated to the move).

### What config changed

- **Root `.gitignore`:** removed the frontend-toolchain-specific lines (`node_modules`, `dist`, `*.tsbuildinfo`, `pnpm-debug.log*`, `.eslintcache`), keeping genuinely repo-wide ignores (env files, `.DS_Store`, `.vscode/`, the v0 cruft entries, archive, generic `*.log`).
- **New `frontend/.gitignore`:** holds the ignores removed from root, plus `.vite` (added after finding that cache leaking to disk).
- **`frontend/.prettierignore`:** dropped the `_docs` entry: now unreachable from inside `frontend/` since `_docs/` lives outside this subtree, so prettier run from `frontend/` never sees it.

### What didn't need changing (checked, confirmed correct)

- **`tsconfig.json`** (paths, include) and **`vite.config.ts`** (resolve.alias): both use paths relative to their own file's location (`./src`), so moving the file and its sibling `src/` down together didn't break anything. `@/` still resolves to `frontend/src`.
- **`index.html`:** `src="/src/main.tsx"` and `href="/favicon.svg"` are root-relative to Vite's server root, which is now `frontend/` (since `index.html` and `vite.config.ts` both live there). Still correct.
- **`components.json`:** `css: "src/index.css"` and the `@/`-prefixed aliases are all relative/alias-based, unaffected.
- **`eslint.config.js`:** `ignores: ['dist']` and file globs are relative to its own location, and ESLint only scans the directory it's run from (`frontend/`).

### Verification

From inside `frontend/`: `pnpm install` (fresh, clean), `pnpm lint` → 0 errors / 0 warnings, `tsc -b` → clean, `pnpm build` → clean. Ran the dev server in a real browser: dashboard renders all 10 seeded projects, favicon serves 200, project-detail page renders fully and correctly with zero console errors.

## 16

Fixed the dashboard's "recently updated" sort so note changes bump the parent project, not just edits to the project's own fields. Only 4 files touched. Nothing committed.

### Where this went, and why

Checked the layer structure before touching anything: `services/api/mock.ts` is the sole data owner, `store.tsx` is the seam that syncs mock results into React state (which the dashboard reads for its sort), and `notes-panel.tsx` was calling `api.addNote`/`api.deleteNote` directly, bypassing the store entirely.

That bypass was the actual bug. `mock.ts`'s `addNote` already bumped the project's `updatedAt` internally, but since `notes-panel.tsx` never went through `store.tsx`, the React `projects` state the dashboard renders from never found out about the bump. It would only have shown up after a full reload. `deleteNote` didn't even do the internal bump.

### What changed

- **`services/api/mock.ts`:** added a private `touchProject(id)` helper (the central seam), and made both `addNote` and `deleteNote` call it and return the updated project. `addNote` now returns `{ note, project }`; `deleteNote` now returns `Project` instead of `void`.
- **`store-context.ts` / `store.tsx`:** added `addNote`/`deleteNote` to the store's public surface. Both call the api, then splice the returned bumped project into the store's `projects` state the same way `updateProject` already does. This is what makes the dashboard sort update live.
- **`notes-panel.tsx`:** now calls `useStore().addNote`/`deleteNote` instead of `api.addNote`/`api.deleteNote` directly. `listNotes` stays a direct api call since it's a pure read with no state to sync.

`pages/project-detail.tsx` was not touched, so the no-op-blur comparisons for name/pitch/description/next action stay intact.

### On attachments

`touchProject` is the seam for this. When attachments are built, `addAttachment`/`deleteAttachment` in `mock.ts` just need to call `touchProject(projectId)` too (one line), and the store methods would follow the identical splice-the-returned-project pattern as notes. It's not automatic (a future implementer still has to call it), so there's a comment on `touchProject` flagging it.

### Verification

Tested all four behaviors live, each in isolation:
- Add a note → project jumps to the top of "recently updated."
- Delete a note → same.
- Real project-field edit (pitch) → still bumps and re-sorts.
- No-op blur (focus in, blur out, no change) → `updatedAt` unchanged.

Lint 0/0, tsc clean, pnpm build clean.

## 17 - AGENTS.md created

Wrote `AGENTS.md` at the repo root after inspecting the actual layout and `frontend/package.json`. Not committed.

Full contents:

```markdown
# AGENTS.md

Standing instructions for AI coding agents working in this repo.

## Project

Hub: a personal platform to capture, organize, and triage project ideas, from
small sparks to standalone builds. See `_docs/specs.md` for the product spec
and data model — that document is the source of truth; don't duplicate it
here and don't let this file drift from it.

## Structure

- `frontend/` — the app. Vite + React SPA, self-contained (its own
  `package.json`, `src/`, config). Currently the only thing that runs.
- `backend/` — not built yet. See "Backend" below.
- `_docs/` — specs, planning notes, and session logs. Reference material, not
  code.

## Frontend

Stack: Vite, React 19, TypeScript, Tailwind v4, shadcn/ui (`components.json`),
`@base-ui/react` for accessible primitives (dialogs, etc.), pnpm.

All commands run from inside `frontend/`:

pnpm install
pnpm dev            # start the dev server
pnpm build          # tsc -b && vite build — must be clean before calling a task done
pnpm lint           # eslint . — must stay 0 errors / 0 warnings
pnpm format         # prettier --write .
pnpm format:check   # prettier --check .

- The `@/` import alias resolves to `frontend/src` (set in both
  `tsconfig.json` and `vite.config.ts`).
- All data access goes through `frontend/src/services/api/`. Never call
  `fetch` directly from a component. Today that layer is an in-memory mock
  (`services/api/mock.ts`); it's the seam that gets swapped for real HTTP
  calls to the backend later, so keep components talking to `api`/the store,
  not to the mock internals.

## Backend (planned — `backend/` does not exist yet)

Not built. When it is:

- FastAPI, Python dependencies managed with `uv`.
- Starts on an in-memory store, then SQLite via SQLAlchemy, kept
  database-agnostic so it can move to Postgres later without a rewrite.
- Auth is roll-your-own: password hashing + JWT bearer tokens, OAuth2
  password flow. Token-based so the same API serves the web app and a future
  iOS app.
- Multi-user with per-user data isolation.

Treat this section as intent, not fact, until the folder exists.

## Working conventions

- Commit regularly; keep changes small and scoped to what was asked.
- Run lint, typecheck, and build and confirm they're clean before considering
  a task done.
- Don't commit unless explicitly asked to.
- Match the existing code style. ESLint + Prettier are configured in
  `frontend/`; lint must stay at 0 errors / 0 warnings.

## Do not

- Don't restructure or refactor working code unless asked.
- Don't add dependencies casually — only what a task actually needs.
- Don't reproduce or edit files under `_docs/` as if they were code; they're
  planning/reference material.
```

Not committed. A couple of things you may want to weigh in on:
- I described @base-ui/react as "for accessible primitives (dialogs, etc.)" based on how it's actually used in the code (Button, Dialog) — adjust if that's not the framing you want.
- The backend section is written purely from your prompt's description since backend/ doesn't exist to inspect — flag anything there that's already stale or that you want phrased differently.

## 18 - openapi.yaml contract

Wrote `openapi.yaml` (687 lines) at the repo root, derived from the frontend's API client and the spec's data model. Parses cleanly. No backend code written.

### Endpoints defined

**Auth** (spec-derived; frontend doesn't call these yet, see mismatches)
- `POST /auth/register` — email + password + optional displayName → token
- `POST /auth/login` — OAuth2 password grant (form-urlencoded, username=email) → token
- `GET /auth/me` — current user

**Projects** (from store.tsx's 5 calls)
- `GET /projects` → Project[], no query params
- `POST /projects` → Project
- `GET /projects/{projectId}` → Project
- `PATCH /projects/{projectId}` → Project
- `DELETE /projects/{projectId}` → 204

**Notes** (from store.tsx + notes-panel.tsx)
- `GET /projects/{projectId}/notes` → Note[], newest first
- `POST /projects/{projectId}/notes` → { note, project } (matches mock.ts's addNote exactly — returns both since adding a note bumps the parent project's updatedAt)
- `DELETE /notes/{noteId}` → returns the parent project, not the note (matches deleteNote(id): Promise<Project> in mock.ts)

**Attachments** — marked provisional throughout, see mismatches.

All project/note/attachment endpoints require bearerAuth; 404 is used uniformly for "not found or not yours," so the API never reveals another user's data exists.

### Mismatches to resolve before writing backend code

1. **Auth has zero frontend integration today.** No login/signup screens, no token storage, no Authorization header anywhere in frontend/src/. The auth endpoints are derived from the spec alone, not from any actual caller. Decide: wire the backend's auth before or alongside the frontend's login/signup screens, since right now there's nothing to test it against end-to-end.
2. **Attachments have no frontend API surface at all** — not in types.ts, mock.ts, or index.ts's ApiClient interface. Stubbed GET/POST /projects/{projectId}/attachments and DELETE /attachments/{attachmentId} from the spec's table columns and marked them PROVISIONAL. The bigger open question is the upload mechanism — direct-to-S3 presigned PUT vs. proxied multipart through the API — which the spec doesn't decide. Treat this section as a placeholder, not a contract to build against yet.
3. **camelCase vs snake_case.** Frontend types are camelCase (nextAction, targetDate, createdAt); the spec's tables are snake_case. Resolved by making the API JSON camelCase everywhere, matching the frontend exactly, so the mock→HTTP swap needs no component changes. This means FastAPI/Pydantic models need alias_generator config to serialize camelCase — flagged as deliberate.
4. **One deliberate exception to camelCase:** the token response (access_token, token_type) stays snake_case, per the OAuth2 spec's field naming, which FastAPI's built-in Swagger Authorize flow expects literally.
5. **links field type.** Spec lists it ambiguously as jsonb / text[]. Frontend's types.ts is unambiguous: links: string[]. Went with the flat array of URL strings. Flagging in case you wanted structured link objects (label a link as "repo" vs "demo").
6. **UpdateProjectInput** allows updatedAt in the frontend's TS type, but mock.ts always overwrites updatedAt server-side. Excluded updatedAt from the contract's UpdateProjectInput schema entirely, since it should never be client-settable. Confirm that's intentional.
7. **targetDate is date-only** (YYYY-MM-DD), while createdAt/updatedAt are full ISO datetimes. Modeled as format: date vs format: date-time respectively.
8. **No filtering/sorting/pagination on GET /projects,** even though the dashboard calls for filter-by-status/tag and sort-by-score/date. Today that's all client-side over the full list. Fine for v1 scale, will need revisiting if the list grows large.

## 19 - Labeled links

Changed project links from flat URL strings to labeled objects ({ label?: string; url: string }), across the contract and frontend. Four files touched.

### Files touched (confirmed before changing)

Links only appeared in types.ts, mock.ts, seed.ts, and project-detail.tsx. mock.ts passes the array through generically, so it needed no logic change, only the type flowing from types.ts.

- **openapi.yaml** — new Link schema ({ label?: string, url: string }), used by Project, CreateProjectInput, UpdateProjectInput
- **frontend/src/services/api/types.ts** — new Link type; Project.links and CreateProjectInput.links are now Link[]
- **frontend/src/services/api/seed.ts** — "This Incubator" now has labeled links (Repo, Demo); chess project's Lichess API link stays unlabeled
- **frontend/src/pages/project-detail.tsx** — display falls back to link.label || link.url; add row gained an optional "Label" input alongside the existing URL input, both wired to Enter-to-submit; removal keys off url

mock.ts needed no changes — it passes links through generically.

### Verified in-browser

(dev server on :5174, extension needed a reconnect first)
- Seeded labeled links ("Repo", "Demo") render with their labels
- Seeded unlabeled link renders as the raw URL
- Added a link with no label in one step (Enter in the URL field alone) — normalized to https:// and displayed as the URL
- Added a link with a label — displayed as the label
- Removed both test links to leave state as it was

Lint (0/0), tsc -b, vite build, and prettier --check all clean. Not committed.

## 20 - FastAPI backend scaffold

Scaffolded a skeleton FastAPI backend in backend/, managed by uv. Health endpoint only, no auth/models/logic. Not committed.

### Layout chosen, and why

```
backend/
  pyproject.toml       # uv-managed, deps: fastapi, uvicorn[standard]
  uv.lock
  .python-version      # 3.12
  .gitignore           # venv, __pycache__, .env, *.db, etc.
  README.md
  app/
    __init__.py
    main.py             # FastAPI() + CORS (localhost:5173) + router registration
    routers/
      __init__.py
      health.py          # GET /health -> {"status": "ok"}
    core/__init__.py     # placeholder — settings later
    auth/__init__.py     # placeholder — password hashing + JWT later
    models/__init__.py   # placeholder — Pydantic schemas + ORM models later
    db/__init__.py       # placeholder — in-memory store, then SQLite later
```

app/ (flat package, not src/) because this is a single deployable service, not a library meant to be installed elsewhere. routers/, auth/, models/, db/, core/ are split now, even though most are empty, because the openapi contract already implies that shape. Adding those seams now means the next session drops files in rather than restructuring.

### Commands to run it

```
cd backend
uv sync                              # install deps
uv run uvicorn app.main:app --reload # dev server, http://localhost:8000
```

### Verified clean

- GET /health → {"status":"ok"}, HTTP 200
- GET /docs → HTTP 200 (Swagger UI loads)
- GET /openapi.json → generated correctly, one path: /health
- git add -n backend/ confirms .venv/ and __pycache__/ are properly ignored

Nothing committed.

## 21 - Backend auth + projects (in-memory)

Built auth and project CRUD in backend/, scoped per user, against the in-memory store. Built to openapi.yaml. No notes/attachments, no database yet. 15/15 tests pass. Not committed.

### What was built

**Auth** (app/auth/, app/routers/auth.py)
- security.py: hash_password/verify_password via passlib with argon2, create_access_token/decode_access_token via PyJWT, HS256, 60-minute expiry.
- dependencies.py: get_current_user, an OAuth2PasswordBearer dependency that decodes the bearer token and loads the user; raises 401 on missing/invalid/expired token or unknown subject.
- routers/auth.py: POST /auth/register (409 on duplicate email), POST /auth/login (OAuth2PasswordRequestForm, so Swagger's Authorize button works), GET /auth/me.

**Projects** (app/routers/projects.py)
- Full CRUD scoped through get_current_user. Every store lookup takes (project_id, owner_id) together, so store.get_project returns None if the id doesn't exist or belongs to someone else, and the router turns that into a single 404 either way. Create assigns owner_id=current_user.id server-side; the client never supplies it.

**Store** (app/db/store.py, app/db/seed.py)
- InMemoryStore with UserRecord/ProjectRecord dataclasses, keyed by id, with an email index. get_store() is the dependency every router uses, so swapping in SQLAlchemy later only touches this file and the one Depends(get_store) wiring point, not the routers.
- seed.py populates one demo user with two projects (ported from the frontend's p-incubator/p-chess seed data). Credentials in the README: demo@hub.dev / demo1234.

**Models** (app/models/)
- base.py: CamelModel (alias_generator=to_camel, populate_by_name=True); every camelCase schema extends this.
- user.py, project.py: User, RegisterInput, Project, Link, CreateProjectInput, UpdateProjectInput matching openapi.yaml field-for-field, plus TokenResponse, which deliberately stays snake_case (access_token, token_type) per OAuth2 convention.

### Decisions / things the contract left open

1. **Argon2 over bcrypt.** Spec said "bcrypt/argon2." Picked argon2 — current passlib releases have a known compatibility break with recent bcrypt versions, and argon2 has no 72-byte password truncation quirk. Swappable via pwd_context in security.py.
2. **JWT secret.** Not specified. Defaults to a hardcoded dev string in security.py, overridable via HUB_JWT_SECRET. No config/settings module yet (app/core/ still empty) — first thing that'll need one.
3. **Token expiry.** Not specified. Picked 60 minutes; easy to change in security.py.
4. **PATCH semantics for targetDate.** Used exclude_unset=True on UpdateProjectInput, so omitting the field leaves it untouched but explicitly sending "targetDate": null clears it — matching the frontend's clear-date button.
5. **Case-insensitive email matching** on register/login (not in the contract, but avoids Foo@x.com and foo@x.com registering as two accounts).

### Verified

- uv run pytest → 15 passed (7 auth, 8 project/isolation), including the four isolation cases by name: 404-not-403 on GET, blocked PATCH, blocked DELETE with the project still intact for the owner, and list never leaking another user's projects.
- Live server: /health and /docs both 200; logged in as the seeded demo user via /docs; confirmed /auth/me and /projects return exact camelCase shapes matching openapi.yaml (including a link with "label": null); live cross-user check against the running server confirmed 404 on GET/PATCH of another user's project and 401 with no token.

Nothing committed.

## 22 - Frontend wired to backend (auth + projects)

Connected the frontend to the real FastAPI backend for auth and projects. Notes/attachments still on the mock. Verified end-to-end in the browser. Not committed.

### What was built

**Config** — frontend/src/lib/config.ts exports API_BASE_URL from VITE_API_BASE_URL (defaults to http://localhost:8000), backed by .env.example and vite-env.d.ts for typing.

**HTTP layer** (services/api/)
- token.ts — localStorage-backed JWT storage (hub.token).
- http.ts — httpRequest(): attaches Authorization: Bearer <token> unless skipAuth, JSON- or form-encodes the body, throws HttpError(status, message) from FastAPI's detail field, and calls a registered onUnauthorized handler when an authenticated request returns 401 (never fires for a plain wrong-password login, since that request carries no token).
- auth.ts — authApi.register/login/getCurrentUser/logout, always real (auth never had a mock).
- real.ts — realProjectsApi, real HTTP implementations of the five project endpoints, same signatures as mockApi's.

**The real/mock split** — services/api/index.ts now builds api as an object literal: project methods from realProjectsApi, note methods still from mockApi, each half labeled with a comment (MOCK — PENDING BACKEND) so the next slice knows what to swap. authApi exported alongside.

**Auth state** — auth-context.ts/auth.tsx/use-auth.ts mirror the existing store pattern: status 'loading'|'authenticated'|'unauthenticated', validates a stored token against /auth/me on mount, exposes login/register/logout.

**Gating** — main.tsx wraps the app in AuthProvider. App.tsx branches on status: unauthenticated renders only /login+/signup; authenticated mounts StoreProvider around the real app. Mounting StoreProvider only when authenticated ensures projects state (and its fetch-on-mount) resets cleanly between users and never fires while logged out.

**UI** — pages/login.tsx, pages/signup.tsx (matching existing style), sign-out control in AppHeader (email/display name + logout icon).

### What didn't line up

The mock's note-touches-parent-project behavior assumed the mock owned every project. Once projects moved to the backend, touchProject would throw "Project not found" for any real project id, crashing the notes panel. Fixed by making touchProject return null instead of throwing for unrecognized ids; addNote/deleteNote (mock + store.tsx) now treat a null project as "nothing to bump locally." Notes work on real projects; they just don't bump updatedAt client-side (no backend note endpoint yet — expected until the next slice).

One side effect: the frontend's old mock seed notes are now orphaned — invisible, since no real backend project has those ids. Harmless.

### Verified end-to-end (backend :8000 + frontend :5173)

- Signed up a new user → dashboard, empty list. Logged out (token cleared, confirmed via JS) → bounced to /login. Logged back in → same empty list.
- Logged in as demo@hub.dev → both seeded projects loaded from the backend with correct camelCase fields.
- Isolation: new user saw 0 projects, demo user saw exactly their 2 — confirmed both directions.
- Created a project via Quick Capture, edited a pitch and reloaded — edit survived (confirmed via curl to /projects too), deleted it — confirmed gone via curl.
- Added a note on a real project — works against the mock, no crash.
- Unauthenticated deep-link to /project/<id> redirects to login.

Note: the Chrome extension's synthetic clicks/typing were unreliable on the project-detail page; used native DOM dispatch as a fallback for some verification. Confirmed the flakiness was the automation link, not the app.

Lint, tsc -b, vite build, prettier --check all clean. Nothing committed.

## 23 - Notes backend + frontend wiring

Made notes real, following the projects pattern. 23 backend tests passing (was 15). The mock layer is now gone entirely. Verified end-to-end. Not committed.

### Backend
- app/models/note.py: Note, CreateNoteInput, AddNoteResponse (camelCase via CamelModel, matching openapi.yaml).
- app/db/store.py: NoteRecord dataclass + list_notes/get_note/create_note/delete_note on InMemoryStore. The parent-project "touch" reuses the existing update_project(project_id, owner_id) with no patch fields — it already bumps updated_at and returns the record, so no new bump logic was needed.
- app/routers/notes.py: GET/POST /projects/{project_id}/notes, DELETE /notes/{note_id}. Ownership enforced the same way as projects — 404 whether the project doesn't exist or belongs to someone else. For delete, ownership is checked via the note's parent project (notes have no owner of their own).
- app/main.py: registered the notes router.
- 8 new tests in tests/test_notes.py: CRUD, newest-first ordering, updatedAt bump on both add and delete, auth-required, and three isolation cases (list/add/delete on another user's project all 404, and B's note count untouched by A's failed attempts).

### Frontend
- services/api/real.ts: added realNotesApi (listNotes/addNote/deleteNote), same shape as mockApi had.
- services/api/index.ts: api is now built entirely from realProjectsApi + realNotesApi — no mock references left.
- store.tsx: dropped the if (project) null-guards in addNote/deleteNote — the backend always returns a real project now.

### What was removed
services/api/mock.ts and services/api/seed.ts, deleted entirely (not just trimmed). Once notes went real, nothing was left calling mockApi — the project methods were already dead code from when projects went real, and the note methods became dead by this task. Checked no other file imported from either module before deleting. openapi.yaml still documents attachments as provisional, but there's no Attachment type or UI anywhere in the frontend yet, so there was nothing attachment-shaped to preserve — an empty placeholder file would have been speculative structure AGENTS.md argues against. Whoever builds attachments creates what it needs from scratch, same as notes/projects did.

### Didn't line up
Nothing this time — contract, projects pattern, and the frontend note code all matched cleanly. The one non-obvious piece: update_project with zero kwargs was already exactly the "touch" primitive needed, so no new bump helper was required.

### Verified end-to-end (backend :8000 + frontend :5173, restarted fresh)
- Added a note → reloaded → note persisted (real backend, not mock).
- Dashboard sort: adding the note moved the project to the top.
- Added a note to another project to move it up, then deleted the first note → the first project jumped back to the top, confirming delete also bumps updatedAt server-side.
- Isolation verified against the API with two fresh users: A gets 404 listing or adding a note on B's project, B's note count unaffected.
- Browser clicks/typing worked reliably this session — no JS-dispatch fallbacks needed.

Lint, tsc -b, vite build all clean; 23 backend tests passing. Nothing committed.

## 24 - SQLite storage swap + curated demo seed

Swapped the in-memory store for SQLite via SQLAlchemy, kept database-agnostic for Postgres later. Replaced the demo seed with the ten curated projects. Data now survives restarts. 24 backend tests passing. Frontend untouched. Not committed.

### What was built
- **app/core/config.py** — single settings source: DATABASE_URL, defaults to sqlite:///./hub.db.
- **app/db/orm.py** — SQLAlchemy tables: UserTable, AuthIdentityTable, ProjectTable, NoteTable.
- **app/db/session.py** — engine, session factory, create_tables(), get_db_session() dependency, enable_sqlite_foreign_keys().
- **app/db/store.py** — rewritten: InMemoryStore → Store, backed by a SQLAlchemy Session instead of dicts. Same method surface and same UserRecord/ProjectRecord/NoteRecord DTOs the routers already depended on.
- **Wiring** — InMemoryStore → Store renamed across the routers and auth/dependencies.py. Purely mechanical: only the type import changed per file, router logic byte-identical.
- **Seeding** — seed.py replaced with the ten projects, notes, and varied timestamps. main.py calls create_tables() then seeds only if not store.has_users(), using its own short-lived session.
- **Tests** — conftest.py rebuilt: each test gets its own in-memory SQLite engine (StaticPool, FK enforcement attached), fresh and disposed per test. Forces DATABASE_URL=sqlite:///:memory: before any app import so the startup seed-check never touches a real DATABASE_URL a developer might have set. 24 tests (23 existing + 1 new cascade-delete test).

### Migration story
No Alembic yet. create_tables() runs Base.metadata.create_all() on startup — creates missing tables, does nothing if they exist. Fine while the schema's still moving pre-launch; becomes real Alembic migrations once it stabilizes, since create_all can't alter existing tables (only create new ones).

### Portability tradeoffs (for the eventual Postgres/Neon swap)
1. No SQLite driver package needed (stdlib). Postgres will need `uv add psycopg[binary]`.
2. UUIDs as String(36), not Postgres native UUID.
3. Tags and links as generic JSON, not Postgres JSONB (costs some Postgres-side JSON query/index efficiency later).
4. Free text as unbounded Text, not VARCHAR(n), to avoid a dev-vs-prod silent-truncation trap.
5. Status enum via SQLAlchemy Enum(values_callable=...) — native ENUM on Postgres, VARCHAR+check on SQLite.
6. Timezone-aware timestamps: DateTime(timezone=True) correct on both, but SQLite strips tzinfo on read. A _utc() helper in store.py reattaches UTC when missing. Masks the SQLite gap at the store layer rather than fixing it at the DB — reading timestamps straight off the SQLite file bypassing the store would give naive datetimes.
7. FK enforcement turned on for SQLite (PRAGMA foreign_keys=ON per connection) so dev matches Postgres.

### One behavior change (not just a swap)
The old in-memory delete_project never cleaned up a project's notes (orphaned but unreachable). Real FK enforcement would turn that into an IntegrityError, so added ondelete="CASCADE" on the notes FKs — which openapi.yaml's DELETE /projects/{projectId} already documented but the in-memory store never implemented. Bug fix the swap surfaced, covered by a new regression test. Also: create_user now flushes the user row before the auth-identity insert (SQLAlchemy doesn't auto-sequence the two unrelated inserts).

### Verified
- 24/24 backend tests pass; confirmed no dev hub.db touched by the test run.
- Fresh DB → seed appears: 10 projects, all six statuses (1/2/3/2/1/1), correct scores/tags/links (incl. null-label)/blank fields/target dates, notes in right counts and newest-first.
- Restart → no re-seed: created a project + note via API, restarted against the same hub.db, confirmed 11 projects (not 20), new data intact with original timestamps.
- Touch behavior survives: verified over HTTP and visually — added a note to "Pivot into UX design", watched it jump to the top of the dashboard sort.
- Cascade delete: new test confirms deleting a project with notes succeeds (204) and the notes are actually gone.
- Frontend untouched (git status zero diff).

Note: found a stray uvicorn --reload process (not one it started) that had crashed mid-edit and left hub.db partial; removed the file and re-verified from a clean one.

## 25 - Tier 1 config/security hardening

Moved all security-relevant settings into the config module and added a startup guard that makes shipping the insecure default secret impossible in production, while local dev still needs zero setup. 32 backend tests passing. Frontend untouched. Not committed.

### What moved into config
app/core/config.py is now the single source for everything security-relevant:

| Setting | Env var | Default |
|---|---|---|
| Environment indicator | ENVIRONMENT | local |
| Database URL | DATABASE_URL | sqlite:///./hub.db (unchanged) |
| JWT secret | HUB_JWT_SECRET | dev-only-insecure-secret-change-me (DEV_JWT_SECRET) |
| JWT algorithm | — (fixed constant) | HS256 |
| Token expiry | ACCESS_TOKEN_EXPIRE_MINUTES | 60 |

security.py now imports JWT_SECRET/JWT_ALGORITHM/ACCESS_TOKEN_EXPIRE_MINUTES from config instead of reading os.environ itself — no os import left in that file. No argon2 numeric parameters were hardcoded to begin with (passlib's CryptContext just names the scheme and uses its own defaults), so there was nothing to move; left as-is and flagged rather than inventing config knobs for values that were never set.

### How the prod guard works
require_safe_jwt_secret(environment, secret, dev_default) in config.py — a pure function (takes inputs as arguments defaulting to the module's resolved settings, so tests never touch real env vars). main.py calls it as the first line after imports, before FastAPI() is constructed:
- local/development/dev (case-insensitive): if the secret is still the dev default, print a warning and continue; otherwise silent.
- anything else (production, staging, ...): raise RuntimeError if the secret is empty/unset or still the dev default. Verified it crashes uvicorn at import time (exit 1) before binding a port; setting a real HUB_JWT_SECRET lets it start clean.

One real bug caught during verification: the warning print wasn't showing under uvicorn with output redirected to a file — Python block-buffers print() on a non-TTY stdout. Added flush=True; the warning now appears immediately. Worth knowing since it's the kind of thing that silently disappears in a real deployment's log capture.

### Env vars (documented in .env.example and README)
ENVIRONMENT, DATABASE_URL, HUB_JWT_SECRET, ACCESS_TOKEN_EXPIRE_MINUTES — table with defaults and prod-required flags in the README, same four with explanatory comments in the new .env.example. Only HUB_JWT_SECRET is marked required in production. Generate one with: python -c "import secrets; print(secrets.token_urlsafe(64))"

### Verified
- 32/32 tests pass (24 existing + 8 new in tests/test_config.py: local-with-dev-secret, local-missing-secret, the development/dev aliases, case-insensitivity, production-with-dev-secret, production-missing-secret, other-non-local-env, production-with-a-real-secret).
- Frictionless local dev: started with a fully wiped environment (env -i, zero vars) — starts clean, warning printed, seeded demo login works, all 10 projects load.
- Production guard: ENVIRONMENT=production with no secret → crashes at import with the exact RuntimeError, before serving anything. Adding HUB_JWT_SECRET → starts and serves fine.
- Nothing hardcoded in security.py: confirmed by grep.

Frontend untouched, no rate-limiting/account caps (out of scope). Nothing committed.

## 26 Write/load error handling + unified optimism

Added error handling to all write and load paths, surfaced load errors with retry, and standardized on pessimistic writes everywhere. Verified all failure paths in the browser. Not committed.

### What changed

New files:
- lib/toast.ts — a toastManager usable outside React so the store itself can trigger toasts, plus notifyError().
- lib/errors.ts — toUserMessage(err, fallback) (backend's curated HttpError.message when available, friendly fallback otherwise) and reportError(err, fallback) (calls notifyError, except for a 401 — see below).
- components/ui/toaster.tsx — the visual toast, styled to match the app's card/border/shadow language. Mounted once in App.tsx.

Store (store.tsx) — every write (create/update/deleteProject, add/deleteNote) now waits for the API, updates projects state only on success, calls reportError + re-throws on failure. The existing error state is now actually consumed.

Dashboard — added an ErrorState component (same visual pattern as EmptyState) shown instead of the grid/stats/toolbar when the load fails, with a "Try again" that calls refresh().

Project detail — save() returns Promise<boolean>; the four fields with local draft state (name, pitch, description, nextAction) revert to project.<field> on failure. Status/scores/target-date/tags/links needed no revert (directly controlled by project.*, so a failed save already leaves them showing the correct unchanged value). handleDelete catches and resets the confirm-delete UI on failure. Same load-error/retry treatment extended to the "not found" branch.

Notes panel — remove() flipped from optimistic to pessimistic (the one inconsistent case): waits for deleteNote to resolve before removing from local state, with a deletingId guard disabling the button mid-flight.

Quick capture — logic was already correct (dialog stays open, data intact on failure); documented why.

### Optimistic-update convention: pessimistic, everywhere
Every write waits for the server before the store's projects state changes. Reasons: it satisfies "never show data that didn't save" by construction (state is backend-confirmed, nothing to roll back); four of five paths were already pessimistic (only note-deletion was the outlier, the smaller/lower-risk change); individual writes are cheap and inputs already echo keystrokes immediately, so the app stays responsive without full optimistic-rollback machinery.

### How errors surface
- Writes: a toast (bottom-right, auto-dismiss 6s, dismissible) with a plain-language message — backend's curated string or a generic network fallback. The four local-draft fields also revert to last-known-good.
- Loads: dashboard and project-detail's "not found" branch show a dedicated error state with the message and a "Try again".
- 401 mid-write: reportError skips toasting a 401 — already routed to logout/login by the existing handler, so no confusing double message.

### Tech debt
Removed the entire Robustness section and the write-optimism line. Updated the "duplicated empty-state layouts" entry from three to four, since the new load-error state is a fourth divergent-but-similar shape (didn't want to leave it stale).

### Verification
Tested with the backend stopped and, more precisely, with window.fetch overridden to fail one specific request while everything else hit the real backend (the task's suggested alternative) — this sidestepped an unrelated environment quirk (this session's tab logs out quickly whenever the backend becomes unreachable at all; confirmed via code inspection and fetch instrumentation that nothing in the app polls or reloads on its own).

Confirmed live:
- Create failure: toast "Couldn't create that project. Try again.", dialog stays open with typed name intact, still exactly 10 projects (no phantom).
- Edit failure: toast "Couldn't save that change. Try again.", title reverted to its saved value.
- Note-delete failure: toast "Couldn't delete that note. Try again.", note stayed in the list.
- Dashboard load failure: full ErrorState with message and a working "Try again" that recovered once the override was removed.
- Happy path: login, load, a real note delete, and reload all worked throughout.

Also fixed a bug in its own test scripts (React onBlur fires via native focusout, not blur) — irrelevant to app code. Lint 0/0, tsc, build, prettier all clean. Nothing committed.

## 27 - Dark mode persistence

Theme now persists across reloads, respects system preference on first load, applies before paint (no flash), and the theme-color meta follows the toggle. Not committed.

### What the mechanism looks like now
- **index.html** — a small inline `<script>` in `<head>`, before any stylesheet or app code, runs synchronously: reads localStorage['hub.theme']; if unset, falls back to matchMedia('(prefers-color-scheme: dark)'); if dark, adds the dark class to `<html>` and sets an approximate dark theme-color. Wrapped in try/catch (falls back to light if storage/matchMedia unavailable). This eliminates the flash — the class is on `<html>` before the browser paints.
- **src/lib/theme.ts** (new) — source of truth from React's side: getStoredTheme/setStoredTheme (try/catch localStorage) and updateThemeColorMeta(), which reads the actual computed background-color off `<body>` and writes it into the meta tag, so it can't drift from the palette in index.css.
- **app-header.tsx's useTheme** — initial React state reads off the DOM (does `<html>` have the dark class) rather than re-deriving, trusting the inline script's resolution. toggle() flips state and persists the explicit choice. An effect applies the class and calls updateThemeColorMeta() whenever dark changes, so the meta updates on toggle, not just load. Toggle button untouched.

### Didn't line up
- The classic "normalize color via canvas fillStyle" trick (to force rgb() for theme-color) no longer works in current Chrome — canvas now preserves oklch() too. Added it defensively, checked the actual output, found it did nothing, removed it. theme-color accepts any valid CSS color and oklch() is supported by the browsers that read this meta (Chrome/Android, Safari/iOS), so it's passed through as-is. Simpler.
- No access to true OS-level prefers-color-scheme emulation (no CDP media-emulation). Machine's real preference is light; confirmed live that a cleared preference resolves to light. For the dark-OS branch, verified the resolution expression in isolation with matchMedia mocked for all four combinations (no-stored+dark, no-stored+light, stored-light+dark-system, stored-dark+light-system) — all correct, including explicit-choice-wins. Algorithm-level, not a true dark-OS end-to-end test; flagged rather than claimed.

### Verified
- Toggle dark → reload: stays dark (html class, meta, screenshot).
- Toggle light → reload: stays light (same checks).
- Cleared preference + real (light) system pref → starts light, live.
- Dark-system branch verified in isolation (couldn't drive a real dark-OS reload).
- theme-color meta changes on toggle both directions, matching light/dark --background exactly.
- Lint 0/0, tsc, build, prettier clean.

## 28 - Consistency cleanup batch (5 items)

Worked through all five consistency items one at a time, lint/tsc/build clean after each. Behavior-preserving throughout. Verified in-browser. Tech-debt updated. Not committed.

### Item 1 — Shared empty/error-state component
Added components/ui/empty-state.tsx exporting EmptyState with a variant ('page' | 'panel', deriving heading tag/size and the dashed-border box), a tone ('neutral' | 'danger'), and optional icon/message/action. Replaced all four call sites: not-found.tsx, dashboard's empty/no-matches state, dashboard's load-error state, project-detail's not-found/load-error branches. All four verified live, including the danger-tone error state (forced via a temporary fetch override) and its retry button.

### Item 2 — Back-to-dashboard button
project-detail's "All ideas" link now uses buttonVariants({ variant: 'ghost', size: 'sm' }) instead of raw classes. Confirmed the hover background-pill state now appears (it didn't before).

### Item 3 — Rating widget
Kept ScorePicker, removed RatingInput. Reason: ScorePicker sets aria-pressed per button, conveying selection state to assistive tech; RatingInput only had aria-label with no pressed-state signal — a real accessibility gap, not cosmetic. Merged RatingInput's one advantage (the numeric "X/5" readout) into ScorePicker's header row before deleting (grep-confirmed zero remaining references first). Migrated project-detail's three rating controls; edit-and-save confirmed live (Potential 3→5, "Updated just now", reverted).

### Item 4 — Card primitive
project-detail's ratings, target-date, tags, and links sections now use the Card primitive instead of hand-rolled border/bg divs, regaining shadow-sm. The "Next action" accent box was deliberately left alone (different intentional treatment). Layout classes preserved.

### Item 5 — Dead fallback branches
formatDate no longer accepts null; its null-check return removed. In project-detail.tsx, removed the due useMemo entirely and inlined formatDate(project.targetDate) inside the existing project.targetDate ? guard (its only call site), which also dropped useMemo from imports. Verified with-date and no-date cases render correctly. daysUntil's null branch correctly left alone (dashboard's target-date sort uses it).

### Didn't line up / notes
- The tech-debt "no date" placeholder note was left untouched as instructed. Flag: Item 5 removed the branches it referenced, so its literal wording is now stale, but the underlying product question (show nothing vs "None" when there's no date) is still open.
- project-detail's not-found branch got proper buttonVariants styling for free via the Item 1 migration — it had been hand-rolling raw classes too.
- Self-corrected mid-implementation on Item 5: first pass only narrowed formatDate's type but left a dead else-branch; caught it in final verification and removed it properly.

### Verification
Each item ran lint (0/0)/tsc/build individually as it landed; final suite clean. Full click-through via the extension: dashboard normal, no-matches, clear-filters recovery, danger-tone error + retry, two project-detail pages (with/without target date), not-found page — all confirmed. The true zero-projects "Nothing captured yet" variant wasn't exercised live (would require deleting all seed data); its logic is identical to the confirmed no-matches branch with different icon/copy/action, so relying on code review there.

tech-debt.md: five resolved Consistency bullets removed (and the empty section header). Notes and Open-questions untouched. Servers/tab shut down. Nothing committed.

## 29 - Stale + quick-win badges

Added isStale/isQuickWin helpers, a shared IndicatorBadge, and wired both badges into the project card. Added Vitest (repo had no frontend test setup) with 19 unit tests. Verified in-browser. Not committed.

### Helper logic (lib/project-utils.ts)
- isQuickWin(p): status ∈ {Inbox, Exploring, Active} && excitement >= 4 && effort <= 2
- isStale(p, now = new Date()): status ∈ {Active, Exploring} and (now - updatedAt) >= 30 days. `now` injectable for deterministic tests.

### Badges
New IndicatorBadge (components/indicator-badge.tsx) mirrors StatusBadge's exact pill shape (rounded-full, dot + text, same padding/type scale) as one shared piece — a Quick win and Stale badge are the same shape with different colors, and duplicating StatusBadge's markup would recreate the pattern the last cleanup removed. Wired into project-card.tsx next to the status pill, wrapped in flex-wrap so it degrades if a card shows all three. Colors: quick win = lime (positive, distinct from Active's emerald and Parked's amber); stale = zinc/gray (deliberately muted, not rose/amber, per "gentle nudge, not alarming").

### Tests
Repo had no test framework, so stopped and asked — you chose Vitest. Added it as a devDependency, a pnpm test script, and lib/project-utils.test.ts with 19 cases: quick-win at/around the excitement-4/effort-2 thresholds, excluded for all three closed statuses; stale at/around the 30-day boundary, excluded for Inbox/Parked/Killed/Graduated; combined both/neither. All pass; lint, build, format:check clean.

### Seed projects, actual result
- Quick win: only "Read 24 books this year" (Active, excitement 4, effort 2 — exactly on threshold).
- Stale: none — the only old seed projects are Parked/Killed/Graduated, correctly excluded. Verified live, then confirmed the stale badge renders by client-side-spoofing one response (non-destructive, restored after) to backdate "Train for a half-marathon" 40 days + drop effort to 2 → correctly showed Active + Quick win + Stale on one line, no overflow.
- Confirmed Parked/Killed/Graduated never show stale even though three are 21–130 days old — correct per spec.

### Didn't line up
The verification note expected "Train for a half-marathon" and "Pivot into UX design" to look quick-win-ish; neither qualifies under the exact definition (both have effort 4-5). And no Active/Exploring seed project is naturally 30+ days stale. So with real seed data only one badge shows anywhere today (quick win on "Read 24 books this year"); everything else was verified by temporary fetch-spoofing. If you want the seed to actually exercise the stale case, that's a seed-data change (backdating an Active project's updatedAt) not made since it wasn't asked for.

## 30 - Seed tweak: exercise both badges in the demo

Seed-data only (backend/app/db/seed.py). No badge logic or frontend touched. 32 backend tests pass, seed syntax valid. Not committed.

### Resulting badge map
| Project | Status | Badges |
|---|---|---|
| Dial in a sourdough starter | Parked | none |
| Etsy shop for my prints | Exploring | Quick win + Stale |
| Automate my budgeting spreadsheet | Active | Stale |
| Train for a half-marathon | Active | none |
| Pivot into UX design | Exploring | none |
| Build my portfolio site | Inbox | none |
| Read 24 books this year | Active | Quick win (unchanged) |
| Learn enough Spanish for the trip | Parked | none |
| Start a podcast with the group chat | Killed | none |
| Declutter and sell old furniture | Graduated | none |

All six statuses still represented at the same counts (Inbox 1, Exploring 2, Active 3, Parked 2, Graduated 1, Killed 1).

### What changed
- Etsy shop for my prints (both-badges): effort 3 → 2 (excitement stays 4, clears quick-win), updatedAt 9d → 40d ago. Notes and createdAt pushed back proportionally (createdAt 45 → 70d; notes 30/18/9 → 61/49/40d) so every note still falls after creation and no later than the new updatedAt.
- Automate my budgeting spreadsheet (stale-only): scores left alone (already fails quick-win), updatedAt 2d → 40d ago, createdAt 14 → 55d, notes 10/2 → 48/40d. Target date (~3 weeks out) left, giving a "deadline coming, no progress" story.
- Comments above both blocks updated to match the new narrative. Nothing else touched.

### Recreate the local DB
```
cd backend
rm hub.db
uv run uvicorn app.main:app --port 8000
```
(seeding only runs against an empty DB, so deleting hub.db is required — the server re-seeds on startup)

## 31 - Pre-deploy read-only review

All objective checks green. No correctness bugs, no untracked security holes, no debug cruft. Frontend/backend contract matches openapi.yaml across auth, projects, notes. Findings are mostly polish plus two decisions. No files modified.

### Objective checks
- Frontend: eslint 0/0; tsc -b && vite build clean; vitest 19/19 pass.
- Backend: pytest 32/32 pass (4 deprecation warnings from third-party libs only — httpx/starlette, passlib/crypt, argon2-cffi — not app code).

### Fix before deploy
1. **CORS hardcoded to localhost** — main.py:16-22. allow_origins is localhost:5173 only. Not a security bug (safe restrictive default) but a functional blocker: once the frontend deploys, requests fail CORS until prod/staging origins are added. Not covered by tech-debt's generic Deploy bullet.
2. **Spec-required observability doesn't exist and isn't tracked as deferred** — spec §2 lists error tracking (Sentry) + dashboards as a v1 layer, not in §9 Deferred. No Sentry SDK either package; no React error boundary in App.tsx, so a render-time bug white-screens with only a console log. Decide: add it, or add to tech-debt as a deliberate deferral so it's not silently missing.

### Real findings — can wait
Correctness:
- auth.py:15-27 — register() does check-then-insert with no try/except around the unique-constraint violation; users.email is unique at the ORM level, so a race between two simultaneous same-email registrations would surface as a 500 instead of the documented 409. Narrow window, easy to close.
- project.py:20 — Link.url is str while openapi.yaml documents format: uri; not enforced server-side. Cosmetic.

Consistency (partly slipped back after the cleanup pass):
- Inconsistent void on fire-and-forget async calls in JSX handlers: project-detail.tsx:133,138,149,155 use void save(...); :245,302,308,314,325 call save(...) bare. Same split in notes-panel.tsx and quick-capture-dialog.tsx. No runtime difference (all handle their own errors); inconsistent within single files.
- stats-row.tsx:19-27 hardcodes the six-status order instead of deriving from the exported STATUSES. DRY nit.

Dead code:
- theme.ts:16-23 — getStoredTheme() exported, never called (app-header reads the DOM class directly). Safe to delete.
- auth.ts:38-40 — authApi.logout() exported, never called; the real logout path duplicates the one-line clearToken() directly. Wire it up or delete.

Doc drift:
- AGENTS.md still describes the API layer as an in-memory mock (services/api/mock.ts) — that file no longer exists; the layer is real HTTP (real.ts).
- openapi.yaml's top description still says "the backend does not exist yet."
- tech-debt.md still lists stale/quick-win surfacing as unbuilt — shipped. And its Notes section says the "no date" branches are "currently unreachable" — the cleanup pass deleted them outright; only the underlying product question (what to show for no date) is still open.

Spec alignment:
- seed.py's demo projects differ from spec §11's listed projects — reads like a deliberate design upgrade, not drift; confirm intentional.
- Confirmed the only deferrals present are attachments, PWA, Postgres/Neon, rate-limiting/caps — matching tech-debt exactly. No other half-built or silently-missing v1 features beyond observability above.

Tests:
- Backend 32: strong auth + isolation coverage. Minor gaps: case-insensitive duplicate-email registration untested; expired-but-well-formed JWT untested (only a garbage token is).
- Frontend 19: all for isStale/isQuickWin. Nothing else (auth forms, store writes, dashboard filtering/sorting, project-detail) is tested. Consistent with the project's stage; "19 tests" doesn't imply broad coverage.

### Already tracked in tech-debt — confirmed still accurate, not re-flagged
- Rate-limiting, account/project caps — neither exists.
- "Logout-on-any-failure too aggressive" — confirmed, exact spot: auth.tsx:32-44. On app load, if a token exists, getCurrentUser()'s .catch() clears the token on ANY rejection, not just a real 401, so a network blip/cold-start during that check logs the user out. (http.ts:66's global 401 handler is correctly scoped; this is specifically the app-mount check.)
- Postgres portability tradeoffs, no-Alembic-yet — accurate, unchanged.

No files modified.

## 32 - Pre-deploy cleanup batch

Error boundary added and verified, two dead exports resolved, doc drift fixed, two deploy-time deferrals now tracked. All checks green. Not committed.

### 1. Error boundary (verified working)
New components/error-boundary.tsx: a class component (getDerivedStateFromError + componentDidCatch) wrapping the entire app in App.tsx (around the loading/unauthenticated/authenticated tree and the Toaster, so it catches crashes anywhere, not just routed pages). On catch it logs to console.error (placeholder until Sentry) and renders the existing EmptyState in page/danger mode: "Something went wrong" + explanation + a Reload button (window.location.assign('/')).

Verified live: temporarily threw inside DashboardPage, confirmed the fallback rendered instead of a white screen, confirmed componentDidCatch's console.error fired with the error + component stack, confirmed Reload does a real navigation, then removed the throw and confirmed normal rendering. dashboard.tsx has no net diff.

### 2. Dead exports
- getStoredTheme() (lib/theme.ts) — deleted. Zero references.
- authApi.logout() (services/api/auth.ts) — kept and wired up instead of deleted. auth.tsx's logout now calls authApi.logout() instead of duplicating clearToken() inline. Reasoning: AGENTS.md's rule is all data access goes through services/api/; the inline clearToken() was the kind of around-the-layer call that rule prevents, so routing through the api layer is the more correct fix. (The other clearToken() in auth.tsx — boot-time invalid-token cleanup — is a different concern, left as-is.)

### 3. Doc drift fixed
- AGENTS.md: API-layer paragraph rewritten to describe real.ts/http.ts as the actual state; no more mock.ts reference.
- openapi.yaml: top description no longer says "the backend does not exist yet"; now says the backend implements the contract, attachments still provisional.
- tech-debt.md: removed the shipped stale/quick-win roadmap entry; rewrote the Notes entry so it no longer claims the no-date branches are unreachable (they were deleted), keeping the open product question.

### 4. New tracked deferrals (tech-debt.md)
- CORS origins hardcoded to localhost in main.py; deployed frontend origins must be added at deploy or requests fail CORS.
- Observability/Sentry not wired; error boundary covers the frontend-crash half, backend/error-tracking deferred to deploy.

Verification: lint 0/0, tsc, build, test 19/19, format:check — all clean. Deferred items (register race, void-consistency, stats-row, Link.url) left untouched as instructed. Nothing committed.

## 33 - Frontend critical-logic tests

Added logic tests for the store, auth flow, http/token layer, and remaining pure helpers. 71 tests total (was 19), all passing. One dep added (jsdom, per the earlier decision). No app code changed. Not committed.

### Added (all in frontend/)
- **src/lib/render-hook.tsx** — a small hand-rolled renderHook/flush helper (real React createRoot + act, no RTL) to mount StoreProvider/AuthProvider and read hook state across renders.
- **src/store.test.tsx (13)** — initial load (success/failure); each write path (create/update/delete project, addNote, deleteNote): success updates state correctly, failure leaves projects referentially unchanged and rejects. Plus getProject.
- **src/auth.test.tsx (8)** — on-mount token check (no token / valid / invalid, including token cleared on invalid); login/register success and failure; logout.
- **src/services/api/token.test.ts (6)** — get/set/clear round-trip; all three degrade to a no-throw no-op when Storage methods throw.
- **src/services/api/http.test.ts (11)** — bearer attached/omitted/skipAuth; string and FastAPI-array detail parsed into HttpError; non-JSON fallback to status text; onUnauthorized fires only on a 401-with-token; 204/200 handling.
- **Extended project-utils.test.ts (+15)** — opportunityScore, daysUntil (null/future/past/same-day boundary), formatRelative (all buckets), formatDate (date-only vs full ISO).

Total 71 tests passing. lint 0/0, build clean, format:check clean.

### Dependency
jsdom as a devDependency (your call earlier). Store/auth logic lives entirely in React hooks, which only run during a render, so there was no way to exercise them without a renderer. Scoped via a per-file // @vitest-environment jsdom pragma so the rest of the suite stays in the faster node environment.

### Left for the component pass
Anything rendering actual UI, DOM queries, or user interaction (clicks, forms) — none of that is here.

### Hard to test / design notes
Nothing flagged as a design concern. The pessimistic-write pattern made the "state unchanged on failure" tests trivial (assert the same array reference); the auth on-mount logout-on-any-failure behavior was straightforward to pin as-is without changing it.

### Note
git status shows _docs/prompts_backend.md and _docs/results_backend.md modified on disk; the agent didn't touch either (didn't edit _docs/ as code). Flagged as possibly something else in the environment writing to them — verify before committing.

## 34 - Deep component + user-flow tests

157 tests passing (71 prior logic + 86 new component/flow). Queried by role/label/text, mocked at the boundary, no styling assertions, no app code changed. Not committed.

### Setup changes
- Added @testing-library/react, @testing-library/user-event, @testing-library/jest-dom, jsdom as devDependencies.
- vite.config.ts now imports defineConfig from vitest/config and sets test: { environment: 'jsdom', setupFiles: ['./src/test-setup.ts'] } — jsdom is now the global default.
- src/test-setup.ts wires jest-dom matchers plus an explicit afterEach(() => cleanup()). That second part isn't optional: this repo keeps test.globals off (explicit imports from 'vitest'), so RTL's auto-cleanup never fires; without it, every test after the first in a file leaked the prior render's DOM into the next query. Flagging as a trap for future test files here.
- Removed the three per-file // @vitest-environment jsdom pragmas; confirmed the original 71 still pass unchanged.

### Per-screen coverage (api/authApi mocked per-file via vi.hoisted; real providers do the work)
- Login/Signup: render, valid submit → authenticate & navigate, backend error shown verbatim, disabled-until-valid, disabled-while-submitting, cross-links.
- Dashboard: pending/error+retry/empty/no-matches+clear/populated; status-chip, tag-chip, search filtering; name and lowest-effort sorting; quick-win/stale badges scoped to the right card only.
- Project detail: field rendering, blur-save vs no-op-blur (pitch, description, next-action, name), save-failure revert, immediate-save fields (status, scores, target date), tag add/remove, labeled+unlabeled link add/remove, two-step delete → navigate, cancel, not-found and load-error branches.
- Quick capture: open/closed, autofocus name field, disabled-until-name, create → close, comma-tag splitting, "Capture & open" → navigate, Enter-to-submit, stays open with data intact on failure, cancel resets draft.
- Notes panel: list, add (button and ⌘/Ctrl+Enter), draft kept on add-failure, two-step delete → remove, cancel, pessimistic "stays in list on delete-failure".
- Error boundary: normal children render; throwing child renders fallback.
- App header: user name vs email fallback, capture wiring, dark-mode toggle + label flip, sign-out wiring.
- Light coverage on StatusBadge, IndicatorBadge, ScorePicker, StatsRow, DashboardToolbar, NotFoundPage — conditional/callback logic only, no styling.

### Full-flow tests (2)
- Auth → dashboard: login page → real login → dashboard shows the user's projects.
- Capture → see it → edit it: empty dashboard → quick-capture → card appears → open detail → edit pitch → blur persists.
(The optional third was skippable without loss.)

### Skipped, with reasons
- Full Tab-cycle focus-trap in quick-capture: base-ui's trap depends on layout/visibility jsdom doesn't compute, so a test would be fake or flaky. Kept the solid assertion: name field focused on open.
- StatsRow active-chip "looks active" state: the active filter chip has no aria-pressed/aria-current, only a class change — tested the onSelect callback instead, and flagging it as a minor accessibility gap worth a follow-up.
- Skeleton/loading visuals: no accessible role/text, so only asserted the negative (final content not yet showing) rather than touching classNames.

### Worth knowing (not a bug, not fixed)
base-ui's Dialog keeps content in the DOM (hidden) while closed rather than unmounting. A loose getByRole for the Capture button matched both the header's real button and the closed dialog's hidden one; fixed by scoping the query to the header landmark. Remember when querying broadly across a page with the dialog mounted.

No app code changed. lint 0/0, tsc clean, build clean, format clean.
