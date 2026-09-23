# Architectural Decisions and Tradeoffs (BARQ Academy DevOps Assessment)

This document records the key architectural decisions, tradeoffs, and limitations for the BARQ Academy DevOps application stack. It serves as a professional engineering decision record based on the actual repository state and implementation history.

## 1. Network Separation (Frontend vs. Backend)
* **Decision:** Implement separate Docker networks for public and internal traffic.
* **Context / problem:** The application stack includes public-facing components (NGINX), application logic (Flask), and private data stores (PostgreSQL, Redis). Exposing data stores to a generalized network introduces broader access than necessary.
* **Chosen approach:** Implemented two distinct Docker networks: `frontend` and `backend`. NGINX resides strictly on the `frontend` network, the data stores on the `backend` network, and the application containers bridge both networks.
* **Alternatives considered:** A single unified network for all containers.
* **Tradeoffs:** Increases the complexity of the network configuration in Compose but achieves separation of concerns, ensuring the topology prevents NGINX from sharing the backend network.
* **Evidence / verification:** The `docker-compose.yml` explicitly defines these segregated networks and assigns them locally to the respective containers.
* **Limitations or production considerations:** In a managed orchestrator (e.g., Kubernetes), internal network separation is typically handled via dynamic NetworkPolicies rather than isolated static networks.

## 2. Database Exposure and Secrets Management
* **Decision:** Block host-port exposure and extract hardcoded secrets into runtime environment variables.
* **Context / problem:** Publishing database ports to the host and hardcoding secrets in version control introduce security risks.
* **Chosen approach:** Removed host port mappings for PostgreSQL (5432) and Redis (6379), keeping access internal via service-name resolution within the Docker network. Database passwords were removed from Compose files and source code, instead utilizing environment variables populated dynamically.
* **Alternatives considered:** Publishing ports for easier local debugging; using advanced secret injection (e.g., HashiCorp Vault).
* **Tradeoffs:** Debugging the databases locally from the host requires proxying or attaching to a container (`docker exec`), which increases friction but avoids external host-level port mapping.
* **Evidence / verification:** The repository state shows no published ports for `db` and `redis`. The `docker-compose.yml` sources `POSTGRES_PASSWORD` from the environment.
* **Limitations or production considerations:** The current approach relies on environment variables, which can leak in process listings. A production setup requires a dedicated secrets manager or native orchestrator secrets.

## 3. Non-Root Container Execution
* **Decision:** Execute the application instances as a restricted, non-root user.
* **Context / problem:** Running application containers as the `root` user violates defense-in-depth principles.
* **Chosen approach:** Modified the Python application `Dockerfile` to create a dedicated user named `app` with UID `10001` and execute the Flask application using this non-root user.
* **Alternatives considered:** Leaving the default root user for simplicity.
* **Tradeoffs:** Requires explicitly assigning directory ownership (`chown`) during the image build for any required operational directories.
* **Evidence / verification:** The verified `Dockerfile` establishes the `app` user (UID 10001) and specifies the `USER` directive before the `CMD` invocation step.
* **Limitations or production considerations:** The base image or system libraries might have sub-processes assuming root access. A production environment might enforce execution bounds systematically using settings like `runAsNonRoot: true`.

## 4. Database Persistence and Restart Policies
* **Decision:** Implement dedicated volumes for data stores alongside explicit restart strategies.
* **Context / problem:** Containers are ephemeral; stopping or deleting a database container leads to data loss unless persistence is configured. Services also need to recover automatically from interruptions.
* **Chosen approach:** Configured a Docker named volume mounted at `/var/lib/postgresql/data` for PostgreSQL. For Redis, enabled append-only file persistence (`--appendonly yes`) mapped to a persistent volume. Applied `restart: unless-stopped` to critical services.
* **Alternatives considered:** Host bind mounts, or running temporarily in-memory without persistence.
* **Tradeoffs:** Named volumes consume disk space managed directly by Docker. Redis AOF impacts write performance slightly compared to pure in-memory execution.
* **Evidence / verification:** The `docker-compose.yml` explicitly defines the volumes, uses the `restart: unless-stopped` directive, and sets the specific Redis command arguments.
* **Limitations or production considerations:** Standalone Docker volumes provided by this Compose configuration do not yield high availability or distributed resilient storage.

