#!/usr/bin/env bash
set -euo pipefail

# ── SportsQuant K8s Deployment ──────────────────────────────────────────────
# Applies manifests in dependency order: storage → data plane → app → observability
# Usage: ./scripts/deploy.sh [--dry-run]

DRY_RUN=""
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN="--dry-run=client"
    echo "=== DRY RUN MODE ==="
fi

KUBECTL="kubectl apply $DRY_RUN"

echo "=== SportsQuant K8s Deployment ==="
echo ""

# ── Phase 1: Storage & Stateful Infrastructure ──────────────────────────────
echo "── Phase 1: Storage & Stateful Infrastructure ──"
$KUBECTL -f k8s/01-storage-layer.yaml
$KUBECTL -f k8s/02-kafka-cluster.yaml
$KUBECTL -f k8s/02a-kafka-nodepool.yaml
$KUBECTL -f k8s/03-timescale.yaml

echo "── Phase 1b: Ignite Cache ──"
$KUBECTL -f k8s/04-ignite.yaml
$KUBECTL -f k8s/04-ignite3.yaml
$KUBECTL -f k8s/04-ignite3-pvc.yaml
$KUBECTL -f k8s/04a-ignite3-configmap.yaml
$KUBECTL -f k8s/04b-ignite3-jdbc-config.yaml

# ── Phase 2: Kafka Connectors & Schema Registry ────────────────────────────
echo "── Phase 2: Kafka Connect & Schema Registry ──"
$KUBECTL -f k8s/06-kafka-connect.yaml
$KUBECTL -f k8s/06b-kafka-connect-standalone.yaml
$KUBECTL -f k8s/06c-schema-registry.yaml
$KUBECTL -f k8s/06c-karapace-schema-registry.yaml
$KUBECTL -f k8s/06c-kafka-connect-json.yaml
$KUBECTL -f k8s/08-debezium-server.yaml

# ── Phase 3: Kafka Topics ──────────────────────────────────────────────────
echo "── Phase 3: Kafka Topics ──"
$KUBECTL -f k8s/09-kafka-topic-users.yaml
$KUBECTL -f k8s/10-kafka-topic-line-movements.yaml
$KUBECTL -f k8s/11-schedule-kafka-topic.yaml
$KUBECTL -f k8s/11-wnba-games-topic.yaml
$KUBECTL -f k8s/11a-nba-stats-topics.yaml
$KUBECTL -f k8s/11-kafka-connector-jdbc-sink.yaml

# ── Phase 4: Timescale Schemas ──────────────────────────────────────────────
echo "── Phase 4: TimescaleDB Schemas & Connectors ──"
$KUBECTL -f k8s/13-timescale-schemas-configmap.yaml
$KUBECTL -f k8s/15-timescale-schema.yaml
$KUBECTL -f k8s/14-ignite-kafka-connector.yaml

# ── Phase 5: Ingestion Pipelines (Pollers & Calendar Generators) ────────────
echo "── Phase 5: Ingestion Pipelines ──"
$KUBECTL -f k8s/12-nba-calendar-generator.yaml
$KUBECTL -f k8s/14-nfl-calendar-generator.yaml
$KUBECTL -f k8s/14a-nfl-odds-poller.yaml
$KUBECTL -f k8s/14b-nhl-calendar-generator.yaml
$KUBECTL -f k8s/14c-nhl-odds-poller.yaml
$KUBECTL -f k8s/14d-mlb-calendar-generator.yaml
$KUBECTL -f k8s/14e-mlb-odds-poller.yaml
$KUBECTL -f k8s/14f-f1-calendar-generator.yaml
$KUBECTL -f k8s/14g-f1-odds-poller.yaml
$KUBECTL -f k8s/15-nba-stats-fetcher.yaml
$KUBECTL -f k8s/15a-nba-backfill-jobs.yaml
$KUBECTL -f k8s/16-odds-poller-deployment.yaml
$KUBECTL -f k8s/17-stats-poller-deployment.yaml
$KUBECTL -f k8s/18-schedule-poller-deployment.yaml

# ── Phase 6: Sport-Specific Topics & Ingest Configs ─────────────────────────
echo "── Phase 6: Sport Topics & Ingest Configs ──"
for sport in nba nfl nhl mlb f1; do
    if [[ -f "k8s/20-${sport}-topics.yaml" ]]; then
        $KUBECTL -f "k8s/20-${sport}-topics.yaml"
    fi
done
$KUBECTL -f k8s/20-odds-topics.yaml
$KUBECTL -f k8s/20-scheduler-topics.yaml
$KUBECTL -f k8s/20-wnba-schedule-updates.yaml

for num in 30 31 32 33 34 35 36; do
    for f in k8s/${num}-*.yaml; do
        [[ -f "$f" ]] && $KUBECTL -f "$f"
    done
done

