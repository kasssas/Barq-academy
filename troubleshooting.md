# Troubleshooting Journal

## Phase 1: Baseline Investigation Methodology

The baseline was investigated using the following commands and techniques:
* `docker compose config`
* `docker compose up -d`
* `docker compose ps`
* `docker compose logs --no-color --tail=200`
* `curl`
* Python socket connectivity tests from inside `app-01`
* Source inspection of the relevant application and Compose/NGINX configuration

---

## Findings

### 1. Application healthcheck mismatch
- **Symptom**: `docker compose ps` showed both `app-01` and `app-02` as `unhealthy`. Application logs showed repeated `/healthz` requests returning HTTP 404.
- **Hypothesis**: The Docker healthcheck endpoint configuration does not match the actual application definition.
- **Command / test**: `docker compose ps`, application log inspection, and inspecting `app/server.py` and `docker-compose.yml`.
- **Actual output / evidence**: `app/server.py` defines `/health`. `docker-compose.yml` healthcheck requests `/healthz`, which causes the 404 errors in the logs.
- **Root cause or current finding**: The Compose file contains a typo/misconfiguration for the healthcheck URL (`/healthz` instead of `/health`).
- **Planned fix**: (Planned / not yet applied) Update the healthcheck test in `docker-compose.yml` to request `/health` instead of `/healthz`.
- **Retest evidence**: (Not yet performed)
- **Related commit**: Baseline evidence was collected from the environment built from commit `8442da3`. No fix commit exists yet.
- **Remaining uncertainty**: None.

### 2. PostgreSQL connectivity mismatch
- **Symptom**: Application cannot reach PostgreSQL database during initialization/readiness checks.
- **Hypothesis**: The application is trying to connect to the wrong port for PostgreSQL.
- **Command / test**: Source inspection of `config/app.env` and `docker-compose.yml`, plus running `socket.create_connection(('postgres',5433),2)` from inside `app-01`.
- **Actual output / evidence**: `docker compose ps` showed PostgreSQL healthy on `5432/tcp`. `config/app.env` configures PostgreSQL as `postgres:5433`. The socket test failed with: `ConnectionRefusedError: [Errno 111] Connection refused`.
- **Root cause or current finding**: The configuration in `config/app.env` expects PostgreSQL on port `5433`, but the container natively listens on port `5432`.
- **Planned fix**: (Planned / not yet applied) Update `config/app.env` to point to port `5432` instead of `5433`.
- **Retest evidence**: (Not yet performed)
- **Related commit**: Baseline evidence was collected from the environment built from commit `8442da3`. No fix commit exists yet.
- **Remaining uncertainty**: Need to retest once the port is corrected to see if there are secondary database issues (like bad credentials).

### 3. Redis connectivity mismatch
- **Symptom**: Application cannot reach Redis during initialization/readiness checks.
- **Hypothesis**: The application is trying to connect to the wrong port for Redis.
- **Command / test**: Source inspection of `config/app.env` and `docker-compose.yml`, plus running `socket.create_connection(('redis',6380),2)` from inside `app-01`.
- **Actual output / evidence**: `docker compose ps` showed Redis healthy on `6379/tcp`. `config/app.env` configures Redis as `redis:6380`. The socket test failed with: `ConnectionRefusedError: [Errno 111] Connection refused`.
- **Root cause or current finding**: The configuration in `config/app.env` expects Redis on port `6380`, but the container natively listens on port `6379`.
- **Planned fix**: (Planned / not yet applied) Change the Redis port in `config/app.env` to `6379`.
- **Retest evidence**: (Not yet performed)
- **Related commit**: Baseline evidence was collected from the environment built from commit `8442da3`. No fix commit exists yet.
- **Remaining uncertainty**: None.

### 4. PostgreSQL credential mismatch
- **Symptom**: Expected authentication mismatch (though masked by the connection refused error).
- **Hypothesis**: Database passwords do not align between application and infrastructure.
- **Command / test**: Source and configuration inspection.
- **Actual output / evidence**: `config/app.env` uses a password ending in `K8d`. `docker-compose.yml` configures PostgreSQL with a password ending in `K8c`.
- **Root cause or current finding**: Configuration mismatch between the application environment configuration and the database initialization secrets.
- **Planned fix**: (Planned / not yet applied) Ensure the application environment connects with the correct password (`K8c`).
- **Retest evidence**: (Not yet performed)
- **Related commit**: Baseline evidence was collected from the environment built from commit `8442da3`. No fix commit exists yet.
- **Remaining uncertainty**: We have not run a proven authentication failure test because the wrong port prevented the app from reaching PostgreSQL in the first place.

### 5. Flask bind address mismatch
- **Symptom**: Baseline configuration indicates that NGINX cannot reach the application through the Docker network because the Flask process is bound to loopback.
- **Hypothesis**: The application is binding only to `localhost` rather than all interfaces.
- **Command / test**: Source/config inspection of `app/server.py` and `docker-compose.yml`.
- **Actual output / evidence**: `app/server.py` uses `APP_HOST` as the Flask bind address. Compose sets `APP_HOST=127.0.0.1`.
- **Root cause or current finding**: A bind address of `127.0.0.1` restricts the container process to loopback only. NGINX needs to reach the application through the Docker network interface.
- **Planned fix**: (Planned / not yet applied) Change `APP_HOST` to `0.0.0.0` in `docker-compose.yml`.
- **Retest evidence**: (Not yet performed)
- **Related commit**: Baseline evidence was collected from the environment built from commit `8442da3`. No fix commit exists yet.
- **Remaining uncertainty**: None.

