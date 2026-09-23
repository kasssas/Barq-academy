# Security Review (BARQ Academy DevOps Assessment)

This document provides a professional security review of the BARQ Academy application stack. It evaluates implemented controls against the actual repository configuration and identifies remaining production risks.

## Implemented Security Fixes

### 1. Secrets Management and Exclusion
* **Risk:** Hardcoding credentials in Git and embedding secrets directly into built container images exposes them to widespread unauthorized access.
* **Implemented control:** `config/app.env` was removed from Git tracking (`.gitignore`) and excluded from the Docker build context (`.dockerignore`). The Dockerfile no longer copies this file. The PostgreSQL password is supplied strictly through the `BARQ_POSTGRES_PASSWORD` environment variable rather than being hardcoded in Compose.
* **Evidence / verification:** `git check-ignore config/app.env` validates tracking exclusion. Verification confirms the secret file is absent inside the running application container. The `docker-compose.yml` natively parses `${BARQ_POSTGRES_PASSWORD}` dynamically.
* **Remaining limitation:** Environment variables containing sensitive credentials can still leak into process lists (`ps`) or crash dumps.

### 2. Network Exposure and Topology
* **Risk:** Exposing data stores directly to host interfaces invites brute-force attacks and unauthorized port scanning.
* **Implemented control:** Database services (PostgreSQL, Redis) do not publish any host ports. Furthermore, structural frontend/backend Docker network separation is enforced: NGINX operates only on the `frontend` network; the application containers bridge `frontend` and `backend`; and the databases are isolated strictly to the `backend`.
* **Evidence / verification:** Inspection of `docker-compose.yml` confirms no `ports` mapped natively for the `db` and `redis` services. Network membership inspection explicitly proves the segregation properties.
* **Remaining limitation:** Container components still rely on static bridge network isolation; this does not extend to sophisticated east-west cluster firewalling across distributed hosts.

### 3. Least Privilege Container Execution
* **Risk:** Running application containers as `root` expands the blast radius if an attacker escapes the application sandbox or exploits an RCE vulnerability.
* **Implemented control:** The application Dockerfile establishes a dedicated non-root user (`app`, UID `10001`) to execute the Flask application securely.
* **Evidence / verification:** Active non-root `id` verification confirms the execution context is successfully bound to UID 10001.
* **Remaining limitation:** This implementation secures the application layer, but base system libraries may theoretically still assume root access for specific operations without overarching orchestrator bounds (like dropping capabilities).

### 4. Resource Allocation and Proxy Governance
* **Risk:** Unbound containers can exhaust host CPU/memory resources (Noisy Neighbor), while proxy startup before backend readiness leads to unhandled request failures.
* **Implemented control:** CPU and memory resource limits are explicitly configured on services. NGINX relies on native Docker healthchecks using the `/health` endpoint for startup via a `depends_on` rule. A separate overarching application endpoint, `/ready`, checks the application's PostgreSQL and Redis dependency readiness. NGINX does not wait natively on `/ready`.
* **Evidence / verification:** The Compose file defines `deploy.resources.limits`. The `docker-compose.yml` explicitly shows NGINX waiting on the Docker healthcheck condition, which probes `/health`, while the `/ready` endpoint evaluates backing dependencies independently.
* **Remaining limitation:** Resource limits do not prevent the container itself from crashing (e.g., via internal memory overallocation) when targeted by aggressive payloads; they strictly protect the host from systemic exhaustion.

### 5. Persistence and Native Recovery
* **Risk:** Container ephemerality causes complete data loss across restarts or crashes if structural state is not durably managed.
* **Implemented control:** PostgreSQL utilizes a named volume mapped dynamically at `/var/lib/postgresql/data`. Redis explicitly enforces append-only file persistence (`--appendonly yes`) according to the active Compose configuration.
* **Evidence / verification:** The `docker-compose.yml` sets the volume parameters. Backup and restore functionality was verified locally. The CI workflow builds the images, starts the Compose environment, waits for readiness, and runs validate.py.
* **Remaining limitation:** Standalone Docker volumes do not natively backup data automatically off-host, nor operations occur with encryption-at-rest natively on the local filesystem.

## Production Security Improvements / Remaining Risks

### 6. Missing Encryption in Transit (TLS/HTTPS)
* **Risk:** Traffic between the external client and NGINX traverses in plaintext (HTTP), exposing end-user access to interception or tampering protocols.
* **Recommended control:** Terminate SSL/TLS natively on NGINX (via automated ACM or Let's Encrypt certificates) and explicitly enforce HTTPS redirection for all routes.
* **Why it matters:** HTTP traffic is not encrypted in transit and could expose requests or responses to interception on an untrusted network.
* **Why it is not claimed as implemented:** The current explicit NGINX configuration merely handles port 80/HTTP traffic actively.

### 7. Explicit Secrets Management (Vault/KMS)
* **Risk:** Passing sensitive credentials like `BARQ_POSTGRES_PASSWORD` solely via raw environment variables remains readable by an attacker with `docker inspect` permissions or in memory core dumps.
* **Recommended control:** Migrate to a dedicated secrets manager architecture (e.g., HashiCorp Vault, AWS Secrets Manager, or Kubernetes Secrets natively mapped to temporary memory files).
* **Why it matters:** Centralized secrets management offers programmatic rotation, cryptographic encryption, and tightly scoped access policies superior to `.env` distribution mechanics.
* **Why it is not claimed as implemented:** The assessed Compose environment relies exclusively on default environment injection populated manually during execution.

### 8. Pinned Versions and Continuous Vulnerability Scanning
* **Risk:** Using generic base tags (e.g., unpinned minors) and omitting image layer scanning aggressively exposes the stack to unpatched vulnerabilities or unverified image changes.
* **Recommended control:** Pin all image versions utilizing exact cryptographic digests (SHA-256). Introduce active CI-based supply-chain vulnerability scanning workflows (e.g., Trivy or Grype).
* **Why it matters:** Ensures deployment immutability and stops unverified, exploitable components from infiltrating the perimeter runtime.
* **Why it is not claimed as implemented:** The current CI workflow securely validates structural integration but lacks dedicated container vulnerability scanning layers.

### 9. Database High Availability and Encrypted Off-Host Backups
* **Risk:** A single PostgreSQL container node represents a single point of failure (SPOF); current local host-volume backups are susceptible to physical disk destruction scenarios.
* **Recommended control:** Implement automated database replication topologies or utilize explicitly managed cloud database resources (e.g., RDS). Transition backup targets to encrypted object storage buckets configured off-host.
* **Why it matters:** This reduces the risk of data loss from container or host-local failures.
* **Why it is not claimed as implemented:** The system structurally relies on localized standalone container persistence. While backups execute practically via local scripts, they lack cryptographic volume encryption or automated cloud egress integration.

## Security Testing Performed
* `git check-ignore` applied specifically against `config/app.env`.
* Secret file absence structurally verified directly inside the active application container.
* Target container structural non-root `id` verification performed against UID bounds.
* Active Compose configuration validation.
* Native network membership inspection against structural isolation.
* Execution of the standard programmatic validation script checking components.
* Failure/recovery test explicitly capturing operational backend service limits and transient fault properties.
* Concrete local backup/restore verification testing.
* GitHub Actions CI run validating the entire composition.
