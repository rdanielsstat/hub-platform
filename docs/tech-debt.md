# Tech debt

## Bugs

- Mobile viewport is zoomed in after login. The login screen is fine; the
  authenticated layout renders wider than the screen until you pinch out.

## Security

- Rate-limiting on signup and login.
- Account and project caps per user.
- Cap password length on `/auth/login`. Registration caps at 256 characters,
  login does not, and argon2 is slow by design.
- Decide what to do about the writable demo account. Retiring it means
  removing that environment's entry from `demo_passwords` and re-applying.
- Wire up observability. Nothing reports errors, frontend or backend.

## Migrations

- Move to Alembic. `create_all()` creates missing tables but cannot alter
  existing ones.

## Deferred features

- Attachments. Needs an upload-mechanism decision (direct-to-S3 presigned vs
  proxied) first.
- PWA installability. No manifest or service worker.

## Open questions

- Logout-on-any-failure may be too aggressive. The app routes to login
  whenever the backend is unreachable, not only on a real 401. Neon sleeps
  after five minutes, so the first request after idle is slow. Not yet
  root-caused; also entangled with an environment quirk seen in the automated
  browser tab.
