# Tech debt

Known issues deferred for later, from the read-only code review and subsequent work. None are bugs or blockers; they're consistency, robustness, and roadmap items to address when convenient (ideally when already working in the relevant file, or as noted, alongside the backend).

## Consistency

- **Three duplicated empty-state layouts** → extract one shared component. Appears in the not-found page, the dashboard empty state, and the project-detail not-found branch.
- **Duplicated back-to-dashboard button** → project-detail hand-rolls it with raw classes instead of using `buttonVariants`, so it misses the hover/focus-visible/transition states.
- **Three rating-widget implementations with diverging accessibility** → standardize on one (`ScorePicker` vs `RatingInput`); they use different `aria` patterns.
- **Card visual drift** → project-detail section cards reuse the border/bg recipe but drop `shadow-sm` and don't use the `Card` primitive (this is why `card.tsx` was kept).
- **Two write-optimism strategies** → note deletion updates local state before the API call resolves; project field edits wait for the call to resolve first. Pick one convention.
- **Dead `'-'` fallback branches** → `formatDate`'s null-`iso` return in `lib/project-utils.ts` and the `: '-'` else in the `due` useMemo in `project-detail.tsx` are both unreachable (callers guard on `project.targetDate` / early-return on `!project`). Harmless; simplify when next in these files.

## Robustness

- **No error handling on write paths** → `createProject` / `updateProject` / `deleteProject` in the store have no try/catch, and several `void save(...)` / note calls are fire-and-forget. Now that requests hit a real backend and can fail, these become silent failures or unhandled rejections. Worth doing now that failures are real and testable.
- **Dead error state** → the store tracks `error` but no component reads it, so a failed load shows nothing to the user. Surface it.

## Security (before deploy / before first paid user)

- **Rate-limiting on signup/login** → open registration on a pay-per-use backend is an abuse surface. Not needed on localhost; add before the backend is publicly reachable.
- **Account / project caps per user** → a simple cap while costs are unguarded, to avoid a single actor running up usage. Decide alongside rate-limiting.

## Portability tradeoffs (for the eventual Postgres/Neon swap)

1. No SQLite driver package needed (stdlib). Postgres will need `uv add psycopg[binary]`.
2. UUIDs as String(36), not Postgres native UUID.
3. Tags and links as generic JSON, not Postgres JSONB (costs some Postgres-side JSON query/index efficiency later).
4. Free text as unbounded Text, not VARCHAR(n), to avoid a dev-vs-prod silent-truncation trap.
5. Status enum via SQLAlchemy Enum(values_callable=...) — native ENUM on Postgres, VARCHAR+check on SQLite.
6. Timezone-aware timestamps: DateTime(timezone=True) correct on both, but SQLite strips tzinfo on read. A _utc() helper in store.py reattaches UTC when missing. Masks the SQLite gap at the store layer rather than fixing it at the DB — reading timestamps straight off the SQLite file bypassing the store would give naive datetimes.
7. FK enforcement turned on for SQLite (PRAGMA foreign_keys=ON per connection) so dev matches Postgres.

## Migrations

- **No Alembic yet** → tables are created on startup via `create_all()` (creates missing tables, can't alter existing ones). Fine while the schema is still moving pre-launch. Once it stabilizes, convert to real Alembic migrations so schema changes are tracked and reversible.

## Spec / roadmap (not debt, remaining build work)

- **Attachments** — spec §3/§4.3 define an attachments table and project-detail UI; none exists yet. Deferred; not critical for v1. Needs an upload-mechanism decision (direct-to-S3 presigned vs proxied) before building.
- **PWA installability** — spec calls for installable-as-PWA; no manifest or service worker yet.
- **Dashboard "stale" and "quick-win" surfacing** — spec §4.2; sorting exists but there's no dedicated stale badge or quick-win callout distinct from the opportunity sort.
- **Dark mode persistence** — resets to light on reload and ignores system preference; `<meta name="theme-color">` is also static and won't follow the toggle.
- **Deploy** — Vercel (frontend) + Neon Postgres (backend). Triggers the Postgres swap above and the security items above.

## Notes

- A minor deviation from the em-dash pass: the `'—'` "no date" placeholder in `lib/project-utils.ts` (and one spot in `project-detail.tsx`) was replaced with an empty string rather than punctuation. Both branches are currently unreachable. Decide later whether it should show something like "None" instead.
