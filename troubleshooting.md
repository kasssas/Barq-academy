# Troubleshooting Journal

## Phase 1: Baseline Investigation

The baseline environment (commit `8442da3`) was investigated using:

- `docker compose config`
- `docker compose up -d`
- `docker compose ps`
- `docker compose logs --no-color --tail=200`
- `curl` requests against the running stack
- Python socket connectivity tests from inside `app-01`
- Source inspection of `app/server.py`, `docker-compose.yml`, `nginx/nginx.conf`, and `config/app.env`

---

## Baseline Findings

### 1. Application Healthcheck Mismatch

- **Symptom:** `docker compose ps` showed `app-01` and `app-02` as `unhealthy`. Application logs showed repeated `/healthz` requests returning HTTP 404.
- **Investigation:** Compared `docker-compose.yml` healthcheck configuration with `app/server.py` route definitions.
- **Root cause:** `docker-compose.yml` configured the healthcheck to request `/healthz`. The application defines `/health`, not `/healthz`.
- **Fix:** Updated the Docker healthcheck test URL in `docker-compose.yml` from `/healthz` to `/health`.
- **Verification:** After the fix, `docker compose ps` showed both app containers as `healthy`. The Docker healthcheck uses the `/health` endpoint. The separate `/ready` endpoint checks PostgreSQL and Redis connectivity and is not used by the Docker healthcheck.
- **Related commit:** Baseline `8442da3`; fix in `5c9ca06`.

---

### 2. PostgreSQL Port Mismatch

- **Symptom:** Application could not reach PostgreSQL during initialization and readiness checks.
- **Investigation:** Inspected `config/app.env` and `docker-compose.yml`. Ran `socket.create_connection(('postgres', 5433), 2)` from inside `app-01`.
- **Root cause:** `config/app.env` configured PostgreSQL at port `5433`. PostgreSQL listens on container port `5432`. The socket test returned `ConnectionRefusedError: [Errno 111] Connection refused`.
- **Fix:** Updated `config/app.env` to use port `5432` for PostgreSQL.
- **Verification:** After the fix, socket test to `postgres:5432` returned `POSTGRES CONNECTED`. The `/ready` endpoint returned HTTP 200 after all connectivity issues in Group 2 were resolved.
- **Related commit:** Baseline `8442da3`; fix in `5992c22`.

---

### 3. Redis Port Mismatch

- **Symptom:** Application could not reach Redis during initialization and readiness checks.
- **Investigation:** Inspected `config/app.env` and `docker-compose.yml`. Ran `socket.create_connection(('redis', 6380), 2)` from inside `app-01`.
- **Root cause:** `config/app.env` configured Redis at port `6380`. Redis listens on container port `6379`. The socket test returned `ConnectionRefusedError: [Errno 111] Connection refused`.
- **Fix:** Updated `config/app.env` to use port `6379` for Redis.
- **Verification:** After the fix, socket test to `redis:6379` returned `REDIS CONNECTED`.
- **Related commit:** Baseline `8442da3`; fix in `5992c22`.

---

### 4. PostgreSQL Credential Mismatch

- **Symptom:** Baseline configuration inspection identified a PostgreSQL credential mismatch. The incorrect PostgreSQL port initially prevented the application from reaching PostgreSQL to demonstrate authentication failure.
- **Investigation:** Compared the password value in `config/app.env` against the `POSTGRES_PASSWORD` configured for the PostgreSQL service in Compose.
- **Root cause:** The password in `config/app.env` did not match the password expected by PostgreSQL.
- **Fix:** Aligned the application-side password with the PostgreSQL service configuration.
- **Verification:** After correcting both the port and the credentials, successful PostgreSQL connectivity was verified. A `POST /records` request created a record; a subsequent `GET /records` returned it successfully.
- **Related commit:** Baseline `8442da3`; fix in `5992c22`.

---

### 5. Flask Bind Address Mismatch

- **Symptom:** NGINX could not reach the Flask application through the Docker network.
- **Investigation:** Inspected `app/server.py` and the `APP_HOST` environment variable in `docker-compose.yml`.
- **Root cause:** `Compose` set `APP_HOST=127.0.0.1`, binding Flask to loopback only. NGINX reaches the app over the Docker bridge network, which requires binding on `0.0.0.0`.
- **Fix:** Changed `APP_HOST` to `0.0.0.0` in `docker-compose.yml`.
- **Verification:** After the fix, `curl http://127.0.0.1:8080/` returned HTTP 200.
- **Related commit:** Baseline `8442da3`; fix in `5c9ca06`.

---

### 6. NGINX Upstream Port Mismatch

