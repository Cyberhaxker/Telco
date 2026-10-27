# syntax=docker/dockerfile:1.7
# Next.js server: UI, /api/auth login routes (bcrypt + JWT) and a same-origin proxy of /api/v1 to the gateway.
FROM node:22-alpine AS build
WORKDIR /repo
COPY contracts ./contracts
WORKDIR /repo/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
ENV NEXT_TELEMETRY_DISABLED=1
# The rewrite target is baked into the routes manifest at build time.
ARG GATEWAY_UPSTREAM=apisix:9080
ENV GATEWAY_UPSTREAM=${GATEWAY_UPSTREAM}
RUN npm run build

FROM node:22-alpine
LABEL org.opencontainers.image.title="telco-web" org.opencontainers.image.licenses="MIT"
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=8080 GATEWAY_UPSTREAM=apisix:9080
WORKDIR /app
COPY --from=build --chown=node:node /repo/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /repo/apps/web/.next/static ./.next/static
COPY --from=build --chown=node:node /repo/apps/web/public ./public
COPY --from=build --chown=node:node /repo/apps/web/scripts/seed-users.mjs ./scripts/seed-users.mjs
USER node
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s CMD wget -qO- http://127.0.0.1:8080/login >/dev/null || exit 1
CMD ["node", "server.js"]
