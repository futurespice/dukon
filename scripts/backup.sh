#!/usr/bin/env bash
# =============================================================================
# DEVOPS FIX #8: automated PostgreSQL backup script.
#
# Usage:
#   bash scripts/backup.sh                  # manual run
#   crontab: 0 3 * * * /opt/dukon/scripts/backup.sh >> /var/log/dukon-backup.log 2>&1
#
# What it does:
#   1. Dumps PostgreSQL to a compressed .sql.gz file
#   2. Keeps the last BACKUP_KEEP_DAYS days of local backups
#   3. Optionally syncs to an S3-compatible bucket (set S3_BUCKET in .env)
#
# Prerequisites on the host:
#   - docker  (pg_dump runs inside the db container — no host install needed)
#   - awscli  (optional, for S3 upload):  apt install awscli
#
# Environment variables (read from .env or exported before calling):
#   DB_NAME, DB_USER   — database credentials
#   S3_BUCKET          — e.g. s3://my-bucket/dukon-backups  (optional)
#   BACKUP_KEEP_DAYS   — days of local backups to retain (default 7)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

# Load .env if present (production scenario)
if [ -f "$ENV_FILE" ]; then
  # shellcheck source=/dev/null
  set -a; source "$ENV_FILE"; set +a
fi

DB_NAME="${DB_NAME:-dukon_db}"
DB_USER="${DB_USER:-postgres}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/dukon}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-7}"
S3_BUCKET="${S3_BUCKET:-}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/dukon_${DB_NAME}_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting backup → $BACKUP_FILE"

# Dump via docker exec — avoids installing pg_dump on the host
docker compose -f "$PROJECT_DIR/docker-compose.production.yml" \
  exec -T db \
  pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Written: $(du -sh "$BACKUP_FILE" | cut -f1)"

# Optional S3 upload (zero cost if S3_BUCKET is empty)
if [ -n "$S3_BUCKET" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Uploading to $S3_BUCKET ..."
  aws s3 cp "$BACKUP_FILE" "$S3_BUCKET/$(basename "$BACKUP_FILE")" \
    --storage-class STANDARD_IA
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] S3 upload done."
fi

# Rotate old local backups
DELETED=$(find "$BACKUP_DIR" -name "dukon_${DB_NAME}_*.sql.gz" \
  -mtime "+${BACKUP_KEEP_DAYS}" -print -delete | wc -l)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Removed $DELETED backup(s) older than ${BACKUP_KEEP_DAYS} days."
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup complete."
