ARG BUILD_FROM="ghcr.io/home-assistant/base:3.24"
FROM ${BUILD_FROM}

RUN apk add --no-cache pjsua python3 py3-aiohttp ffmpeg

COPY app.py /app.py
COPY run.sh /run.sh
# Samba/Windows copies often arrive as CRLF. A CR in the shebang makes s6
# look for "bashio\r", which does not exist, and the app never starts.
RUN sed -i 's/\r$//' /run.sh /app.py && chmod +x /run.sh

CMD ["/run.sh"]
