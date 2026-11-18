# Version wie im offiziellen Paperless-ngx-Compose-Setup (von der GitHub Action gepflegt).
ARG GOTENBERG_VERSION=8.38
FROM docker.io/gotenberg/gotenberg:${GOTENBERG_VERSION}

# Einstellungen wie im offiziellen Paperless-ngx-Compose-Setup:
# kein JavaScript und keine externen Inhalte (z. B. Tracking-Pixel in E-Mails).
CMD ["gotenberg", "--chromium-disable-javascript=true", "--chromium-allow-list=^file:///tmp/.*"]
