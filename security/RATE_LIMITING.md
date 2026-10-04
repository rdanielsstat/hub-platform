# Rate limiting and usage caps

What limits the API enforces, where, and what each layer does and does
not protect against. The config reference is in `backend/README.md`
("Rate limits", "Usage caps"); this file is about the threat model and
the known gaps.

## Layers

| Layer | Limit | Scope | Enforced by |
|---|---|---|---|
| Login | 5 attempts / minute | Per client IP (IPv6 per /64), `POST /auth/login` | `backend/app/auth/rate_limit.py` |
| Sign-up | 3 attempts / minute | Per client IP, `POST /auth/register` | same |
| Error reports | 30 reports / minute | Per client IP, `POST /client-errors` | same |
| API Gateway stage throttle | 50 req/s steady, burst 100 | Every client and route together | `infra/hub/apigateway.tf` |
| Login password length | 256 characters | `POST /auth/login`, rejected before argon2 | `backend/app/routers/auth.py` |
| Accounts | 1000 total | `POST /auth/register` | `backend/app/core/quotas.py` |
| Projects | 500 per user | `POST /projects` | same |
| Notes | 500 per project | `POST /projects/{id}/notes` | same |

The per-IP limits and the account cap are on only when deployed
(`is_deployed()`: dev and prod Lambdas); locally they're off so the E2E
suite can register and log in hundreds of times from 127.0.0.1. The
project and note caps and the password cap apply everywhere. Every value
can be overridden by environment variable (`backend/.env.example`).

Over a per-IP limit: `429` with `Retry-After`. Over a cap: `403` with a
human-readable `detail`. Over-long password: `422` in FastAPI's usual
validation shape.

## What each layer is for

- **Login limit**: slows online password guessing against one account,
  or one password against many accounts, from one network. argon2 makes
  each guess expensive for us too, so this also bounds CPU spent per IP.
- **Sign-up limit and account cap**: stop one client mass-creating
  accounts (storage, argon2 CPU), and put a hard ceiling on the database
  size of a public demo deployment however many IPs an attacker has.
- **Error-report limit**: `/client-errors` is unauthenticated, so this
  is what keeps one client from flooding CloudWatch Logs.
- **Project and note caps**: bound what one account can make the
  database hold. Without them a single signed-in script could fill the
  Neon storage quota.
- **Password length cap**: argon2 hashes the whole input. Uncapped, one
  request with a multi-megabyte password costs seconds of Lambda CPU.
- **API Gateway throttle**: the global backstop. It isn't per client:
  when it trips, everyone gets `429` until the rate drops.

## Known gap: per-IP limits are per Lambda container

The sliding-window counters live in process memory
(`SlidingWindowRateLimiter`). Each warm Lambda container is its own
process with its own counts, and nothing is shared between them.

Consequences:

- With N containers warm, one client can get up to N times the limit
  through, if its requests happen to land on different containers.
  Lambda routes requests to idle containers, so concurrent requests
  (the thing an attacker controls) are exactly what spreads them out.
- A container that's recycled (idle timeout, deploy, scale-in) starts
  with empty counts.
- There's no reserved concurrency on the API function
  (`infra/hub/lambda.tf`), so N is bounded only by the account's
  concurrency limit and the API Gateway throttle. In practice, at
  50 req/s and roughly 100 to 300 ms per request, that's on the order of
  5 to 15 containers, so a determined client could get maybe 25 to 75
  login attempts per minute instead of 5.

Why that's acceptable for now: this is a single-user-scale app with a
stage throttle in front, argon2 makes each guess slow, and accounts are
self-registered with an 8-character minimum. The limit still stops
casual and single-threaded abuse, which is the bulk of it.

Options if it starts to matter, cheapest first:

1. **Reserved concurrency** on the API Lambda (for example 5). Caps N
   directly, at the cost of throttling legitimate traffic under load.
   One line in `infra/hub/lambda.tf`.
2. **AWS WAF rate-based rule** on the CloudFront distribution, scoped
   to `/api/auth/*`. Global and enforced before the request reaches
   Lambda. Adds a monthly WAF cost and a minimum window of a minute or
   more; check current WAF minimums before choosing thresholds.
3. **Shared counter in Postgres**: a `rate_limit_hits` table keyed by
   bucket and minute, incremented with an upsert. Exact and global, but
   adds a database write to every auth request and wakes Neon from
   sleep for a request that might be rejected. Would need an Alembic
   migration.

## Client identity

Behind CloudFront, the client IP comes from `CloudFront-Viewer-Address`
(`CLIENT_IP_HEADER`), or, when that address is a trusted proxy, from
`X-Forwarded-For` (below). The header is trusted only because origin
verification (`backend/app/auth/origin_verify.py`) rejects any request
that didn't come through CloudFront: a direct call to the public
`execute-api` URL could otherwise set the header to anything and get a
fresh bucket per request.

