FROM node:22-alpine

WORKDIR /app

COPY vendor/oqlts /app/vendor/oqlts
RUN npm ci --prefix /app/vendor/oqlts && npm run build --prefix /app/vendor/oqlts

COPY packages/cql-runtime/package.json ./packages/cql-runtime/
COPY packages/cql-runtime/src ./packages/cql-runtime/src/
COPY packages/cql-runtime-server/package.json ./packages/cql-runtime-server/
COPY packages/cql-runtime-server/src ./packages/cql-runtime-server/src/
COPY runtime ./runtime

# Mirror the dev layout: a root-level node_modules symlink so every package
# (cql-runtime and cql-runtime-server) resolves @semcod/oqlts by walking up to
# /app/node_modules — oqlos/cql is not an npm workspace, so a file: dependency's
# own imports aren't covered by per-package installs alone.
RUN mkdir -p /app/node_modules/@semcod \
  && ln -s /app/vendor/oqlts /app/node_modules/@semcod/oqlts

WORKDIR /app/packages/cql-runtime-server
# `npm start` runs `node --import tsx …`, so tsx (a devDependency) must be
# present at runtime — do NOT use --omit=dev here.
RUN npm install

ENV OQL_RUNTIME_HOST=0.0.0.0
ENV OQL_RUNTIME_PORT=8101
EXPOSE 8101

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8101/health || exit 1

CMD ["npm", "start"]