## 5. Health vs. Readiness Checks and Proxy Reliability
* **Decision:** Define explicit container health checks to govern NGINX startup constraints.
* **Context / problem:** NGINX needs to wait for application containers to boot before starting and routing traffic.
* **Chosen approach:** In Compose, NGINX uses a `depends_on` condition requiring the app containers to reach `condition: service_healthy`. This is driven by Docker's application healthcheck checking the basic `/health` endpoint. A separate overarching application endpoint, `/ready`, explicitly checks PostgreSQL and Redis connectivity.
* **Alternatives considered:** Relying purely on Docker's default container running state.
* **Tradeoffs:** NGINX startup is delayed until the `/health` endpoint passes, extending initial full-stack boot time logic.
* **Evidence / verification:** The `docker-compose.yml` includes the `depends_on` rules leveraging the `/health` Docker healthcheck configuration, while `/ready` is distinctly mapped in the application logic.
* **Limitations or production considerations:** NGINX relies on Docker's native healthcheck definition to govern startup. Ongoing active health checking of upstreams dynamically at the proxy level often requires proxy-specific mechanisms (e.g., NGINX Plus) beyond static container boot dependencies.

## 6. Automated Failure Validation and Failover Realities
* **Decision:** Document explicit failure testing while acknowledging the realistic bounds of mid-flight request drops.
* **Context / problem:** Measuring failover resilience provides an accurate professional picture of system behavior under distress.
* **Chosen approach:** Developed a validation script (`failure_test.py`) to systematically stop an upstream node while measuring request success rates, explicitly recording transient failures.
* **Alternatives considered:** Skipping disruption tests or relying theoretically on orchestration behavior.
* **Tradeoffs:** Recognizing real connection drops proves operational rigor, rather than making theoretical assumptions about seamless failover.
* **Evidence / verification:** The actual failure test systematically stopped `app-01` and observed exactly 15 failures out of 30 requests during the failure window. The successful requests were actively served by `app-02`. After full recovery, 40/40 requests succeeded flawlessly.
* **Limitations or production considerations:** The test demonstrates surviving-backend service provision, but also exposes transient request failures when an upstream is abruptly stopped. Operational production configurations typically employ active outlier detection and retry layers to mitigate these sudden drops.

## 7. CI Pipeline Validation with Compose
* **Decision:** Execute automated Docker Compose validation natively inside the CI pipeline.
* **Context / problem:** Merging infrastructural changes without verifying stack components creates risks for deployments.
* **Chosen approach:** Implemented a GitHub Actions workflow (`ci.yml`) that validates the Docker Compose configuration by performing an actual integration-style stack startup and validation inside the workflow runner.
* **Alternatives considered:** Running isolated unit tests without executing the orchestrative stack.
* **Tradeoffs:** Spinning up the full stack takes extra execution time compared to isolated tests but practically validates integration constraints.
* **Evidence / verification:** The `.github/workflows/ci.yml` starts Docker Compose physically inside GitHub Actions and executes the target programmatic checks.
* **Limitations or production considerations:** This workflow validates integration, but running stateful databases in ephemeral CI runners is highly scoped and scales poorly. Complex architectures usually require dedicated staged deployment environments.

## 8. Objective Log Analysis and Limitation Acknowledgment
* **Decision:** Ensure forensic log analysis restricts conclusions to verifiable text artifacts.
* **Context / problem:** A historical incident resulted in HTTP 503 errors and internal `dependency_error` logs. Identifying the root cause is critical, but extrapolating beyond literal data creates inaccurate incident reports.
* **Chosen approach:** The historical log analysis restricts its conclusions to direct textual evidence, correlating final HTTP 503 errors to the abstract `dependency_error` events within `application.log`.
* **Alternatives considered:** Guessing whether Redis or PostgreSQL caused the cascading failure based on typical patterns.
* **Tradeoffs:** The analysis lacks a definitive source component for the 503 incident phase, but maintains factual rigor.
* **Evidence / verification:** The resulting log report refrains from claiming "PostgreSQL" or "Redis" unless the raw logs supply those exact strings. The `dependency_error` records provided generic events without specific labels.
* **Limitations or production considerations:** The raw application logs must be enhanced to inject deterministic dependency context into structured records during exception handling, enabling actionable root-cause observability.
