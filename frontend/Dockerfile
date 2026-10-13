# syntax=docker/dockerfile:1

# The web app for the local Docker Compose stack: the production build
# (`pnpm build`, the same artifact CI uploads to S3) served by nginx,
# which also forwards /api/* to the backend the way CloudFront does when
# deployed. Not used for deployment; see frontend/README.md.

# ---- stage: build ------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /src
# pnpm at the version pinned in package.json's packageManager field.
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
# VITE_API_BASE_URL is left unset (and .env is excluded by .dockerignore),
# so the app calls same-origin /api, as in every deployed build.
RUN pnpm build

# ---- stage: serve --------------------------------------------------------
# Non-root nginx, listening on 8080.
FROM nginxinc/nginx-unprivileged:1.30-alpine
# Security fixes the base image doesn't have yet (trivy found a MEDIUM
# zlib CVE with a fixed package released), as the backend image does with
# dnf. Root only for the upgrade, then back to the image's nginx user.
USER root
RUN apk upgrade --no-cache
USER 101
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
# The page itself, not /api: the backend has its own lifecycle.
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
