FROM ghcr.io/home-assistant/base:latest
RUN apk add --no-cache ca-certificates python3 py3-flask py3-pillow
WORKDIR /app
COPY main.py /app/main.py
COPY templates /app/templates
COPY static /app/static
COPY run.sh /run.sh
RUN chmod a+x /run.sh
CMD ["/run.sh"]
