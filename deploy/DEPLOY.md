# Running this in production

One machine, four containers, no orchestrator. For fifteen people, Kubernetes
would be more moving parts than the thing it runs (K-004, working agreement 10).

Everything below has been run, not just written. Timings are measured.

---

## What you need

- A Linux machine with Docker Engine and the Compose plugin.
- A DNS name pointed at its public IP, with ports **80** and **443** reachable.
  Port 80 is not optional — Let's Encrypt uses it to prove you own the name.
- About 1 GB of RAM. The database is the hungry part and it is not hungry.

---

## First deployment

```bash
git clone <this repo> && cd Resource-planning/deploy
cp .env.example .env
```

Edit `.env`. Two lines matter:

- `SITE_ADDRESS` — the hostname, exactly. Caddy requests a certificate for it.
- `POSTGRES_PASSWORD` — generate it, do not invent it:
  ```bash
  openssl rand -base64 32
  ```

Then:

```bash
docker compose up -d
```

That builds the app image, starts Postgres, runs migrations to completion,
starts the app only once migrations succeeded, brings up Caddy, and takes a
first backup within seconds.

Watch it settle:

```bash
docker compose ps          # all four Up, db and app (healthy)
docker compose logs -f app
```

**Then open the site and create the first administrator.** The sign-in page
offers a one-time setup form while no account exists (BR-021 — no configuration
step; creating the first account is the single unavoidable exception). Do this
immediately: until it is done, anyone who finds the URL can create it.

Finally, make sure Docker starts at boot, or a power cut takes the app with it:

```bash
sudo systemctl enable docker
```

---

## What each container is for

| Service | Why it exists |
|---|---|
| `db` | PostgreSQL 16. Not published to the host — only the app can reach it |
| `migrate` | Runs `alembic upgrade head` once and exits. Separate so two app containers cannot race to migrate, and so a bad migration stops the deploy loudly instead of crash-looping |
| `app` | The application. One process; the supervisor restarts it |
| `proxy` | Caddy. HTTPS, certificate renewal, security headers |
| `backup` | Nightly `pg_dump`, verified and pruned |

---

## Day to day

```bash
docker compose ps                      # what is running and healthy
docker compose logs -f app             # application log
docker compose logs backup             # confirm last night's dump
docker compose exec backup ls -lh /backups
```

**Deploying a change:**

```bash
git pull
docker compose up -d --build
```

Migrations run before the new app starts. If a migration fails, the app is not
replaced — you keep the version that works.

---

## Backups

A dump is taken when the stack starts and every 24 hours after, into the
`backups` volume, kept for `BACKUP_KEEP_DAYS` (default 30).

Each dump is **verified after writing** by reading its table of contents back,
and written to a `.part` file renamed only on success — so a dump interrupted
half-way can never be mistaken for a complete one. That is precisely the file
somebody would reach for in an emergency.

Take one by hand before anything risky:

```bash
docker compose exec backup sh /usr/local/bin/backup.sh --once
```

**Copy them off this machine.** A backup on the same disk as the database
protects you from a mistake, not from a dead disk. Something like:

```bash
docker run --rm -v deploy_backups:/b -v /mnt/offsite:/out alpine \
  sh -c 'cp /b/rp-*.dump /out/'
```

---

## Restoring

```bash
cd deploy
./restore.sh                                # lists what is available
./restore.sh rp-20260818-014712.dump
```

It stops the app, restores, restarts, and waits for health. It asks you to type
`RESTORE` first, because it destroys everything recorded since that dump.

**This has been tested, and here is exactly what was tested.** With three work
items, one person and three transitions recorded, the entire schema was dropped
(`DROP SCHEMA public CASCADE`) — a total loss, zero tables remaining — and then
restored from the previous night's dump:

| | |
|---|---|
| Time to restore | **6 seconds** |
| Rows | 3 work items, 1 person, 3 transitions — identical |
| Triggers | 9 restored |
| Indexes | 35 restored |
| INV-2 still enforced | Yes — a `DELETE` on `state_transition` was refused after restore |
| Sign-in and board | Worked immediately |

The trigger check matters more than the row counts. A restore that returns your
rows but not the rules protecting them leaves a database that *looks* fine and
will quietly accept things it should refuse.

Six seconds is for a nearly-empty database. Expect it to grow roughly with the
data, and it will stay in minutes rather than hours at this scale — but
**re-run this drill once a quarter** and note the real number. That is the only
way the figure stays true.

---

## When something breaks

**The site is down.**
```bash
docker compose ps
```
- `app` unhealthy → `docker compose logs app`. It self-heals once the database
  is reachable: stale pooled connections are discarded automatically
  (`pool_pre_ping`), verified by killing Postgres and watching the app recover
  *without* restarting.
- `db` not running → `docker compose logs db`, then `docker compose start db`.
- Everything running, still down → check DNS still points here, and that 80/443
  are open. Caddy cannot renew a certificate without port 80.

**A crash.** Both `app` and `db` restart themselves; that was tested by killing
PID 1 inside the database container and watching the stack come back with the
data intact. Nothing needs doing by hand.

**Certificate problems.** `docker compose logs proxy`. Almost always DNS not
pointing here, or port 80 blocked. The `caddy_data` volume holds the
certificates — losing it means re-issuing, which is fine but rate-limited, so
do not delete it casually.

**Out of disk.** Usually old images:
```bash
docker system prune -a          # safe: does not touch volumes
docker system df                # where the space actually went
```
Never `docker volume prune` — that is the database.

**A bad migration reached production.** Restore from the dump taken before the
deploy. That is what the pre-deploy backup is for.

---

## What is deliberately not here

- **No monitoring or alerting.** With fifteen people on one machine, the failure
  is noticed in minutes by someone trying to use it. A pager rota for a team
  that sits together is ceremony. Revisit when it is serving people who are not
  in the room.
- **No high availability.** One machine. An hour of downtime costs a morning of
  inconvenience, not money — and a second machine doubles what can break.
- **No secret manager.** The password lives in `.env`, mode 600, on a machine
  only administrators can reach. A vault to hold one secret is a second system
  to keep running.

Each of these is a considered omission rather than an oversight. Revisit them
when the answer to "what does an hour of downtime cost?" changes.