- **Symptom:** NGINX could not proxy traffic to `app-01`.
- **Investigation:** Inspected `nginx/nginx.conf` upstream block.
- **Root cause:** The upstream block configured `app-01:8081` while the Flask application listens on port `8080` (set via `APP_PORT`).
- **Fix:** Corrected the upstream port for `app-01` to `8080` in `nginx/nginx.conf`.
- **Verification:** After the fix, requests were successfully proxied to both `app-01` and `app-02`. Ten repeated requests to `/instance` alternated between both instances.
- **Related commit:** Baseline `8442da3`; fix in `5c9ca06`.

---

### 7. NGINX Published Port Mismatch

- **Symptom:** NGINX was not reachable on the expected host port.
- **Investigation:** Compared the NGINX `listen` directive in `nginx.conf` with the Compose `ports` mapping.
- **Root cause:** NGINX listens on container port `80`. Compose mapped `127.0.0.1:${PUBLIC_PORT:-8080}:81`, targeting container port `81` instead of `80`.
- **Fix:** Corrected the Compose port mapping to target container port `80`.
- **Verification:** After the fix, `docker compose ps` showed `nginx` published on `127.0.0.1:8080 -> 80/tcp`.
- **Related commit:** Baseline `8442da3`; fix in `5c9ca06`.

---

### 8. Duplicate Instance Identity

- **Symptom:** The `/instance` endpoint on `app-02` reported `instance_id: app-01`.
- **Investigation:** Inspected the `app-02` environment block in `docker-compose.yml`.
- **Root cause:** `INSTANCE_ID` for `app-02` was set to `app-01` (copy-paste error).
- **Fix:** Updated `INSTANCE_ID` in the `app-02` block to `app-02`.
- **Verification:** After the fix, `/instance` returned the correct `app-02` identifier for the second instance.
- **Related commit:** Baseline `8442da3`; fix in `5c9ca06`.

---

### 9. PostgreSQL Persistence Misconfiguration

- **Symptom:** Database records were not expected to survive PostgreSQL container recreation.
- **Investigation:** Inspected `docker-compose.yml` volume configuration. Ran `docker volume inspect barq-assessment_postgres-data`. Mounted an Alpine container with the volume to confirm it was empty.
- **Root cause:** The `postgres-data` named volume was mounted at `/var/lib/postgresql/backup` (a non-standard path). A `tmpfs` volume was mounted at `/var/lib/postgresql/data` (the actual data directory), making database storage ephemeral.
- **Fix:** Remounted `postgres-data` to `/var/lib/postgresql/data`. Removed the `tmpfs` mount.
- **Verification:** Created a record via `POST /records` with `{"title":"persistence-test"}`. Recreated the PostgreSQL container using `docker compose rm -s -f postgres` followed by `docker compose up -d postgres`. The record was still returned by `GET /records`, confirming persistence across container recreation. Note: the first test attempt used `{"name":"persistence-test"}` which was rejected with `title_must_be_1_to_200_characters` — this was a request-field error, not a persistence failure.
- **Related commit:** Baseline `8442da3`; fix in `58ae345`.

---

## Phase 2: Fix Group 1 — Application and NGINX Routing

**Fixes applied (commit `5c9ca06`):**
- Flask bind address changed from `127.0.0.1` to `0.0.0.0`
- Docker healthcheck endpoint corrected from `/healthz` to `/health`
- `app-02` instance identity corrected from `app-01` to `app-02`
- NGINX upstream port for `app-01` corrected to `8080`
- NGINX Compose port mapping corrected to target container port `80`

**Verification:**
1. `docker compose config` — passed.
2. `docker compose up -d --force-recreate` — completed successfully.
3. `docker compose ps` — `app-01: healthy`, `app-02: healthy`, `nginx: Up 127.0.0.1:8080 -> 80`.
4. `curl -i http://127.0.0.1:8080/` — HTTP 200, `X-Instance-ID: app-01`.
5. `curl -i http://127.0.0.1:8080/health` — HTTP 200.
6. `curl -i http://127.0.0.1:8080/instance` — HTTP 200, `instance_id: app-01`.
7. Ten repeat requests to `/instance` alternated between `app-01` and `app-02`.

*The `/ready` endpoint was not fully claimed at this stage; database and cache connectivity were pending.*

---

## Phase 2: Fix Group 2 — PostgreSQL and Redis Connectivity

**Fixes applied (commit `5992c22`):**
- PostgreSQL port corrected to `5432` in `config/app.env`
- Redis port corrected to `6379` in `config/app.env`
- PostgreSQL password aligned between the application and the PostgreSQL service

