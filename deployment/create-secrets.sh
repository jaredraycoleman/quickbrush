#!/bin/bash

# Helper script to create Kubernetes secrets from secrets.json
# This replaces the interactive script with a JSON-based approach

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_FILE="$SCRIPT_DIR/secrets.json"

# Check if secrets.json exists
if [ ! -f "$SECRETS_FILE" ]; then
    echo "❌ Error: secrets.json not found at $SECRETS_FILE"
    echo ""
    echo "Please create secrets.json based on secrets.json.example"
    echo ""
    echo "cp $SCRIPT_DIR/secrets.json.example $SECRETS_FILE"
    echo "# Then edit secrets.json with your actual values"
    exit 1
fi

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo "❌ Error: jq is required but not installed."
    echo ""
    echo "Install it with:"
    echo "  Ubuntu/Debian: sudo apt-get install jq"
    echo "  macOS: brew install jq"
    echo "  Arch: sudo pacman -S jq"
    exit 1
fi

echo "🔐 Creating Kubernetes secrets from secrets.json"
echo "================================================"
echo ""

# Read namespace from JSON
NAMESPACE=$(jq -r '.namespace' "$SECRETS_FILE")

echo "Namespace: $NAMESPACE"
echo ""

# Create namespace if it doesn't exist
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# Function to create a secret from JSON
create_secret_from_json() {
    local secret_name=$1

    echo "📝 Creating secret: $secret_name"

    # Extract the secret data from JSON
    local secret_data=$(jq -r ".secrets[\"$secret_name\"]" "$SECRETS_FILE")

    if [ "$secret_data" == "null" ]; then
        echo "   ⚠️  Secret $secret_name not found in JSON, skipping"
        return
    fi

    # Build kubectl arguments
    local args=""
    for key in $(echo "$secret_data" | jq -r 'keys[]'); do
        local value=$(echo "$secret_data" | jq -r ".[\"$key\"]")
        args="$args --from-literal=$key=$value"
    done

    # Delete existing secret if it exists
    kubectl -n "$NAMESPACE" delete secret "$secret_name" --ignore-not-found > /dev/null 2>&1

    # Create the secret
    kubectl -n "$NAMESPACE" create secret generic "$secret_name" $args
    echo "   ✅ Secret $secret_name created"
}

# Create all secrets defined in the JSON
echo "Creating secrets..."
echo ""

for secret_name in $(jq -r '.secrets | keys[]' "$SECRETS_FILE"); do
    create_secret_from_json "$secret_name"
done

# Handle Docker Hub credentials if enabled
echo ""
DOCKERHUB_ENABLED=$(jq -r '.dockerhub.enabled' "$SECRETS_FILE")

if [ "$DOCKERHUB_ENABLED" == "true" ]; then
    echo "📝 Creating Docker Hub credentials"

    DOCKER_USERNAME=$(jq -r '.dockerhub.username' "$SECRETS_FILE")
    DOCKER_PASSWORD=$(jq -r '.dockerhub.password' "$SECRETS_FILE")
    DOCKER_EMAIL=$(jq -r '.dockerhub.email' "$SECRETS_FILE")

    # Delete existing secret if it exists
    kubectl -n "$NAMESPACE" delete secret dockerhub-credentials --ignore-not-found > /dev/null 2>&1

    # Create docker-registry secret
    kubectl -n "$NAMESPACE" create secret docker-registry dockerhub-credentials \
        --docker-server=https://index.docker.io/v1/ \
        --docker-username="$DOCKER_USERNAME" \
        --docker-password="$DOCKER_PASSWORD" \
        --docker-email="$DOCKER_EMAIL"

    echo "   ✅ Secret dockerhub-credentials created"
    echo ""
    echo "   ⚠️  Make sure imagePullSecrets is enabled in deployment/service.yaml"
else
    echo "⏭️  Docker Hub credentials disabled (using public image)"
fi

echo ""
echo "================================================"
echo "✅ All secrets created successfully!"
echo ""
echo "Secret summary:"
kubectl -n "$NAMESPACE" get secrets | grep -v "TYPE"
echo ""
echo "Next steps:"
echo "  1. Deploy application: ./deploy.sh"
echo "  2. Check logs: kubectl -n $NAMESPACE logs -f deployment/quickbrush-service"
echo ""
