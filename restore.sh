#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <backup_file>"
    echo "Example: $0 backups/barq_tasks_20231010_120000.sql"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "FAIL: Backup file '$BACKUP_FILE' does not exist." >&2
    exit 1
fi

echo "Restoring PostgreSQL database 'barq_tasks' from '$BACKUP_FILE'..."

# Pipe the backup file into psql inside the postgres container.
# Using sh -c passes the container's internal POSTGRES_PASSWORD securely.
# -v ON_ERROR_STOP=1 ensures that psql exits with an error status if any command fails.
if docker exec -i postgres sh -c 'PGPASSWORD=$POSTGRES_PASSWORD psql -U barq_app -d barq_tasks -v ON_ERROR_STOP=1 -q' < "$BACKUP_FILE"; then
    echo "PASS: Restore completed successfully."
else
    echo "FAIL: Restore process encountered an error." >&2
    exit 1
fi
