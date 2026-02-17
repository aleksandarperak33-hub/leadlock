#!/bin/bash
# ============================================================================
# LeadLock Database Backup Script
#
# Performs a pg_dump backup of the LeadLock PostgreSQL database.
# Designed to run as a daily cron job (3 AM UTC).
#
# Configuration (environment variables):
#   PGHOST       - PostgreSQL host (default: localhost)
#   PGPORT       - PostgreSQL port (default: 5432)
#   PGUSER       - PostgreSQL user (default: leadlock)
#   PGPASSWORD   - PostgreSQL password (required)
#   PGDATABASE   - Database name (default: leadlock)
#   BACKUP_DIR   - Local backup directory (default: /backups)
#   BACKUP_RETAIN_DAYS - Days to retain backups (default: 7)
#   S3_BUCKET    - Optional S3 bucket for offsite backup (e.g., s3://my-bucket/backups)
#
# Cron example (add to crontab):
#   0 3 * * * /app/scripts/backup_db.sh >> /var/log/leadlock-backup.log 2>&1
#
# Restore procedure:
#   1. Stop the application: docker compose stop api
#   2. Drop existing database: dropdb -U leadlock leadlock
#   3. Create fresh database: createdb -U leadlock leadlock
#   4. Restore from backup: pg_restore -U leadlock -d leadlock /backups/leadlock_YYYYMMDD_HHMMSS.dump
#   5. Run migrations: alembic upgrade head
#   6. Start application: docker compose start api
# ============================================================================

set -euo pipefail

# Configuration with defaults
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-leadlock}"
PGDATABASE="${PGDATABASE:-leadlock}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_RETAIN_DAYS="${BACKUP_RETAIN_DAYS:-7}"
S3_BUCKET="${S3_BUCKET:-}"

# Timestamp for backup filename
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/${PGDATABASE}_${TIMESTAMP}.dump"

echo "[$(date -Iseconds)] Starting backup of ${PGDATABASE}..."

# Ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

# Perform backup using custom format (supports parallel restore)
pg_dump \
    -h "${PGHOST}" \
    -p "${PGPORT}" \
    -U "${PGUSER}" \
    -d "${PGDATABASE}" \
    -Fc \
    --no-owner \
    --no-privileges \
    -f "${BACKUP_FILE}"

BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "[$(date -Iseconds)] Backup completed: ${BACKUP_FILE} (${BACKUP_SIZE})"

# Upload to S3 if configured
if [ -n "${S3_BUCKET}" ]; then
    echo "[$(date -Iseconds)] Uploading to ${S3_BUCKET}..."
    if command -v aws &> /dev/null; then
        aws s3 cp "${BACKUP_FILE}" "${S3_BUCKET}/${PGDATABASE}_${TIMESTAMP}.dump"
        echo "[$(date -Iseconds)] S3 upload complete"
    else
        echo "[$(date -Iseconds)] WARNING: aws CLI not installed — skipping S3 upload"
    fi
fi

# Clean up old backups (retain last N days)
echo "[$(date -Iseconds)] Cleaning up backups older than ${BACKUP_RETAIN_DAYS} days..."
find "${BACKUP_DIR}" -name "${PGDATABASE}_*.dump" -mtime "+${BACKUP_RETAIN_DAYS}" -delete
REMAINING=$(find "${BACKUP_DIR}" -name "${PGDATABASE}_*.dump" | wc -l)
echo "[$(date -Iseconds)] Cleanup complete. ${REMAINING} backup(s) retained."

echo "[$(date -Iseconds)] Backup process finished successfully."
