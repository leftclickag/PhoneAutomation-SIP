ARG BUILD_FROM="ghcr.io/home-assistant/base:3.24"
FROM ${BUILD_FROM}

RUN apk add --no-cache pjsua python3 py3-aiohttp ffmpeg

COPY app.py /app.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
