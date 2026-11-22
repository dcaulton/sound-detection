#!/usr/bin/env bash
# Dump Postgres and Neo4j from the machine that processes recordings.
# Copy the share/ directory to chakakhan and run bin/import_share.sh there.
set -euo pipefail

OUT="${1:-share}"
mkdir -p "$OUT"

PG_CONTAINER="${PG_CONTAINER:-sound-detection-postgres}"
NEO4J_CONTAINER="${NEO4J_CONTAINER:-sound-detection-neo4j}"
NEO4J_VOLUME="${NEO4J_VOLUME:-sound-detection_neo4j_data}"
PG_USER="${PG_USER:-sound}"
PG_DB="${PG_DB:-sound_detection}"

echo "dumping postgres from $PG_CONTAINER"
docker exec "$PG_CONTAINER" pg_dump -U "$PG_USER" -d "$PG_DB" --no-owner --no-acl \
  > "$OUT/postgres.sql"

echo "dumping neo4j from $NEO4J_CONTAINER (database stops for a moment)"
docker stop "$NEO4J_CONTAINER"
docker run --rm --user root \
  -v "$NEO4J_VOLUME":/data \
  neo4j:5.20 \
  neo4j-admin database dump neo4j --to-stdout > "$OUT/neo4j.dump"
docker start "$NEO4J_CONTAINER"

echo "wrote $OUT/postgres.sql and $OUT/neo4j.dump"
echo "copy $OUT/ to chakakhan and run: bin/import_share.sh $OUT"