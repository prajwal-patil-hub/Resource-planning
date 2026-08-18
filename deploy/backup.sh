#!/bin/sh
# Nightly database dump with retention, and the restore that proves it works.
#
# The reason this script exists rather than a one-line cron entry: a backup
# nobody has restored is not a backup, it is a file. Everything below is shaped
# by that — the dump is verified after being written, the loop reports failure
# loudly rather than silently skipping a night, and `restore.sh` beside it is
# meant to be *run*, not read.
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) backup: $*"; }

take_backup() {
	mkdir -p "$BACKUP_DIR"
	stamp="$(date -u +%Y%m%d-%H%M%S)"
	target="$BACKUP_DIR/rp-$stamp.dump"

	# Custom format (-Fc): compressed, and restorable table-by-table with
	# pg_restore, which matters when the thing to undo is one bad migration
	# rather than a lost machine.
	#
	# Written to .part first and renamed on success. A rename within one
	# filesystem is atomic, so a dump interrupted half-way can never be mistaken
	# for a complete one — which is exactly the file someone would reach for in
	# an emergency.
	if pg_dump -Fc -f "$target.part"; then
		mv "$target.part" "$target"
	else
		log "FAILED to dump — leaving no partial file"
		rm -f "$target.part"
		return 1
	fi

	# Verify by reading it back. pg_restore --list parses the archive's table of
	# contents, so a truncated or corrupt dump fails here rather than at 2am
	# during an actual restore.
	if ! pg_restore --list "$target" > /dev/null 2>&1; then
		log "FAILED verification — $target is not a readable archive, removing"
		rm -f "$target"
		return 1
	fi

	size="$(du -h "$target" | cut -f1)"
	log "wrote $target ($size), verified readable"

	# Retention. Deliberately after a successful verified write, so a run of
	# failures can never delete the last good backup along the way.
	deleted="$(find "$BACKUP_DIR" -name 'rp-*.dump' -type f -mtime "+$KEEP_DAYS" -print -delete | wc -l)"
	[ "$deleted" -gt 0 ] && log "removed $deleted backup(s) older than $KEEP_DAYS days"

	log "$(find "$BACKUP_DIR" -name 'rp-*.dump' -type f | wc -l) backup(s) held"
	return 0
}

case "${1:---once}" in
--once)
	take_backup
	;;
--loop)
	# A sleep loop rather than cron: one process, its output goes to
	# `docker compose logs backup` like everything else, and there is no second
	# scheduler to configure or forget.
	log "started — nightly dumps to $BACKUP_DIR, keeping $KEEP_DAYS days"
	# Take one immediately so a fresh deployment is protected within seconds
	# rather than at the end of the first day.
	take_backup || log "initial backup failed — will retry on the next cycle"
	while true; do
		sleep 86400
		take_backup || log "backup failed — the stack keeps running, but FIX THIS"
	done
	;;
*)
	echo "usage: backup.sh [--once|--loop]" >&2
	exit 2
	;;
esac