**Verification:**
1. `git diff --check` — passed.
2. `docker compose up -d --force-recreate app-01 app-02` — completed.
3. Both app containers returned `healthy`.
4. `/ready` returned HTTP 200 through NGINX.
5. `POST /records` successfully created a record.
6. `GET /records` returned the previously created record, proving PostgreSQL read/write.
7. Repeated `GET /counter` calls incremented the counter, proving Redis operations.
8. Socket tests from inside `app-01`: `POSTGRES CONNECTED`, `REDIS CONNECTED`.

---

## Phase 2: Fix Group 3 — PostgreSQL Persistence and Network Isolation

**Fixes applied (commit `58ae345`):**
- `postgres-data` volume remounted to `/var/lib/postgresql/data`
- PostgreSQL `tmpfs` mount removed
- PostgreSQL host port `15432` removed
- Redis host port `16379` removed
- NGINX removed from the `backend` network

**Verification:**
- `docker compose config` — passed.
- `docker compose ps` — PostgreSQL and Redis show no host port mappings; NGINX published on `127.0.0.1:8080` only.
- Record created, PostgreSQL recreated, record confirmed to survive — persistence proven.
- Network inspection confirmed:
  - NGINX: `frontend` only
  - `app-01`, `app-02`: `frontend` + `backend`
  - `postgres`: `backend` only
  - `redis`: `backend` only

---

## Phase 2: Fix Group 4 — Runtime Reliability (commit `80d405d`)

**Changes applied:**
- `restart: unless-stopped` added to all services.
- CPU and memory resource limits configured.

**Verification:**
- `docker compose config` — confirmed `restart` and `deploy.resources.limits` present on all services.

---

## Phase 2: Fix Group 5 — Security Controls (commit `1a1d567`)

**Changes applied:**
- `config/app.env` removed from Git tracking; added to `.gitignore` and `.dockerignore`.
- Dockerfile no longer copies `config/app.env` into the image.
- PostgreSQL password supplied via `BARQ_POSTGRES_PASSWORD` environment variable in Compose.
- Application Dockerfile runs Flask under non-root user `app` (UID `10001`).

**Verification:**
- `git check-ignore config/app.env` — confirmed tracked exclusion.
- Non-root `id` check inside the running `app-01` container — confirmed UID `10001`.
- Secret file absence confirmed inside the application container.

---

## Phase 3: Validation Testing (commit `4034e2f`)

`python3 validate.py` was implemented and executed against the running environment.

The script performs bounded checks for:
- Public access via NGINX on `http://127.0.0.1:8080`
- Endpoint responses: `/`, `/health`, `/ready`, `/instance`, `/records`, `/counter`
- PostgreSQL and Redis readiness via `/ready`
- Traffic distribution across both app instances
- Network and port expectations

---

## Phase 3: Failure and Recovery Testing (commit `21e3475`)

`python3 failure_test.py` was implemented and executed.

**Test procedure:** `app-01` was stopped abruptly while requests were running.

**Observed result:**
- During the failure window: **15 of 30 requests failed**. Successful requests were served by `app-02`.
- After restarting `app-01`: **40 of 40 requests succeeded**, with both instances available.

**Interpretation:** The test demonstrates that `app-02` continued to serve traffic during the failure window. Transient request failures were observed when `app-01` was abruptly stopped. This is expected behaviour with static upstream configuration; it is not claimed as zero-downtime failover.

---

## Phase 3: Backup and Restore Testing (commit `187c49f`)

`backup.sh` and `restore.sh` were implemented.

**Test procedure:**
1. Ran `./backup.sh` to create a local backup.
2. Introduced a subsequent database change via `POST /records`.
3. Ran `./restore.sh <backup_file>` to restore from the backup.
4. Confirmed the later change was removed and the original state (prior to the backup) was restored via `GET /records`.

**Result:** Backup and restore functionality was verified locally. Backups are stored on the local host and are not encrypted or stored off-host.

---

## Historical Log Analysis (commits `ed281b7`)

`analyze_logs.py` was implemented and run against the three supplied historical log files (`logs/access.log`, `logs/error.log`, `logs/application.log`).

Key findings (see `log_analysis.md` for full details):
- **720 distinct requests** over a 30-minute window.
- **14.58% error rate** (105 failures out of 720 requests).
- Three distinct incident phases: connection-refused (502s), dependency errors (503s), upstream timeouts (504s).
- The `dependency_error` events in `application.log` do not identify the specific failed dependency (PostgreSQL vs Redis) by name. No claim is made about which dependency caused the 503 phase based on these logs alone.

---

## CI Validation (commit `c5b5e82`)

The GitHub Actions workflow (`.github/workflows/ci.yml`) was created and validated. It performs: checkout → Compose validation → build → start → poll `/ready` → run `validate.py` → cleanup.

The CI workflow validates the Compose configuration and performs an integration-style stack startup inside GitHub Actions. It does not claim to prove production readiness.
