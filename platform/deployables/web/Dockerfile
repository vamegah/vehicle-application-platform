# AutoReliance AI web app (task 1.6). Build context: the repository root (platform/docker-compose.yml sets it).
# Copies the Next.js standalone server built by `npm run build` in apps/web; no npm install in the image.
# Base image pinned by tag and digest in DEPENDENCIES.lock.md. All data shown is fictional.
FROM node:24.22.3-trixie-slim@sha256:4d00acb4bcc42c454c4eb801526f7ad7f772ea3bd4fd168c5cc2e384abcbb9d4
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
COPY --chown=node:node apps/web/.next/standalone ./
COPY --chown=node:node apps/web/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
