#!/bin/sh
# First-boot bootstrap for the job-ability-graph backend container.
#
# The backend is designed to read its fixtures (seed JD, pre-built KG files,
# ESCO index) from ${DATA_GOVERNANCE_ROOT:-/app/data}. That directory is a
# named volume so user data (app.db, uploads, profiles...) survives restarts.
# A mounted volume shadows everything baked into the image, so on first boot
# we copy the read-only fixtures from /.fixtures into the volume. Later boots
# are no-ops (guarded by the .seeded marker).
set -eu

DATA_DIR="${DATA_GOVERNANCE_ROOT:-/app/data}"
FIXTURES_DIR="/app/.fixtures"

if [ ! -f "$DATA_DIR/.seeded" ]; then
  echo "[entrypoint] first boot: seeding fixtures into $DATA_DIR"
  mkdir -p "$DATA_DIR"
  cp -rn "$FIXTURES_DIR"/small_raw_200_lskt_tech_v2 "$DATA_DIR/" 2>/dev/null || true
  cp -rn "$FIXTURES_DIR"/esco "$DATA_DIR/" 2>/dev/null || true
  mkdir -p "$DATA_DIR/small-raw"
  cp -n "$FIXTURES_DIR"/small-raw/jd_raw_100.jsonl "$DATA_DIR/small-raw/" 2>/dev/null || true
  touch "$DATA_DIR/.seeded"
  echo "[entrypoint] fixtures seeded"
fi

exec "$@"
