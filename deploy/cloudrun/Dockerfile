FROM nginxinc/nginx-unprivileged:1.28-alpine
COPY --chown=101:101 index.html workspace.json health.json /usr/share/nginx/html/
COPY --chown=101:101 static/ /usr/share/nginx/html/static/
USER 101
EXPOSE 8080
