#!/bin/bash

# Quick System Issues Diagnosis Script
# Identifies common issues in Sports Platform deployment

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo "========================================"
echo "Sports Platform Issues Diagnosis"
echo "========================================"

# 1. Registry connectivity issue
log_info "=== REGISTRY CONNECTIVITY ==="
if docker ps | grep -q "registry.*:5000"; then
    log_success "Docker registry is running on host"
else
    log_error "Docker registry is not running on host"
fi

# Check if minikube can access the registry
if minikube ip &> /dev/null; then
    MINIKUBE_IP=$(minikube ip)
    log_info "Testing registry access from minikube ($MINIKUBE_IP)..."
    
    # Try to access registry from minikube
    if minikube ssh "curl -s $MINIKUBE_IP:5000/v2/_catalog" &> /dev/null; then
        log_success "Registry accessible from minikube"
    else
        log_error "Registry NOT accessible from minikube - this is causing ImagePullBackOff"
        log_info "Solution: minikube addons enable registry || use external registry"
    fi
fi

# 2. Missing StatefulSets
log_info "=== MISSING COMPONENTS ==="
log_warning "Ignite and TimescaleDB StatefulSets are missing"
log_info "Required manifests:"
log_info "  - 04-ignite.yaml"
log_info "  - 03-timescale.yaml"

# 3. Spark image issues
log_info "=== SPARK JOB ISSUES ==="
kubectl get pods -n default | grep -E "spark-.*driver" | while read -r line; do
    pod_name=$(echo "$line" | awk '{print $1}')
    status=$(echo "$line" | awk '{print $3}')
    log_info "Spark pod $pod_name: $status"
    if [[ "$status" == "ImagePullBackOff" || "$status" == "Pending" ]]; then
        log_warning "Spark jobs need custom images to be built"
    fi
done

# 4. Pod health summary
log_info "=== POD HEALTH SUMMARY ==="
total_pods=$(kubectl get pods -n default --no-headers 2>/dev/null | wc -l)
healthy_pods=$(kubectl get pods -n default --no-headers 2>/dev/null | grep -c "Running\|Completed" || echo "0")
problem_pods=$((total_pods - healthy_pods))

log_info "Total pods: $total_pods"
log_info "Healthy pods: $healthy_pods"
log_info "Problem pods: $problem_pods"

# 5. Kafka status (this seems to work)
log_info "=== KAFKA STATUS ==="
if kubectl get kafka sports-cluster -n default &> /dev/null; then
    kafka_status=$(kubectl get kafka sports-cluster -n default -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
    if [[ "$kafka_status" == "True" ]]; then
        log_success "Kafka cluster is operational"
    else
        log_error "Kafka cluster issues"
    fi
fi

echo "========================================"
echo "RECOMMENDED FIXES"
echo "========================================"
echo "1. Registry Issue:"
echo "   minikube addons enable registry"
echo "   OR"
echo "   docker run -d -p 5000:5000 --restart=always --name registry registry:2"
echo ""
echo "2. Missing StatefulSets:"
echo "   kubectl apply -f k8s-manifests/03-timescale.yaml"
echo "   kubectl apply -f k8s-manifests/04-ignite.yaml"
echo ""
echo "3. Build custom images:"
echo "   cd Dockerfiles && ./build-all.sh"
echo ""
echo "4. For Spark jobs:"
echo "   Update image references to use available images"
echo "========================================"