### 6. NGINX upstream port mismatch
- **Symptom**: Baseline configuration indicates that NGINX is configured with an incorrect upstream port for app-01.
- **Hypothesis**: NGINX is configured to forward traffic to the wrong internal ports.
- **Command / test**: Source/config inspection of `nginx/nginx.conf` and `docker-compose.yml`.
- **Actual output / evidence**: Flask apps run on `APP_PORT=8080`. However, `nginx/nginx.conf` is configured to send traffic to `app-01:8081` and `app-02:8080`.
- **Root cause or current finding**: The `nginx.conf` upstream block contains an incorrect port `8081` for `app-01`.
- **Planned fix**: (Planned / not yet applied) Change the port for `app-01` to `8080` in `nginx/nginx.conf`.
- **Retest evidence**: (Not yet performed)
- **Related commit**: Baseline evidence was collected from the environment built from commit `8442da3`. No fix commit exists yet.
- **Remaining uncertainty**: None.

### 7. NGINX published target port mismatch
- **Symptom**: NGINX is inaccessible on the expected host port mappings.
- **Hypothesis**: The host-to-container port mapping in Compose does not align with NGINX's listen port.
- **Command / test**: Source/config inspection.
- **Actual output / evidence**: NGINX listens on container port `80` (per `nginx.conf`). Compose publishes `127.0.0.1:${PUBLIC_PORT:-8080}:81`.
- **Root cause or current finding**: The container port configured in Compose mapping (`:81`) differs from the actual NGINX listening port (`:80`).
- **Planned fix**: (Planned / not yet applied) Correct the NGINX ports configuration in `docker-compose.yml` to route to container port `80`.
- **Retest evidence**: (Not yet performed)
- **Related commit**: Baseline evidence was collected from the environment built from commit `8442da3`. No fix commit exists yet.
- **Remaining uncertainty**: None.

### 8. Duplicate app identity
- **Symptom**: Identity headers and endpoints will incorrectly double-report the same instance.
- **Hypothesis**: The environment variable setting for `INSTANCE_ID` was copy-pasted or misconfigured.
- **Command / test**: Source/config inspection.
- **Actual output / evidence**: In `docker-compose.yml`, the environment for `app-02` sets `INSTANCE_ID=app-01`.
- **Root cause or current finding**: Duplicate hardcoded variable in Compose config.
- **Planned fix**: (Planned / not yet applied) Update `INSTANCE_ID` in `app-02` block to read `app-02`.
- **Retest evidence**: (Not yet performed)
- **Related commit**: Baseline evidence was collected from the environment built from commit `8442da3`. No fix commit exists yet.
- **Remaining uncertainty**: None.

### 9. PostgreSQL persistence configuration concern
- **Symptom**: Database records are likely to be lost during container restarts or recreation.
- **Hypothesis**: Volume mount locations are misaligned with PostgreSQL's actual data directory.
- **Command / test**: Source/config inspection of `docker-compose.yml`.
- **Actual output / evidence**: `postgres-data` named volume is mounted at `/var/lib/postgresql/backup`. A `tmpfs` volume is mounted at `/var/lib/postgresql/data`.
- **Root cause or current finding**: The `tmpfs` mount at the standard data path (`/var/lib/postgresql/data`) prevents disk persistence, and the named volume is mounted to a non-standard redundant path (`/backup`).
- **Planned fix**: (Planned / not yet applied) Mount the `postgres-data` volume to `/var/lib/postgresql/data` and remove the `tmpfs` directive.
- **Retest evidence**: (Not yet performed) Data loss has not yet been experimentally proven through a container recreation test. This requires a targeted persistence/recreation test following repairs.
- **Related commit**: Baseline evidence was collected from the environment built from commit `8442da3`. No fix commit exists yet.
- **Remaining uncertainty**: Need to prove record survival across PostgreSQL recreation once fixed.

---

## Phase 2: Fix Group 1 (Application + NGINX routing) Retest Evidence

The following fixes were implemented and verified on the Ubuntu runtime environment:
* Flask bind address (changed `APP_HOST` to `0.0.0.0`)
* Application healthcheck endpoint (changed from `/healthz` to `/health`)
* `app-02` instance identity (changed `INSTANCE_ID` to `app-02`)
* NGINX upstream port for `app-01` (changed to `8080`)
* NGINX published container port (changed mapping to `:80`)

### Verification Evidence
1. `docker compose config` completed successfully after the changes.
2. `docker compose up -d --force-recreate` completed successfully.
3. `docker compose ps` showed:
   * app-01: healthy
   * app-02: healthy
   * nginx: Up, host 127.0.0.1:8080 -> container 80
   * postgres: healthy
   * redis: healthy
4. `curl -i http://127.0.0.1:8080/` returned HTTP 200 and `X-Instance-ID: app-01`.
5. `curl -i http://127.0.0.1:8080/health` returned HTTP 200 and `X-Instance-ID: app-01`.
6. `curl -i http://127.0.0.1:8080/instance` returned HTTP 200 with `instance_id` app-01.
7. Ten repeated requests to `/instance` alternated between `app-01` and `app-02`, proving NGINX is routing traffic to both backend instances.

*Note: The `/ready` endpoint has not been fully verified and backend database/cache operations are not claimed as working yet, as PostgreSQL and Redis connection configurations are pending for the next fix group.*
