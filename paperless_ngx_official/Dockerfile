# Home Assistant übergibt die Version aus config.yaml als BUILD_VERSION.
# Damit wird immer genau das offizielle Paperless-ngx-Image dieser Version genutzt.
ARG BUILD_VERSION=3.5.1
FROM ghcr.io/paperless-ngx/paperless-ngx:${BUILD_VERSION}

# PostgreSQL-Hauptversion bewusst festgenagelt (wie im offiziellen Compose-Setup).
# Ein Wechsel der Hauptversion erfordert eine Datenmigration – nie automatisch ändern.
ARG PG_MAJOR=18

# PostgreSQL und Redis laufen im offiziellen Compose-Setup als eigene Container;
# hier laufen sie intern im selben Container (nur auf 127.0.0.1 erreichbar).
RUN set -eux; \
    apt-get update; \
    apt-get install --yes --quiet --no-install-recommends ca-certificates curl gnupg; \
    . /etc/os-release; \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg; \
    echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install --yes --quiet --no-install-recommends \
      "postgresql-${PG_MAJOR}" "postgresql-client-${PG_MAJOR}" redis-server; \
    apt-get purge --yes gnupg; \
    apt-get autoremove --yes; \
    rm -rf /var/lib/apt/lists/*; \
    ln -s "/usr/lib/postgresql/${PG_MAJOR}/bin" /usr/lib/postgresql/current

ENV PG_MAJOR=${PG_MAJOR} \
    S6_SERVICES_GRACETIME=30000 \
    S6_KILL_GRACETIME=10000

COPY rootfs /

RUN chmod +x \
      /usr/local/bin/ha-config.py \
      /etc/s6-overlay/s6-rc.d/init-ha-config/run \
      /etc/s6-overlay/s6-rc.d/init-postgres/run \
      /etc/s6-overlay/s6-rc.d/init-postgres-db/run \
      /etc/s6-overlay/s6-rc.d/svc-postgres/run \
      /etc/s6-overlay/s6-rc.d/svc-redis/run

LABEL io.hass.type="addon" \
      io.hass.version="${BUILD_VERSION}"
