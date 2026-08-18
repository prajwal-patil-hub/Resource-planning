# The application image.
#
# Two stages so the wheel-building toolchain never reaches the runtime image:
# a smaller image is a smaller thing to keep patched, and a runtime with no
# compiler is one fewer way for a foothold to become an exploit.
FROM python:3.12-slim AS build

WORKDIR /build
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

COPY requirements.txt .
# psycopg[binary] ships wheels, so nothing here needs to compile — but pinning
# the build stage anyway means adding a dependency that does compile will not
# silently start dragging gcc into production.
RUN pip install --no-cache-dir -r requirements.txt


FROM python:3.12-slim

# Runs as a non-root user. If the process is ever compromised, the blast radius
# stops at a user that owns nothing on the host.
RUN useradd --create-home --uid 10001 rp

# Deliberately no extra packages. Two things that would obviously belong here
# are not:
#
# - `postgresql-client`, for backups. Whatever version Debian ships could drift
#   from the database's, and `pg_dump` older than its server refuses to run. The
#   backup service uses the `postgres` image instead, so the tool taking the
#   dump is by construction the same version as the server producing it.
# - `curl`, for the health check. The image already has Python; adding a second
#   HTTP client to make one request is a package to keep patched for nothing.
#
# What is left is the smallest thing that runs the app.

COPY --from=build /venv /venv
ENV PATH="/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --chown=rp:rp . /app

USER rp
EXPOSE 8000

# No --reload, one process per container: the supervisor restarts it, and two
# workers sharing one container hide a crash from the health check.
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
