# Tech debt

Known issues deferred for later, from the read-only code review and subsequent work. None are bugs or blockers; they're consistency, robustness, and roadmap items to address when convenient (ideally when already working in the relevant file, or as noted, alongside the backend).

## Consistency

- **Three duplicated empty-state layouts** → extract one shared component. Appears in the not-found page, the dashboard empty state, and the project-detail not-found branch.
- **Duplicated back-to-dashboard button** → project-detail hand-rolls it with raw classes instead of using `buttonVariants`, so it misses the hover/focus-visible/transition states.
- **Three rating-widget implementations with diverging accessibility** → standardize on one (`ScorePicker` vs `RatingInput`); they use different `aria` patterns.
- **Card visual drift** → project-detail section cards reuse the border/bg recipe but drop `shadow-sm` and don't use the `Card` primitive (this is why `card.tsx` was kept).
- **Two data-flow conventions** → notes call the api layer directly from the component instead of going through the store like all project CRUD does.
- **`getProject` seam unused** → detail page uses the store's synchronous filter over the bulk-loaded list instead of the api's single-item get. Revisit with the backend (a real backend wants a single-item GET).
- **Two write-optimism strategies** → note deletion updates local state before the API call resolves; project field edits wait for the call to resolve first. Pick one convention.
- **Dead `'-'` fallback branches** → `formatDate`'s null-`iso` return in `lib/project-utils.ts` and the `: '-'` else in the `due` useMemo in `project-detail.tsx` are both unreachable (callers guard on `project.targetDate` / early-return on `!project`). Harmless; simplify when next in these files. (Audit consistency #8.)

## Robustness (do with the backend, when failures are testable)

- **No error handling on write paths** → `createProject` / `updateProject` / `deleteProject` in the store have no try/catch, and several `void save(...)` / note calls are fire-and-forget. Invisible with the mock (always resolves); becomes silent failures or unhandled rejections once real requests can fail.
- **Dead error state** → the store tracks `error` but no component reads it, so a failed load shows nothing to the user. Surface it.

## Accessibility / UX

- *(done)* Dialog focus trap — fixed in batch 3.
- *(done)* Note-delete confirmation — fixed in batch 3.

## Spec / roadmap (not debt, remaining build work)

- **Attachments** — spec §3/§4.3 define an attachments table and project-detail UI; none exists yet. (Milestone 5.)
- **PWA installability** — spec calls for installable-as-PWA; no manifest or service worker yet. (Milestone 6.)
- **Dashboard "stale" and "quick-win" surfacing** — spec §4.2; sorting exists but there's no dedicated stale badge or quick-win callout distinct from the opportunity sort.
- **Dark mode persistence** — resets to light on reload and ignores system preference; `<meta name="theme-color">` is also static and won't follow the toggle.
- **Login / auth + real backend** — the whole next phase (spec §4.1).

## JWT signing secret is a hardcoded dev default

The JWT signing secret defaults to a hardcoded string in backend/app/auth/security.py,
overridable via the HUB_JWT_SECRET env var. Fine for local dev, but a security hole if
it ever reaches a deployed/shared environment: anyone who knows the secret can forge
valid auth tokens for any user.

Required before any deployment:
- Move the secret (and JWT expiry, and other config) into a proper settings module in
  app/core/, read from the environment with no insecure fallback in non-local contexts.
- Generate a strong random secret per environment (dev/prod separate), stored as a real
  secret (env var / secrets manager), never committed.
- Fail fast: the app should refuse to start in a non-local environment if HUB_JWT_SECRET
  is unset, rather than silently using the dev default.

Related: app/core/ is currently empty; this is the first thing that needs it. Token
expiry (currently hardcoded 60 min) and the argon2 parameters should move there too.

## Notes

- A minor deviation from the em-dash pass: the `'—'` "no date" placeholder in `lib/project-utils.ts` (and one spot in `project-detail.tsx`) was replaced with an empty string rather than punctuation. Both branches are currently unreachable. Decide later whether it should show something like "None" instead.
