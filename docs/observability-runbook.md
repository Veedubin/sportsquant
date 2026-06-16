# Observability Runbook

A comprehensive guide for using the Grafana OSS observability stack (Loki, Mimir, Tempo, Grafana) to monitor and debug the Sports Platform.

## Quick Start

### Access Grafana

```bash
# Port-forward to Grafana (runs in background)
kubectl port-forward -n monitoring svc/grafana 3000:3000 &

# Or run in foreground ( Ctrl+C to stop)
kubectl port-forward -n monitoring svc/grafana 3000:3000

# Open browser to http://localhost:3000
# Default credentials: admin / admin
```

### Default Credentials

| Service | Username | Password                        |
| ------- | -------- | ------------------------------- |
| Grafana | `admin`  | `admin` (change on first login) |

---

## Loki - Log Aggregation

### Access Loki via Grafana Explore

1. Navigate to **Explore** (sidebar icon)
2. Select **Loki** from the dropdown
3. Build LogQL queries to search logs

### Common LogQL Queries

#### Basic Queries

```logql
# All logs from the sports platform
{app="sports-platform"}

# All logs with error level
{app="sports-platform"} | level="error"

# Logs from a specific service
{app="betting-api"}
{app="unified-poller"}
{app="kafka-ignite-consumer"}
```

#### Filtering by League

```logql
# NBA poller logs
{app="unified-poller", league="NBA"}

# NFL poller logs
{app="unified-poller", league="NFL"}

# Error logs for a specific league
{app="unified-poller", league="NBA"} | level="error"
```

#### Time Range Filters

```logql
# Last 5 minutes
{app="sports-platform"} | __line__ | duration > 5s

# Last 1 hour with errors
{app="sports-platform", level="error"} | __line__

# Last 24 hours
{app="sports-platform"} | __line__ | line_format "{{.timestamp}} {{.level}} {{.message}}"
```

#### LogQL Examples for Common Tasks

```logql
# Find all exceptions with stack traces
{app="sports-platform"} | level="error" | trace_id != ""

# Find Kafka consumer errors
{app="kafka-ignite-consumer"} | level="error" | json | line_format "{{.message}}"

# Find API request failures
{app="betting-api"} | json | line_format "{{.timestamp}} {{.method}} {{.status}} {{.path}}"

# Find slow API requests (>1s)
{app="betting-api"} | json | duration > 1s | line_format "{{.timestamp}} {{.path}} took {{.duration}}"

# Find poller rate limit issues
{app="unified-poller"} | json | rate_limit_remaining < 10
```

#### Parsing JSON Logs

```logql
# Extract fields from JSON logs
{app="betting-api"} | json | line_format "{{.timestamp}} {{.level}} {{.message}} [trace={{.trace_id}}]"

# Filter by error type
{app="sports-platform"} | json | error_type="ConnectionError"

# Find logs with specific trace ID
{app="sports-platform"} | trace_id="abc123def456"
```

### Loki API for Log Search

```bash
# Query logs via Loki API (from cluster)
curl -s "http://loki:3100/loki/api/v1/query_range" \
  -G \
  -d "query={app=\"betting-api\"}" \
  -d "limit=100" \
  -d "start=$(date -d '1 hour ago' +%s)000000000" \
  -d "end=$(date +%s)000000000" | jq '.data.result'
```

---

## Mimir - Metrics

### Access Mimir via Grafana Explore

1. Navigate to **Explore**
2. Select **Mimir** from the dropdown
3. Write PromQL queries to explore metrics

### Common PromQL Queries

#### Platform Overview Metrics

```promql
# HTTP request rate (requests per second)
sum(rate(http_requests_total[5m]))

# HTTP error rate
sum(rate(http_requests_total{status=~"5.."}[5m]))

# API latency (p99)
histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, path))
```

#### Kafka Consumer Metrics

```promql
# Consumer lag by topic
kafka_consumer_group_lag{group=~"sports-.*"}

# Messages consumed per second
sum(rate(pipeline_messages_consumed_total[1m])) by (topic)
```

#### Poller Metrics

```promql
# Polls per minute by league
sum(rate(poller_polls_total[1m])) by (league)

# Poll duration (p95)
histogram_quantile(0.95, sum(rate(poller_poll_duration_seconds_bucket[5m])) by (league, le))

# Poll errors by type
sum(rate(poller_errors_total[5m])) by (league, error_type)
```

#### Cache Metrics

