# Mini App build + Caddy. Build context: the repository root.
FROM node:22-alpine AS build
WORKDIR /repo/miniapp
COPY miniapp/package.json miniapp/package-lock.json ./
RUN npm ci
COPY contracts /repo/contracts
COPY miniapp ./
RUN npm run build

FROM caddy:2-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /repo/miniapp/dist /srv
