# syntax=docker/dockerfile:1.7
# ---- serve with NGINX (open source) ----
FROM nginx:1.30.5-alpine
LABEL org.opencontainers.image.title="telco-web" org.opencontainers.image.licenses="MIT"
ENV NGINX_ENVSUBST_OUTPUT_DIR=/tmp/conf.d
COPY apps/web/nginx/nginx.conf /etc/nginx/nginx.conf
COPY apps/web/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --chmod=755 apps/web/nginx/05-tmp-dirs.sh /docker-entrypoint.d/05-tmp-dirs.sh
COPY --chmod=755 apps/web/nginx/30-render-config.sh /docker-entrypoint.d/30-render-config.sh
COPY apps/web/out /usr/share/nginx/html
COPY apps/web/nginx/csp-hashes.txt /tmp/csp-hashes.txt
RUN rm -f /usr/share/nginx/html/config.json /etc/nginx/conf.d/default.conf \
 && sed -i "s|__CSP_SCRIPT_HASHES__|$(cat /tmp/csp-hashes.txt)|" /etc/nginx/templates/default.conf.template \
 && rm /tmp/csp-hashes.txt \
 && mkdir -p /tmp/conf.d
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s CMD wget -qO- http://127.0.0.1:8080/nginx-health || exit 1