```promql
# Cache hit rate
sum(rate(pipeline_cache_hits_total[5m])) by (cache) /
(sum(rate(pipeline_cache_hits_total[5m])) by (cache) +
 sum(rate(pipeline_cache_misses_total[5m])) by (cache))

# Cache size by cache name
ignite_cache_entries{cache=~"sports:v1:.*"}
```

#### Betting Metrics

```promql
# Bets placed per hour
sum(rate(betting_bets_placed_total[1h])) by (market)

# Webhook request rate
sum(rate(betting_webhook_requests_total[5m])) by (endpoint)

# Webhook latency (p99)
histogram_quantile(0.99, sum(rate(betting_webhook_latency_seconds_bucket[5m])) by (endpoint, le))
```

### Key Metrics Reference

| Metric                             | Type      | Labels                  | Description             |
| ---------------------------------- | --------- | ----------------------- | ----------------------- |
| `http_requests_total`              | Counter   | method, path, status    | Total HTTP requests     |
| `http_request_duration_seconds`    | Histogram | path                    | Request duration        |
| `poller_poll_duration_seconds`     | Histogram | league                  | Poll cycle duration     |
| `poller_records_fetched_total`     | Counter   | league, status          | Records fetched         |
| `poller_errors_total`              | Counter   | league, error_type      | Poll errors             |
| `kafka_consumer_group_lag`         | Gauge     | topic, partition, group | Consumer lag            |
| `pipeline_messages_consumed_total` | Counter   | topic                   | Kafka messages consumed |
| `pipeline_cache_hits_total`        | Counter   | cache                   | Cache hits              |
| `pipeline_cache_misses_total`      | Counter   | cache                   | Cache misses            |
| `betting_bets_placed_total`        | Counter   | market, status          | Bets placed             |
| `betting_webhook_requests_total`   | Counter   | endpoint, status        | Webhook requests        |

---

## Tempo - Distributed Tracing

### Access Tempo via Grafana Explore

1. Navigate to **Explore**
2. Select **Tempo** from the dropdown
3. Use TraceQL to search traces

### TraceQL Query Examples

#### Basic Trace Search

```traceql
# Find all traces from betting-api
{service="betting-api"}

# Find traces with errors
{service="sports-platform"} | status=error

# Find traces by name (span name)
{name="handle_webhook"}

# Find traces by duration
{duration>5s}
```

#### Filtering by Service and Attributes

```traceql
# Traces from specific service with errors
{service="betting-api", span.http.method="POST"} | status=error

# Traces with specific HTTP status
{service="betting-api"} | span.http.status_code>=400

# Traces with trace ID pattern
{resource.service.name="betting-api"} | traceID=~"abc.*"
```

#### Common TraceQL Patterns

```traceql
# All traces in last 15 minutes
{resource.service.name=~"betting-api|unified-poller"}

# Traces with database operations
{resource.service.name="kafka-ignite-consumer"} | name=~"WriteCache|ReadCache"

# Traces with Kafka operations
{resource.service.name="kafka-ignite-consumer"} | name=~"Consume|Send"

# Find slow traces (>2s)
{duration>2s} | status=ok

# Find error traces with specific exception
{resource.service.name="betting-api"} | status=error | error.type="ConnectionError"
```

### Viewing Traces from Logs

When logs include `trace_id` field, you can click to view the full trace:

1. Find a log with `trace_id` field
2. Click the trace ID link
3. Grafana opens the trace in Tempo viewer

Example log entry with trace ID:

```json
{
  "timestamp": "2026-01-25T12:00:00Z",
  "level": "error",
  "message": "Failed to process request",
  "trace_id": "4a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d",
  "span_id": "1a2b3c4d5e6f7890"
}
```

### Tempo API for Trace Search

```bash
# Search traces by service
curl -s "http://tempo:3200/api/traces?service=betting-api&limit=10" | jq '.'

# Get specific trace by ID
curl -s "http://tempo:3200/api/traces/4a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d" | jq '.'
```

---

## Grafana Dashboards

### Platform Overview Dashboard

**Location:** Grafana → Dashboards → Platform Overview

Shows:

- HTTP request rate and error rate
- API latency (p50, p95, p99)
- Overall system health

### Poller Metrics Dashboard

**Location:** Grafana → Dashboards → Poller Metrics

Shows:

- Poll duration by league
- Records fetched per poll
- API errors by type
- Rate limit remaining

### Kafka Consumers Dashboard

**Location:** Grafana → Dashboards → Kafka Consumers

Shows:

- Consumer lag by topic and partition
- Messages consumed rate
- Write latency to Ignite

### Logs Dashboard

**Location:** Grafana → Dashboards → Logs

Shows:

- Live log stream with filtering
- Log volume over time
- Error log count

