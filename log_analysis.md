# Log analysis

## Commands / scripts
The analysis was performed using the `analyze_logs.py` Python script. The script parses all three text logs (`access.log`, `error.log`, `application.log`), strictly validates records line-by-line using exact duplicate removal, natively generates exact 5-minute time buckets, and avoids double-counting retries.

## Results

1. **What UTC interval is covered? How many valid, malformed and duplicate lines are in each file?**
   - **Request-log Interval**: 2026-08-20T11:00:00.015Z to 2026-08-20T11:29:57.578Z
   - **access.log**: 726 total lines, 725 valid JSON records, 1 malformed line, 5 exact duplicate lines.
   - **error.log**: 68 total lines, 68 valid expected-format NGINX text records, 0 malformed lines, 0 duplicates. (Note: error.log also explicitly contains a log-rotation notice at `2026-08-20 11:30:00Z`).
   - **application.log**: 730 total lines, 729 valid JSON records, 1 malformed line, 2 exact duplicate lines.

2. **How many distinct client requests occurred? How did you deduplicate and avoid counting retries twice?**
   - **Distinct requests:** 720 distinct client request IDs.
   - **Deduplication strategy:** We used the primary key `request_id` to deduplicate client requests only after initially dropping exact line duplicates. Upstream retries appear as comma-separated values in the `upstream` values mapping, meaning they are inherently grouped within one initial record and not double-counted.

3. **What are the final client status counts and error rate? State your denominator.**
   - Total distinct requests (Denominator): **720**
   - Failed requests (HTTP >= 400): **105**
   - Final error rate: **14.58%**
   - Status Counts: HTTP 200 (615), HTTP 404 (10), HTTP 502 (40), HTTP 503 (47), HTTP 504 (8).

4. **Which paths, time windows and backends account for the failures?**
   - **Paths**: `/records` (26 failures), `/counter` (26), `/ready` (23), `/missing` (10), `/health` (10), `/` (10).
   - **Backends**: `172.23.0.12:8080` (73 failures), `172.23.0.11:8080` (32 failures).
   - **Exact 5-minute failure buckets**:
     - `11:00:00-11:04:59 = 2`
     - `11:05:00-11:09:59 = 42`
     - `11:10:00-11:14:59 = 24`
     - `11:15:00-11:19:59 = 10`
     - `11:20:00-11:24:59 = 17`
     - `11:25:00-11:29:59 = 10`

5. **What are the median and p95 client latencies? State the percentile method and units.**
   - **Median**: 0.054 s
   - **p95**: 2.001 s
   - **Max**: 2.025 s
   - **Method**: Percentiles calculated using standard linear interpolation.
   - **Units**: Seconds (via NGINX `$request_time`).

6. **Which requests retried upstream? How many succeeded after retrying?**
   - **Retries**: 19 requests had multiple upstream attempts.
   - **Ultimately Succeeded**: All 19 ultimately returned HTTP 200.

## Timeline and correlated examples

7. **Build an incident timeline using evidence from access, error AND application logs.**
   - `11:00:00-11:04:59`: Normal initial traffic.
   - `11:05:00-11:09:59`: `error.log` records 111 Connection refused strings. `access.log` logs native traffic retries successfully but also logs final HTTP 502 status failures.
   - `11:10:00-11:24:59`: `application.log` flags `dependency_error` events. This is correlated directly to multiple `access.log` 503 internal server errors across endpoints.
   - `11:25:00-11:29:59`: `error.log` flags upstream timeouts reading headers. `access.log` shows final HTTP 504 delays. `application.log` eventually finishes handling the request, notably long after the NGINX timeouts limit triggered string responses (as exhibited by `duration_ms` outputs taking longer than 2s).

8. **Show one correlated failed request and one successful request. Include IDs and timestamps.**
   - **Retry Success (lab-000124):**
     - `access log`: `11:05:07.620Z`, final 200, upstream `172.23.0.12:8080,172.23.0.11:8080`, upstream_status `502,200`
     - `error log`: connection refused to .12
     - `application log`: app-01 returned 200 at `11:05:07.620Z`
   - **Failed Request (504 Timeout - lab-000606):**
     - `access log`: `11:25:14.501Z`, final 504, request_time 2.001s
     - `error log`: upstream timed out
     - `application log`: app-02 returned 200 at `11:25:15.200Z` with duration_ms 2700

## Conclusions and limits

9. **Which errors appear to be proxy/connectivity issues versus dependency/application issues? What proves it?**
   - **Proxy/connectivity issues**: 59 NGINX connection-refused records exist overall in error logs, with 40 correlating to final client HTTP 502 failures in the access log. Separately, 8 final HTTP 504 failures correspond strictly to NGINX upstream timeouts in error.log.
   - **Dependency/application issues**: 47 final HTTP 503 failures correlate with application `dependency_error` events recorded inside application.log. Note: these records do NOT specifically label the dependency name (e.g. Postgres vs Redis).

10. **What do the logs not prove? What would you check next in a running environment?**
    - The raw logs provide generalized `dependency_error` strings without identifying PostgreSQL or Redis. Thus, the specific dependency cannot be determined solely via these logs.
    - They don't prove resource conditions like active Memory/CPU constraints limits.
    - **Next checks**: Inspect container limits tracking natively, inspect exact external databases connections strings directly inside their components, and analyze the specific environment OS parameters.
