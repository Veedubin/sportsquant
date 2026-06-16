#!/bin/bash
# Deploy Sports Platform Observability Stack
# Installs: Prometheus, Loki, Grafana, OTEL Collector

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MANIFESTS_DIR="$PROJECT_DIR/k8s-manifests"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found"
        exit 1
    fi
    
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    log_success "Prerequisites OK"
}

create_namespace() {
    log_info "Creating monitoring namespace..."
    kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
    log_success "Namespace created"
}

deploy_prometheus() {
    log_info "Deploying Prometheus..."
    kubectl apply -f "$MANIFESTS_DIR/90-prometheus.yaml"
    log_success "Prometheus deployed"
}

deploy_loki() {
    log_info "Deploying Loki + Promtail..."
    kubectl apply -f "$MANIFESTS_DIR/91-loki.yaml"
    log_success "Loki deployed"
}

deploy_grafana() {
    log_info "Deploying Grafana..."
    kubectl apply -f "$MANIFESTS_DIR/92-grafana.yaml"
    log_success "Grafana deployed"
}

deploy_otel_collector() {
    log_info "Deploying OTEL Collector..."
    kubectl apply -f "$MANIFESTS_DIR/93-otel-collector.yaml"
    log_success "OTEL Collector deployed"
}

wait_for_pods() {
    log_info "Waiting for pods to be ready..."
    local timeout=120
    local elapsed=0
    
    while [[ $elapsed -lt $timeout ]]; do
        local ready=$(kubectl get pods -n monitoring --no-headers 2>/dev/null | grep -c "Running\|Completed" || echo "0")
        local total=$(kubectl get pods -n monitoring --no-headers 2>/dev/null | wc -l || echo "0")
        
        if [[ $total -gt 0 && $ready -eq $total ]]; then
            log_success "All $total pods are running"
            return 0
        fi
        
        echo -n "."
        sleep 2
        ((elapsed += 2))
    done
    
    log_warning "Timeout waiting for pods"
    kubectl get pods -n monitoring
    return 1
}

print_access_info() {
    echo ""
    echo "=========================================="
    echo -e "${GREEN}Observability Stack Deployed!${NC}"
    echo "=========================================="
    echo ""
    echo "Access URLs:"
    echo ""
    
    # Get node IP (for minikube)
    local node_ip=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || echo "localhost")
    
    # "localhost Get Grafana NodePort
    local grafana_port=$(kubectl get svc grafana -n monitoring -o jsonpath='{.spec.ports[?(@.name=="http")].nodePort}' 2>/dev/null || echo "30000")
    
    # Get Prometheus NodePort (if exposed)
    local prom_port=$(kubectl get svc prometheus -n monitoring -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo "30900")
    
    echo -e "${BLUE}Grafana:${NC}    http://$node_ip:$grafana_port (admin/admin123)"
    echo -e "${BLUE}Prometheus:${NC} http://$node_ip:$prom_port"
    echo ""
    echo "Internal URLs (from within cluster):"
    echo "  - Prometheus:  prometheus.monitoring:9090"
    echo "  - Loki:        loki.monitoring:3100"
    echo "  - Grafana:     grafana.monitoring:3000"
    echo "  - OTEL:        otel-collector.monitoring:4317"
    echo ""
    echo "Commands:"
    echo "  kubectl port-forward -n monitoring svc/grafana 3000:3000"
    echo "  kubectl port-forward -n monitoring svc/prometheus 9090:9090"
    echo "  kubectl logs -n monitoring -l app=promtail -f"
    echo ""
}

main() {
    echo "=========================================="
    echo "Sports Platform Observability Stack"
    echo "=========================================="
    echo ""
    
    check_prerequisites
    create_namespace
    
    deploy_prometheus
    deploy_loki
    deploy_grafana
    deploy_otel_collector
    
    wait_for_pods
    print_access_info
}

main "$@"
