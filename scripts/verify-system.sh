#!/bin/bash

# Sports Platform Comprehensive System Verification Script
# This script performs end-to-end verification of all platform components

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Global variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REPORT_FILE="$PROJECT_DIR/system-verification-report-$(date +%Y%m%d-%H%M%S).txt"
TEMP_DIR="/tmp/sports-platform-verify-$$"

# Create temp directory
mkdir -p "$TEMP_DIR"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$REPORT_FILE"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$REPORT_FILE"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$REPORT_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$REPORT_FILE"
}

# Initialize report
init_report() {
    cat > "$REPORT_FILE" << EOF
========================================
Sports Platform System Verification Report
Generated: $(date)
========================================

EOF
    log_info "Starting comprehensive system verification..."
}

# Check if kubectl is available and cluster is accessible
check_kubernetes_access() {
    log_info "Checking Kubernetes access..."
    
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH"
        return 1
    fi
    
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        return 1
    fi
    
    log_success "Kubernetes cluster is accessible"
    return 0
}

# 1. Kafka Verification
verify_kafka() {
    log_info "=== KAFKA VERIFICATION ==="
    
    # Check if Kafka cluster is running
    log_info "Checking Kafka cluster status..."
    if kubectl get kafka sports-cluster -n default &> /dev/null; then
        local kafka_status=$(kubectl get kafka sports-cluster -n default -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
        if [[ "$kafka_status" == "True" ]]; then
            log_success "Kafka cluster is ready"
        else
            log_error "Kafka cluster is not ready"
            return 1
        fi
    else
        log_error "Kafka cluster not found"
        return 1
    fi
    
    # List all topics
    log_info "Listing Kafka topics..."
    local topics=$(kubectl get kafkatopics -n default -o name 2>/dev/null || echo "")
    if [[ -n "$topics" ]]; then
        log_success "Found Kafka topics:"
        echo "$topics" | sed 's/.*\///' | while read -r topic; do
            log_info "  - $topic"
        done
    else
        log_warning "No Kafka topics found"
    fi
    
    # Check Kafka brokers
    log_info "Checking Kafka brokers..."
    local bootstrap_server=$(kubectl get kafka sports-cluster -n default -o jsonpath='{.status.listeners[?(@.name=="plain")].bootstrapServers}' 2>/dev/null || echo "")
    if [[ -n "$bootstrap_server" ]]; then
        log_success "Kafka bootstrap server: $bootstrap_server"
    else
        log_error "Could not get Kafka bootstrap server"
        return 1
    fi
    
    # Test message production/consumption
    log_info "Testing Kafka message production/consumption..."
    local test_pod="kafka-test-$$"
    
    # Create test pod
    cat > "$TEMP_DIR/kafka-test-pod.yaml" << EOF
apiVersion: v1
kind: Pod
metadata:
  name: $test_pod
  namespace: default
spec:
  containers:
  - name: kafka-client
    image: confluentinc/cp-kafka:latest
    command: ["sleep", "3600"]
EOF
    
    kubectl apply -f "$TEMP_DIR/kafka-test-pod.yaml" &> /dev/null
    
    # Wait for pod to be ready
    local retry=0
    while [[ $retry -lt 30 ]]; do
        if kubectl get pod $test_pod -n default -o jsonpath='{.status.phase}' | grep -q "Running"; then
            break
        fi
        sleep 2
        ((retry++))
    done
    
    if [[ $retry -eq 30 ]]; then
        log_error "Test pod failed to start"
        kubectl delete pod $test_pod -n default --ignore-not-found &> /dev/null
        return 1
    fi
    
    # Test producing a message
    log_info "Testing message production..."
    if kubectl exec $test_pod -n default -- kafka-topics --bootstrap-server $bootstrap_server --topic test-verification --create --if-not-exists --partitions 1 --replication-factor 1 &> /dev/null; then
        if echo "test-message-$(date +%s)" | kubectl exec -i $test_pod -n default -- kafka-console-producer --bootstrap-server $bootstrap_server --topic test-verification &> /dev/null; then
            log_success "Message production test passed"
        else
            log_error "Message production test failed"
            kubectl delete pod $test_pod -n default --ignore-not-found &> /dev/null
            return 1
        fi
    else
        log_error "Could not create test topic"
        kubectl delete pod $test_pod -n default --ignore-not-found &> /dev/null
        return 1
    fi
    
    # Clean up test pod
    kubectl delete pod $test_pod -n default --ignore-not-found &> /dev/null
    
    return 0
}

# 2. Data Flow Verification
verify_data_flow() {
    log_info "=== DATA FLOW VERIFICATION ==="
    
    # Check pollers are producing to Kafka
    log_info "Checking data pollers..."
    local pollers=("odds-poller" "stats-poller")
    
    for poller in "${pollers[@]}"; do
        if kubectl get deployment $poller -n default &> /dev/null; then
            local replicas=$(kubectl get deployment $poller -n default -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
            if [[ "$replicas" -gt 0 ]]; then
                log_success "$poller is running ($replicas replicas)"
            else
                log_warning "$poller is not ready"
            fi
        else
            log_warning "$poller deployment not found"
        fi
    done
    
    # Check Ignite cache
    log_info "Checking Ignite cache..."
    if kubectl get statefulset ignite-statefulset -n default &> /dev/null; then
        local ignite_replicas=$(kubectl get statefulset ignite-statefulset -n default -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        if [[ "$ignite_replicas" -gt 0 ]]; then
            log_success "Ignite cache is running ($ignite_replicas replicas)"
        else
            log_warning "Ignite cache is not ready"
        fi
    else
        log_warning "Ignite StatefulSet not found"
    fi
    
    # Check TimescaleDB
    log_info "Checking TimescaleDB..."
    if kubectl get statefulset timescaledb -n default &> /dev/null; then
        local tsdb_replicas=$(kubectl get statefulset timescaledb -n default -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        if [[ "$tsdb_replicas" -gt 0 ]]; then
            log_success "TimescaleDB is running ($tsdb_replicas replicas)"
        else
            log_warning "TimescaleDB is not ready"
        fi
    else
        log_warning "TimescaleDB StatefulSet not found"
    fi
    
    # Check Spark jobs
    log_info "Checking Spark jobs..."
    local spark_jobs=$(kubectl get spark -n default -o name 2>/dev/null || echo "")
    if [[ -n "$spark_jobs" ]]; then
        log_success "Found Spark jobs:"
        echo "$spark_jobs" | while read -r job; do
            local job_name=$(echo "$job" | sed 's/.*\///')
            local job_status=$(kubectl get $job -n default -o jsonpath='{.status.applicationState.state}' 2>/dev/null || echo "UNKNOWN")
            log_info "  - $job_name: $job_status"
        done
    else
        log_warning "No Spark jobs found"
    fi
    
    return 0
}

# 3. ML Pipeline Verification
verify_ml_pipeline() {
    log_info "=== ML PIPELINE VERIFICATION ==="
    
    # Check MLflow
    log_info "Checking MLflow accessibility..."
    if kubectl get service mlflow -n default &> /dev/null; then
        local mlflow_port=$(kubectl get service mlflow -n default -o jsonpath='{.spec.ports[0].port}' 2>/dev/null || echo "5000")
        log_success "MLflow service found on port $mlflow_port"
        
        # Test MLflow endpoint (basic connectivity test)
        local mlflow_pod="mlflow-test-$$"
        cat > "$TEMP_DIR/mlflow-test.yaml" << EOF
apiVersion: v1
kind: Pod
metadata:
  name: $mlflow_pod
  namespace: default
spec:
  containers:
  - name: curl
    image: curlimages/curl:latest
    command: ["sleep", "3600"]
EOF
        
        kubectl apply -f "$TEMP_DIR/mlflow-test.yaml" &> /dev/null
        
        # Wait for pod
        local retry=0
        while [[ $retry -lt 15 ]]; do
            if kubectl get pod $mlflow_pod -n default -o jsonpath='{.status.phase}' | grep -q "Running"; then
                break
            fi
            sleep 2
            ((retry++))
        done
        
        if [[ $retry -lt 15 ]]; then
            if kubectl exec $mlflow_pod -n default -- curl -s -o /dev/null -w "%{http_code}" http://mlflow.$mlflow_port/health | grep -q "200"; then
                log_success "MLflow health check passed"
            else
                log_warning "MLflow health check failed"
            fi
        fi
        
        kubectl delete pod $mlflow_pod -n default --ignore-not-found &> /dev/null
    else
        log_warning "MLflow service not found"
    fi
    
    # Check Spark ML jobs with GPU
    log_info "Checking Spark ML jobs with GPU..."
    local gpu_jobs=$(kubectl get spark -n default -l gpu=true -o name 2>/dev/null || echo "")
    if [[ -n "$gpu_jobs" ]]; then
        log_success "Found GPU-enabled Spark jobs:"
        echo "$gpu_jobs" | while read -r job; do
            local job_name=$(echo "$job" | sed 's/.*\///')
            local job_status=$(kubectl get $job -n default -o jsonpath='{.status.applicationState.state}' 2>/dev/null || echo "UNKNOWN")
            log_info "  - $job_name: $job_status"
        done
    else
        log_warning "No GPU-enabled Spark jobs found"
    fi
    
    # Check model training progress
    log_info "Checking model training progress..."
    local training_jobs=$(kubectl get spark -n default -l purpose=training -o name 2>/dev/null || echo "")
    if [[ -n "$training_jobs" ]]; then
        log_success "Found training jobs:"
        echo "$training_jobs" | while read -r job; do
            local job_name=$(echo "$job" | sed 's/.*\///')
            local job_status=$(kubectl get $job -n default -o jsonpath='{.status.applicationState.state}' 2>/dev/null || echo "UNKNOWN")
            log_info "  - $job_name: $job_status"
        done
    else
        log_warning "No training jobs found"
    fi
    
    # Check predictions topic
    log_info "Checking predictions topic..."
    if kubectl get kafkatopic sports.smoke.test.predictions -n default &> /dev/null; then
        log_success "Predictions topic exists"
    else
        log_warning "Predictions topic not found"
    fi
    
    return 0
}

# 4. System Health Check
verify_system_health() {
    log_info "=== SYSTEM HEALTH CHECK ==="
    
    # Check all pod statuses across namespaces
    log_info "Checking pod statuses across all namespaces..."
    local namespaces=$(kubectl get namespaces -o jsonpath='{.items[*].metadata.name}')
    
    for namespace in $namespaces; do
        local total_pods=$(kubectl get pods -n $namespace --no-headers 2>/dev/null | wc -l)
        if [[ $total_pods -gt 0 ]]; then
            local running_pods=$(kubectl get pods -n $namespace --no-headers 2>/dev/null | grep -c "Running\|Completed" || echo "0")
            log_info "Namespace $namespace: $running_pods/$total_pods pods running"
            
            # Show problematic pods
            local problem_pods=$(kubectl get pods -n $namespace --no-headers 2>/dev/null | grep -v "Running\|Completed" || echo "")
            if [[ -n "$problem_pods" ]]; then
                log_warning "Problematic pods in $namespace:"
                echo "$problem_pods" | while read -r pod_line; do
                    local pod_name=$(echo "$pod_line" | awk '{print $1}')
                    local pod_status=$(echo "$pod_line" | awk '{print $3}')
                    log_warning "  - $pod_name: $pod_status"
                done
            fi
        fi
    done
    
    # Verify resource utilization
    log_info "Checking resource utilization..."
    if command -v kubectl top &> /dev/null; then
        log_info "Node resource utilization:"
        kubectl top nodes 2>/dev/null | while read -r line; do
            log_info "  $line"
        done
        
        log_info "Pod resource utilization (default namespace):"
        kubectl top pods -n default 2>/dev/null | head -10 | while read -r line; do
            log_info "  $line"
        done
    else
        log_warning "kubectl top plugin not available"
    fi
    
    # Test API endpoints and services
    log_info "Testing service endpoints..."
    local services=$(kubectl get services -n default -o name 2>/dev/null || echo "")
    if [[ -n "$services" ]]; then
        log_success "Found services:"
        echo "$services" | while read -r service; do
            local service_name=$(echo "$service" | sed 's/.*\///')
            local service_type=$(kubectl get service $service_name -n default -o jsonpath='{.spec.type}' 2>/dev/null || echo "Unknown")
            local service_ports=$(kubectl get service $service_name -n default -o jsonpath='{.spec.ports[*].port}' 2>/dev/null || echo "Unknown")
            log_info "  - $service_name ($service_type): ports $service_ports"
        done
    else
        log_warning "No services found"
    fi
    
    return 0
}

# Generate comprehensive status report
generate_status_report() {
    log_info "=== COMPREHENSIVE STATUS REPORT ==="
    
    # Summary
    local total_issues=0
    local total_warnings=0
    local total_successes=0
    
    # Count from report file
    if [[ -f "$REPORT_FILE" ]]; then
        total_issues=$(grep -c "\[ERROR\]" "$REPORT_FILE" || echo "0")
        total_warnings=$(grep -c "\[WARNING\]" "$REPORT_FILE" || echo "0")
        total_successes=$(grep -c "\[SUCCESS\]" "$REPORT_FILE" || echo "0")
    fi
    
    cat >> "$REPORT_FILE" << EOF

========================================
SUMMARY
========================================
Total Successes: $total_successes
Total Warnings: $total_warnings
Total Errors: $total_issues

EOF
    
    if [[ $total_issues -eq 0 ]]; then
        log_success "System verification completed with no critical errors"
    else
        log_error "System verification completed with $total_issues critical errors"
    fi
    
    if [[ $total_warnings -gt 0 ]]; then
        log_warning "Found $total_warnings warnings that should be reviewed"
    fi
    
    # Cluster info
    cat >> "$REPORT_FILE" << EOF

========================================
CLUSTER INFORMATION
========================================
Kubernetes Version: $(kubectl version --client --short 2>/dev/null || echo "Unknown")
Current Context: $(kubectl config current-context 2>/dev/null || echo "Unknown")
Current Namespace: $(kubectl config view --minify -o jsonpath='{.contexts[?(@.name=="'$(kubectl config current-context)'")].context.namespace}' 2>/dev/null || echo "default")

EOF
    
    log_info "Detailed report saved to: $REPORT_FILE"
}

# Cleanup function
cleanup() {
    log_info "Cleaning up temporary files..."
    rm -rf "$TEMP_DIR"
    
    # Clean up any test pods that might be left behind
    kubectl get pods -n default --no-headers 2>/dev/null | grep -E "kafka-test|mlflow-test" | awk '{print $1}' | while read -r pod; do
        kubectl delete pod $pod -n default --ignore-not-found &> /dev/null
    done
}

# Main execution
main() {
    # Set up cleanup trap
    trap cleanup EXIT
    
    # Initialize report
    init_report
    
    # Run verification checks
    local exit_code=0
    
    if ! check_kubernetes_access; then
        log_error "Cannot proceed with verification - Kubernetes access failed"
        exit 1
    fi
    
    if ! verify_kafka; then
        ((exit_code++))
    fi
    
    if ! verify_data_flow; then
        ((exit_code++))
    fi
    
    if ! verify_ml_pipeline; then
        ((exit_code++))
    fi
    
    if ! verify_system_health; then
        ((exit_code++))
    fi
    
    # Generate final report
    generate_status_report
    
    if [[ $exit_code -eq 0 ]]; then
        log_success "All verification checks completed successfully"
        exit 0
    else
        log_error "Some verification checks failed - see report for details"
        exit 1
    fi
}

# Run main function
main "$@"