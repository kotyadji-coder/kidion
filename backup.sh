#!/bin/bash
BACKUP_DIR="/opt/backups/kidion/$(date +%Y-%m-%d)"
mkdir -p "$BACKUP_DIR"
cp /opt/kidion/kidion.db "$BACKUP_DIR/" 2>/dev/null
cp /opt/kidion/.env "$BACKUP_DIR/" 2>/dev/null
# Keep only last 30 days
find /opt/backups/kidion/ -maxdepth 1 -type d -mtime +30 -exec rm -rf {} \;
echo "Backup done: $BACKUP_DIR"
