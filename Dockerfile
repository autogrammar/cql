FROM node:20-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS build
WORKDIR /app
COPY package.json package-lock.json* ./
# vendor/oqlts musi istnieć przed npm install (dependency file:vendor/oqlts);
# stage'owany przez build-images-push-pi109.sh / krok build-cql migracji.
COPY vendor ./vendor
RUN npm install
# Copy only what's needed for the build — legacy/ and node_modules are
# excluded via .dockerignore so they never enter the image context.
COPY . .
RUN npm run build

FROM nginx:alpine@sha256:83075afea33660ca1911ce1905dee384079ed856397e0e5a9249435b22c35dc8
# envsubst is bundled in nginx:alpine; template is rendered on container start.
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# Defaults — safe to override via `docker compose --env-file .env`
ENV BACKEND_API_URL="http://host.docker.internal:8080" \
    BACKEND_WS_URL="http://host.docker.internal:8080" \
    CQL_BACKEND_URL="http://cql-backend:8101" \
    CQL_LISTEN_PORT="80" \
    FRAME_ANCESTORS="self http://*.localhost https://*.localhost"
EXPOSE 80
# nginx:alpine auto-runs envsubst on /etc/nginx/templates/*.template at startup.
CMD ["nginx", "-g", "daemon off;"]
