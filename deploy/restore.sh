#!/bin/sh
# Restore the database from a backup.
#
# This script is meant to be RUN, not read. A backup nobody has restored is a
# file with hopeful contents; the only way to know the backups work is to have
# done this at least once, on purpose, when nothing was on fire.
#
#   ./restore.sh                      # list what is available
#   ./restore.sh rp-20260817-020000.dump
#
# Run it from the deploy/ directory, with the stack up.
set -eu

COMPOSE="${COMPOSE:-docker compose}"

if [ $# -eq 0 ]; then
	echo "Backups available:"
	$COMPOSE exec -T backup sh -c 'ls -lh /backups/rp-*.dump 2>/dev/null || echo "  none yet"'
	echo
	echo "Then: $0 <filename>"
	exit 0
fi

FILE="$1"

cat <<WARNING

This REPLACES the current contents of the database with $FILE.

Everything recorded since that backup was taken will be gone. If this is a
production machine and you are not certain, stop now and take a fresh dump
first:  $COMPOSE run --rm backup /usr/local/bin/backup.sh --once

WARNING
printf 'Type RESTORE to continue: '
read -r confirm
[ "$confirm" = "RESTORE" ] || { echo "Aborted — nothing changed."; exit 1; }

echo "==> Stopping the application so nothing writes mid-restore"
# Left running, the app would hold connections that block the drop and could
# write into a half-restored database. The proxy stays up so people get an
# error page rather than a dead socket.
$COMPOSE stop app

echo "==> Restoring"
# --clean --if-exists drops each object before recreating it, so this works on a
# populated database rather than only an empty one — which is the situation you
# are actually in when restoring.
#
# NOT --single-transaction: with `--clean` on a database whose objects differ
# from the archive, one unexpected drop failure would roll back the entire
# restore and leave nothing. Failing per-object and reporting is recoverable;
# an all-or-nothing rollback at 2am is not.
$COMPOSE exec -T backup sh -c "pg_restore --clean --if-exists --no-owner -d \"\$PGDATABASE\" /backups/$FILE" \
	|| echo "!! pg_restore reported errors — read them before trusting this database"

echo "==> Starting the application"
$COMPOSE start app

echo "==> Waiting for health"
for i in $(seq 1 30); do
	if $COMPOSE exec -T app python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz', timeout=4).status == 200 else 1)" > /dev/null 2>&1; then
		echo "Healthy. Restore complete."
		exit 0
	fi
	sleep 2
done

echo "!! The app did not become healthy within 60s. Check: $COMPOSE logs app"
exit 1
