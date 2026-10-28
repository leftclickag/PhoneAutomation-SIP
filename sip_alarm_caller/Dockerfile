ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache baresip python3 py3-aiohttp ffmpeg

COPY app.py /app.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
