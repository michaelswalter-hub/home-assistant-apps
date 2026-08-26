#!/usr/bin/with-contenv bashio
set -euo pipefail

export LIBRARY_DATA_DIR="/data/library"
export LIBRARY_MAX_UPLOAD_MB="$(bashio::config 'max_upload_mb')"
export LIBRARY_METADATA_LANGUAGE="$(bashio::config 'metadata_language')"

mkdir -p "${LIBRARY_DATA_DIR}/books"

bashio::log.info "Starte Bibliothek auf Port 8099"
bashio::log.info "Maximale Upload-Größe: ${LIBRARY_MAX_UPLOAD_MB} MB"
bashio::log.info "Bevorzugte Metadaten-Sprache: ${LIBRARY_METADATA_LANGUAGE}"

cd /app
exec /opt/venv/bin/waitress-serve \
  --listen=0.0.0.0:8099 \
  --threads=4 \
  --channel-timeout=600 \
  main:app