# ── Phase 7: Betting API & Feature Engineering ─────────────────────────────
echo "── Phase 7: Betting API & Features ──"
$KUBECTL -f k8s/40-betting-api.yaml
$KUBECTL -f k8s/41-betting-topics.yaml
$KUBECTL -f k8s/42-feature-engineering-deployment.yaml
$KUBECTL -f k8s/42-feature-engineering-job.yaml
$KUBECTL -f k8s/43-backtest-deployment.yaml
$KUBECTL -f k8s/43-backtest-job.yaml

# ── Phase 8: ML / Spark / MLflow ────────────────────────────────────────────
echo "── Phase 8: ML / Spark / MLflow ──"
$KUBECTL -f k8s/22-spark-model-training.yaml
$KUBECTL -f k8s/23-spark-model-evaluator.yaml
$KUBECTL -f k8s/24-secrets.yaml
$KUBECTL -f k8s/24-spark-rbac.yaml
$KUBECTL -f k8s/25-mlflow-deployment.yaml
$KUBECTL -f k8s/26-mlflow-service.yaml
$KUBECTL -f k8s/27-mlflow-pvc.yaml
$KUBECTL -f k8s/28-kafka-config.yaml
$KUBECTL -f k8s/28-spark-xgboost-training.yaml
$KUBECTL -f k8s/29-spark-batch-inference.yaml
$KUBECTL -f k8s/spark-model-training-configmap.yaml
$KUBECTL -f k8s/spark-model-evaluator-configmap.yaml
$KUBECTL -f k8s/spark-ml-training-configmap.yaml

# ── Phase 9: Unified Pollers & Kafka Consumers ──────────────────────────────
echo "── Phase 9: Unified Pollers & Consumers ──"
$KUBECTL -f k8s/51-kafka-ui-ingress.yaml
$KUBECTL -f k8s/60-nba-odds-backfill.yaml
$KUBECTL -f k8s/70-scheduler-config-server.yaml
$KUBECTL -f k8s/71-unified-poller.yaml
$KUBECTL -f k8s/71a-unified-poller-nfl.yaml
$KUBECTL -f k8s/71b-unified-poller-nhl.yaml
$KUBECTL -f k8s/71c-unified-poller-mlb.yaml
$KUBECTL -f k8s/71d-unified-poller-f1.yaml
$KUBECTL -f k8s/71-wnba-poller.yaml
$KUBECTL -f k8s/72-kafka-ignite-consumer.yaml
$KUBECTL -f k8s/72-spark-topics.yaml
$KUBECTL -f k8s/73-spark-data-producer.yaml
$KUBECTL -f k8s/74-spark-backfill-job.yaml
$KUBECTL -f k8s/74-spark-ignite3-configmap.yaml
$KUBECTL -f k8s/75-spark-ignite3-job.yaml
$KUBECTL -f k8s/80-kafka-timescale-backfill.yaml

# ── Phase 10: NBA XGBoost Models ───────────────────────────────────────────
echo "── Phase 10: NBA XGBoost Models ──"
if [[ -d "k8s/nba-xgb" ]]; then
    for f in k8s/nba-xgb/base/*.yaml; do
        [[ -f "$f" ]] && $KUBECTL -f "$f"
    done
    for f in k8s/nba-xgb/cronjobs/*.yaml; do
        [[ -f "$f" ]] && $KUBECTL -f "$f"
    done
    for f in k8s/nba-xgb/jobs/*.yaml; do
        [[ -f "$f" ]] && $KUBECTL -f "$f"
    done
fi

# ── Phase 11: Observability Stack ──────────────────────────────────────────
echo "── Phase 11: Observability ──"
$KUBECTL -f k8s/90-namespace.yaml
$KUBECTL -f k8s/90-loki.yaml
$KUBECTL -f k8s/91-mimir.yaml
$KUBECTL -f k8s/92-tempo.yaml
$KUBECTL -f k8s/93-grafana.yaml
$KUBECTL -f k8s/93-otel-collector.yaml
$KUBECTL -f k8s/95-dashboards.yaml
$KUBECTL -f k8s/96-ingress-observability.yaml

# ── Phase 12: HPA / PDB Autoscaling ────────────────────────────────────────
echo "── Phase 12: Autoscaling & Pod Disruption Budgets ──"
for f in k8s/90-hpa-*.yaml k8s/91-hpa-*.yaml k8s/92-hpa-*.yaml; do
    [[ -f "$f" ]] && $KUBECTL -f "$f"
done
for f in k8s/93-pdb-*.yaml k8s/94-pdb-*.yaml; do
    [[ -f "$f" ]] && $KUBECTL -f "$f"
done

# ── Phase 13: Optional GPU / Spark Operator ────────────────────────────────
echo "── Phase 13: Optional GPU / Spark Operator ──"
$KUBECTL -f k8s/99-nvidia-device-plugin.yaml 2>/dev/null || echo "  (skipped nvidia-device-plugin — not applicable)"
$KUBECTL -f k8s/99-spark-operator.yaml 2>/dev/null || echo "  (skipped spark-operator — not applicable)"

echo ""
echo "=== Deployment complete ==="
echo ""
kubectl get pods -A -o wide