### Traces Dashboard

**Location:** Grafana → Dashboards → Traces

Shows:

- Trace search interface
- Trace duration distribution
- Error trace rate

---

## Alert Configuration

### Recommended Alerts

#### Critical Alerts

```yaml
# Alert: API Down
- alert: API down
  expr: up{job="betting-api"} == 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "Betting API is down"

# Alert: High Error Rate
- alert: High Error Rate
  expr: sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > 0.05
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "API error rate > 5%"
```

#### Warning Alerts

```yaml
# Alert: Consumer Lag High
- alert: Consumer Lag High
  expr: kafka_consumer_group_lag > 10000
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Consumer lag > 10,000 messages"

# Alert: Poll Duration High
- alert: Poll Duration High
  expr: histogram_quantile(0.95, sum(rate(poller_poll_duration_seconds_bucket[5m])) by (league, le)) > 60
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Poll duration p95 > 60s"

# Alert: Cache Hit Rate Low
- alert: Cache Hit Rate Low
  expr: sum(rate(pipeline_cache_hits_total[5m])) by (cache) / (sum(rate(pipeline_cache_hits_total[5m])) + sum(rate(pipeline_cache_misses_total[5m]))) < 0.8
  for: 15m
  labels:
    severity: warning
  annotations:
    summary: "Cache hit rate < 80%"
```

### Configuring Alerts in Grafana

1. Navigate to **Alerting** → **Contact points**
2. Add contact point (email, Slack, PagerDuty)
3. Navigate to **Notification policies**
4. Create matching labels and routing

---

## Troubleshooting Guide

### Grafana Not Loading

```bash
# Check Grafana pod status
kubectl get pods -n monitoring -l app=grafana

# Check Grafana logs
kubectl logs -n monitoring -l app=grafana -f

# Check service endpoints
kubectl get endpoints -n monitoring grafana
```

### No Metrics Showing

```bash
# Check Mimir pod status
kubectl get pods -n monitoring -l app=mimir

# Check Mimir logs
kubectl logs -n monitoring -l app=mimir -f

# Test Mimir API
curl -s "http://mimir:9009/prometheus/api/v1/query?query=up" | jq '.'
```

### No Logs Showing

```bash
# Check Loki pod status
kubectl get pods -n monitoring -l app=loki

# Check Loki logs
kubectl logs -n monitoring -l app=loki -f

# Test Loki API
curl -s "http://loki:3100/loki/api/v1/labels" | jq '.'
```

### No Traces Showing

```bash
# Check Tempo pod status
kubectl get pods -n monitoring -l app=tempo

# Check Tempo logs
kubectl logs -n monitoring -l app=tempo -f

# Test Tempo API
curl -s "http://tempo:3200/api/traces?limit=1" | jq '.'
```

### Telemetry Not Flowing from Applications

```bash
# Check if services have OTEL configured
kubectl exec -it deploy/betting-api -- env | grep OTEL

# Check service metrics endpoint
kubectl exec -it deploy/betting-api -- curl localhost:8000/metrics | head -20

# Check OTEL collector logs
kubectl logs -n monitoring -l app=otel-collector -f
```

---

## Useful Commands

### Port-Forward All Services

```bash
# Grafana
kubectl port-forward -n monitoring svc/grafana 3000:3000

# Mimir (for direct Prometheus queries)
kubectl port-forward -n monitoring svc/mimir 9009:9009

# Loki (for LogQL API access)
kubectl port-forward -n monitoring svc/loki 3100:3100

# Tempo (for TraceQL API access)
kubectl port-forward -n monitoring svc/tempo 3200:3200
```

### Check Component Health

```bash
# Grafana health
curl -s http://localhost:3000/api/health

# Mimir health
curl -s http://localhost:9009/ready

# Loki health
curl -s http://localhost:3100/ready

# Tempo health
curl -s http://localhost:3200/ready
```

### List Dashboards

```bash
# Via API
curl -s -u admin:admin http://localhost:3000/api/search | jq '.[] | {id, title, uri}'
```

---

## Retention Configuration

| Component | Retention | Storage |
| --------- | --------- | ------- |
| Mimir     | 14 days   | 5Gi     |
| Loki      | 7 days    | 10Gi    |
| Tempo     | 7 days    | 5Gi     |

To modify retention, update the respective `k8s-manifests/9x-*.yaml` files:

```yaml
# Example: Loki retention update
spec:
  limits:
    global:
      retention_period: 168h # 7 days
```

---

## Related Documentation

- [AGENTS.md](../AGENTS.md) - Agent instructions for observability tasks
