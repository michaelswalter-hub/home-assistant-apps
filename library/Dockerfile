FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION=0.9.16
ARG BUILD_ARCH

LABEL \
    io.hass.name="Bibliothek" \
    io.hass.description="Private EPUB- und PDF-Bibliothek für Home Assistant" \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="${BUILD_ARCH}"

RUN apk add --no-cache \
      python3 \
      py3-pip \
      poppler-utils \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip

COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

COPY app /app
COPY run.sh /run.sh
RUN chmod a+x /run.sh

WORKDIR /app
CMD ["/run.sh"]
