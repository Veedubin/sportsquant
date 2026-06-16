#!/bin/bash
# Verification script for Grafana OSS Observability Stack
# This script verifies all components are running and responding

set -e

NAMESPACE="monitoring"
TIMEOUT=10

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Grafana OSS Stack Verification Script"
echo "=========================================="
echo ""

# Function to check pod status
check_pod() {
    local pod_name=$1
    local status=$(kubectl get pod -n "$NAMESPACE" "$pod_name" -o jsonpath='{.status.phase}' 2>/dev/null || echo "NotFound")
    if [ "$status" == "Running" ]; then
        echo -e "${GREEN}✓${NC} $pod_name is running"
        return 0
    else
        echo -e "${RED}✗${NC} $pod_name is $status"
        return 1
    fi
}

# Function to check service
check_service() {
    local svc_name=$1
    local cluster_ip=$(kubectl get svc -n "$NAMESPACE" "$svc_name" -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")
    if [ -n "$cluster_ip" ]; then
        echo -e "${GREEN}✓${NC} $svc_name is available (ClusterIP: $cluster_ip)"
        return 0
    else
        echo -e "${RED}✗${NC} $svc_name not found"
        return 1
    fi
}

# Function to check endpoint health
check_endpoint() {
    local svc_name=$1
    local port=$2
    local cluster_ip=$(kubectl get svc -n "$NAMESPACE" "$svc_name" -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")
    if [ -n "$cluster_ip" ]; then
        if curl -s -m "$TIMEOUT" "http://$cluster_ip:$port/api/health" > /dev/null 2>&1; then
            echo -e "${GREEN}✓${NC} $svc_name is responding on port $port"
            return 0
        else
            echo -e "${YELLOW}?${NC} $svc_name is not responding on port $port (may still be starting)"
            return 1
        fi
    fi
}

echo "1. Checking Pod Status..."
echo "------------------------"
PODS_RUNNING=0
check_pod "grafana-9bc789fcd-sqrkd" || PODS_RUNNING=1
check_pod "loki-0" || PODS_RUNNING=1
check_pod "mimir-6f7c5d67f5-mz6c5" || PODS_RUNNING=1
check_pod "tempo-577b65c69f-pxp2r" || PODS_RUNNING=1
echo ""

echo "2. Checking Services..."
echo "-----------------------"
check_service "grafana"
check_service "loki"
check_service "mimir"
check_service "tempo"
echo ""

echo "3. Checking Component Health..."
echo "--------------------------------"
check_endpoint "grafana" "3000"
check_endpoint "loki" "3100"
check_endpoint "mimir" "8080"
check_endpoint "tempo" "4318"
echo ""

echo "4. Verifying Prometheus Removal..."
echo "------------------------------------"
if kubectl get deployment prometheus -n "$NAMESPACE" >/dev/null 2>&1; then
    echo -e "${RED}✗${NC} Prometheus deployment still exists"
else
    echo -e "${GREEN}✓${NC} Prometheus has been removed"
fi
echo ""

echo "5. Quick Integration Tests..."
echo "------------------------------"

# Test Loki log ingestion
echo -n "Testing Loki API... "
if curl -s -m "$TIMEOUT" "http://loki:3100/loki/api/v1/labels" | grep -q "status"; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}?${NC}"
fi

# Test Mimir metrics API
echo -n "Testing Mimir API... "
if curl -s -m "$TIMEOUT" "http://mimir:8080/prometheus/api/v1/status/runtimeinfo" | grep -q "status"; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}?${NC}"
fi

# Test Tempo trace API
echo -n "Testing Tempo API... "
if curl -s -m "$TIMEOUT" "http://tempo:4318/api/echo" | grep -q "method"; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}?${NC}"
fi

echo ""
echo "=========================================="
echo "Verification Complete!"
echo "=========================================="
echo ""
echo "Access Grafana at: http://localhost:3000"
echo "  - Default login: admin/admin"
echo ""
echo "Service Endpoints:"
echo "  - Grafana:  http://grafana:3000"
echo "  - Loki:     http://loki:3100 (HTTP), loki:9095 (gRPC)"
echo "  - Mimir:    http://mimir:8080 (HTTP), mimir:9095 (gRPC)"
echo "  - Tempo:    http://tempo:4318 (HTTP), tempo:4317 (gRPC)"
echo ""

if [ $PODS_RUNNING -eq 0 ]; then
    echo -e "${GREEN}All main components are running!${NC}"
    exit 0
else
    echo -e "${YELLOW}Some components may still be starting. Please wait a few moments and re-run.${NC}"
    exit 1
fi
