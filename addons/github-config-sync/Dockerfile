ARG BUILD_FROM=ghcr.io/home-assistant/base:latest
FROM ${BUILD_FROM}

WORKDIR /app

COPY rootfs /

RUN chmod a+x /usr/local/bin/start.sh \
    && (command -v pip3 >/dev/null 2>&1 || apk add --no-cache python3 py3-pip) \
    && pip3 install --no-cache-dir flask==3.0.3

EXPOSE 8099

CMD ["/usr/local/bin/start.sh"]
