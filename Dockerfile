# Royal Beef LAN — baut Seite und Server in ein fertiges Image.
# Portainer baut das selbst, sobald der Stack aus dem Repository kommt.
FROM python:3.12-alpine

WORKDIR /app
COPY server.py /app/server.py
COPY index.html /app/web/index.html

ENV PORT=8080 \
    WEB_ROOT=/app/web \
    DATA_FILE=/data/state.json

VOLUME /data
EXPOSE 8080

CMD ["python", "/app/server.py"]
