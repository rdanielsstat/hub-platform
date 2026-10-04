# Changelog

All notable changes to Hub are recorded here. Versions follow
[Semantic Versioning](https://semver.org/); the deployed `SERVICE_VERSION`
comes from the git tag (`.github/scripts/service-version.sh`).

## [1.0.0] - 2026-10-03

### Added
- User authentication (login/signup with cookie-based sessions)
- Projects and notes (multi-user, per-user data isolation)
- Rate limiting per client IP (login 5/min, register 3/min, client error reports 30/min), plus usage quotas
- Cloudflare integration (DDoS protection, WAF, Web Analytics)
- Frontend error reporting to Grafana Cloud Loki
- Data length limits: display name (100), tags (50 @ 64 chars), links (50 @ 2048 URL + 200 label)

### Security
- Content Security Policy (CSP) with HSTS, X-Frame-Options, nosniff, Referrer-Policy
- Backend Docker image hardened (Trivy scan clean)
- Infrastructure scanning (tfsec/checkov)
- Dependency scanning (pip-audit, pnpm audit) gated in CI
- GitHub branch protection (blocks force-push and deletion of main)

### Infrastructure
- PostgreSQL with Alembic migrations (0003)
- Lambda backend, CloudFront + S3 frontend
- Docker Compose for local development
- CI/CD pipeline: test → integration → e2e → dependency-scan → deploy-dev; separate promotion to prod with migrations-before-code
- Grafana Cloud observability (logs, error reporting)

### Testing
- 435 backend unit tests, 38 backend integration tests
- 202 frontend unit tests, 201 Playwright E2E tests

### Documentation
- Product specification
- API specification (OpenAPI)
- Architecture and design notes
- Deployment and troubleshooting guides
- Security audit and hardening documentation

### Design Notes
- Tags field caps total input length (comma-separated), not per-tag
- Link URLs auto-prepend `https://` if missing
- Form fields use HTML `maxLength` attributes to enforce API limits

[1.0.0]: https://github.com/rdanielsstat/hub-platform/releases/tag/v1.0.0