### Behind Cloudflare: trusted proxies and X-Forwarded-For

The site's DNS record is Cloudflare-proxied (`proxied = true` in
`infra/hub/dns.tf`), so the request path is browser, Cloudflare,
CloudFront, API Gateway, Lambda. CloudFront's "viewer" is a Cloudflare
edge server, so `CloudFront-Viewer-Address` carries Cloudflare's egress
IP, not the user's. On its own, that makes the per-IP limits per
Cloudflare edge: users who share one get each other's `429`s. (Found on
2026-10-02.)

**The fix (implemented 2026-10-02):** `TRUSTED_PROXY_IPS`, a
comma-separated list of IPs or CIDR ranges
(`backend/app/core/config.py`). `client_ip()` in
`backend/app/auth/rate_limit.py` now:

1. Takes the nearest hop it can see, as before: the address in
   `CLIENT_IP_HEADER` (`CloudFront-Viewer-Address`), else the TCP peer.
2. If that hop is **not** in `TRUSTED_PROXY_IPS`, uses it. Done.
   `X-Forwarded-For` is ignored entirely.
3. If it **is** (a Cloudflare edge), reads `X-Forwarded-For`, drops any
   entries after the hop itself (CloudFront or API Gateway may append
   their own), and walks the rest right to left, skipping trusted
   proxies. The first untrusted address is the client.
4. If the chain is empty, all trusted, or has a malformed entry before
   an untrusted one, falls back to the hop (fail closed: never trust
   what's left of something unreadable).

Why it can't be spoofed:

- Only the right-hand end of `X-Forwarded-For` is trustworthy; each
  proxy appends what it saw. A client that sends
  `X-Forwarded-For: 6.6.6.6` through Cloudflare arrives as
  `6.6.6.6, <real address>, ...`, and the walk stops at the real one.
- A client that skips Cloudflare and calls the `*.cloudfront.net`
  domain directly is its own CloudFront viewer. Its address isn't in
  Cloudflare's ranges, so its `X-Forwarded-For` is never read.
- Calling the `execute-api` URL directly is still refused by origin
  verification before the limiter runs.
- The list is validated at startup: a typo stops the Lambda from
  starting rather than trusting the wrong thing.

The one trust this adds: anyone who can send requests *from* an
address in the list can claim any client address. That's why the list
must be exactly Cloudflare's published ranges, and nothing broader.

**Default: empty**, meaning no proxy is trusted and behaviour is exactly
as before. That's correct for local runs and Docker Compose, which have
no proxy in front. Leave it unset there.

**Deploying it:** set the GitHub environment variable
`TRUSTED_PROXY_IPS` on the `dev` and `prod` environments to Cloudflare's
current ranges. Both workflows pass it to OpenTofu
(`TF_VAR_trusted_proxy_ips`, `variable "trusted_proxy_ips"` in
`infra/hub/main.tf`), which sets it on the API Lambda
(`infra/hub/lambda.tf`). Commands, and how to check it works from two
networks: `ops/DEPLOYMENT.md`, "Trusted proxies: Cloudflare's IP
ranges". Set on both environments since 2026-10-03; verified from two
networks on 2026-10-04 (the second network got `401`, not `429`). If the
variable is ever unset, the limits fall back to per Cloudflare edge.

The alternative of making the DNS record DNS-only (`proxied = false`)
would also fix the keying with no app change, at the cost of
Cloudflare's proxy features for this hostname. Not done.

**Tests** (`backend/tests/test_rate_limit.py`): the header is used only
when the hop is trusted; ignored with no trusted proxies or an
untrusted hop; entries after the hop dropped; forged left-hand entries
ignored; several trusted proxies skipped; malformed entries fall back
to the hop; IPv6 clients still grouped by /64; two users behind one
Cloudflare edge get separate login buckets; and the list parser
normalizes ranges and rejects typos.

## Caps are soft

Every cap is "count, then insert" with no lock between. Two requests at
the boundary can both pass and leave a user one or two over. Making them
exact would need a row lock or a constraint, which isn't worth it for
limits whose job is bounding growth, not billing.

## Tests

- `backend/tests/test_rate_limit.py`: windows, IP parsing (IPv4, IPv6,
  bracketed, mapped), /64 grouping, login and sign-up 429s.
- `backend/tests/test_client_errors.py`: the error-report limit, and
  that it's separate from the login count.
- `backend/tests/test_auth.py`: the login password cap (including that
  over-long attempts never reach argon2 and still count toward the
  limit).
- `backend/tests/test_quotas.py`: every cap, per user and per project.
