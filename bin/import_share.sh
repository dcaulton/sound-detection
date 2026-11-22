#!/usr/bin/env bash
# Restore a share dump into chakakhan's Postgres and Neo4j.
# Run from the repo root, with docker compose.share.yml up for the databases.
set -euo pipefail

SRC="${1:-share}"
PG_CONTAINER="${PG_CONTAINER:-chakakhan-postgres}"
NEO4J_CONTAINER="${NEO4J_CONTAINER:-chakakhan-neo4j}"
PG_USER="${PG_USER:-sound}"
PG_DB="${PG_DB:-sound_detection}"

test -f "$SRC/postgres.sql" || { echo "missing $SRC/postgres.sql"; exit 1; }
test -f "$SRC/neo4j.dump" || { echo "missing $SRC/neo4j.dump"; exit 1; }

echo "restoring postgres into $PG_CONTAINER"
docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -c \
  "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" < "$SRC/postgres.sql"

echo "restoring neo4j into $NEO4J_CONTAINER"
docker stop "$NEO4J_CONTAINER"
docker run --rm \
  -v chakakhan_neo4j_data:/data \
  -v "$PWD/$SRC":/backups \
  neo4j:5.20 \
  neo4j-admin database load neo4j --from-path=/backups --overwrite-destination=true
docker start "$NEO4J_CONTAINER"

echo "restored. restart the read-only API if it is already running."
