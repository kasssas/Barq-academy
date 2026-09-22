#!/usr/bin/env bash
set -euo pipefail

echo "Creating backup of PostgreSQL database 'barq_tasks'..."

# Ensure backups directory exists
mkdir -p backups

# Generate timestamped filename
BACKUP_FILE="backups/barq_tasks_$(date +%Y%m%d_%H%M%S).sql"

# Run pg_dump inside the postgres container.
# Using sh -c ensures we securely use the container's internal POSTGRES_PASSWORD
# without passing it explicitly on the host process list or in the script.
if docker exec -i postgres sh -c 'PGPASSWORD=$POSTGRES_PASSWORD pg_dump -U barq_app -d barq_tasks --clean --if-exists' > "$BACKUP_FILE"; then
    echo "PASS: Backup created successfully at $BACKUP_FILE"
else
    echo "FAIL: Backup process encountered an error." >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi
