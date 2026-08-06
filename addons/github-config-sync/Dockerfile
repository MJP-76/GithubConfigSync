ARG BUILD_FROM=ghcr.io/home-assistant/base:3.24-2026.06.1
FROM ${BUILD_FROM}

WORKDIR /app

COPY config.yaml /app/config.yaml
COPY rootfs /

RUN chmod a+x /usr/local/bin/start.sh \
    && apk add --no-cache python3 py3-flask

EXPOSE 8099

CMD ["/usr/local/bin/start.sh"]
