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

## 7

## Codebase Review — No files changed

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

Everything is in place, nothing committed. Here's the summary:

## Summary

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

Everything's clean and nothing committed. Here's the per-item summary:

## Summary

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

Everything's clean — lint, typecheck, and build all pass, and only `pages/project-detail.tsx` was touched.

## Summary

**Root cause:** the next-action callout used `<Input>` — a native single-line `<input>` element. Native inputs can never wrap their value across multiple lines regardless of CSS (no `white-space`/`min-width:0` fix can change that); they just clip/scroll internally. That's exactly what the screenshot showed at 375px: text cut off mid-word, no page-level overflow. It wasn't a flexbox or whitespace bug — the field was structurally the wrong kind of control for text that needs to wrap.

**Fix (`pages/project-detail.tsx` only):**
- Swapped the `<Input>` for a native `<textarea rows={1}>`, styled to match the original input's look exactly for short text (same padding, border, focus states).
- Added a `useLayoutEffect` that syncs the textarea's height to its `scrollHeight` whenever `nextAction` changes — this is the textbook correct use of an effect (direct DOM mutation to sync with an external system), not a React-state effect, so it doesn't trip the `set-state-in-effect` rule from the recent lint cleanup.
- This auto-grows the box to fit however many lines the text wraps to, and shrinks back down for short text, while typing.

**Verified** at 320px, 375px, and 390px with a long next-action string: `document.documentElement.scrollWidth === window.innerWidth` at all three (zero horizontal page overflow), and the textarea's `scrollHeight ≈ clientHeight` (fully expanded, no clipped/hidden lines) — confirmed visually via screenshots too. Also confirmed the normal case (short, single-line next-action text) still renders at its original compact height with no visual regression, and `pnpm lint` / `tsc` / `pnpm build` all pass clean. Nothing else was touched.

---

## 11

Everything's clean and only the two intended files were touched. Nothing committed.

## Summary

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

All clean — lint 0/0, `tsc` clean, `pnpm build` clean, and only `pages/project-detail.tsx` was touched. Nothing committed.

## Summary

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