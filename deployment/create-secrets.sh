#!/bin/bash

# Helper script to create Kubernetes secrets for Quickbrush
# Run this BEFORE deploying for the first time

set -e

NAMESPACE="quickbrush"

echo "🔐 Creating Kubernetes secrets for Quickbrush"
echo "================================================"
echo ""
echo "⚠️  This script will prompt you for sensitive values."
echo "   Make sure you have all credentials ready."
echo ""

# Create namespace if it doesn't exist
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# Function to create secret from user input
create_secret_interactive() {
    local secret_name=$1
    shift
    local keys=("$@")

    echo ""
    echo "📝 Creating secret: $secret_name"

    local args=""
    for key in "${keys[@]}"; do
        read -sp "   Enter $key: " value
        echo ""
        args="$args --from-literal=$key=$value"
    done

    # Delete existing secret if it exists
    kubectl -n $NAMESPACE delete secret $secret_name --ignore-not-found

    # Create the secret
    kubectl -n $NAMESPACE create secret generic $secret_name $args
    echo "   ✅ Secret $secret_name created"
}

# Create secrets
echo "1️⃣ Auth0 Credentials"
create_secret_interactive "auth0-credentials" \
    "AUTH0_CLIENT_ID" \
    "AUTH0_CLIENT_SECRET"

echo ""
echo "2️⃣ MongoDB URI"
create_secret_interactive "mongodb-uri" \
    "MONGODB_URI"

echo ""
echo "3️⃣ Stripe Credentials"
create_secret_interactive "stripe-credentials" \
    "STRIPE_SECRET_KEY" \
    "STRIPE_WEBHOOK_SECRET"

echo ""
echo "4️⃣ Stripe Price IDs - Subscriptions"
create_secret_interactive "stripe-prices" \
    "STRIPE_PRICE_BASIC" \
    "STRIPE_PRICE_PRO" \
    "STRIPE_PRICE_PREMIUM" \
    "STRIPE_PRICE_ULTIMATE" \
    "STRIPE_PRICE_PACK_250" \
    "STRIPE_PRICE_PACK_500" \
    "STRIPE_PRICE_PACK_1000" \
    "STRIPE_PRICE_PACK_2500"

echo ""
echo "5️⃣ OpenAI API Key"
create_secret_interactive "openai-credentials" \
    "OPENAI_API_KEY"

echo ""
echo "6️⃣ Docker Hub Credentials (for private image)"
echo "   (Skip this if your image is public)"
read -p "   Is your Docker image private? (y/n): " is_private

if [[ $is_private == "y" || $is_private == "Y" ]]; then
    read -p "   Enter Docker Hub username: " docker_username
    read -sp "   Enter Docker Hub password/token: " docker_password
    echo ""
    read -p "   Enter Docker Hub email: " docker_email

    # Delete existing secret if it exists
    kubectl -n $NAMESPACE delete secret dockerhub-credentials --ignore-not-found

    # Create docker-registry secret
    kubectl -n $NAMESPACE create secret docker-registry dockerhub-credentials \
        --docker-server=https://index.docker.io/v1/ \
        --docker-username="$docker_username" \
        --docker-password="$docker_password" \
        --docker-email="$docker_email"

    echo "   ✅ Secret dockerhub-credentials created"
    echo ""
    echo "   ⚠️  IMPORTANT: Update deployment/service.yaml to use this secret!"
    echo "      Add under spec.template.spec:"
    echo "        imagePullSecrets:"
    echo "          - name: dockerhub-credentials"
else
    echo "   ⏭️  Skipping Docker Hub credentials (public image)"
fi

echo ""
echo "================================================"
echo "✅ All secrets created successfully!"
echo ""
echo "Next steps:"
echo "  1. Review secrets: kubectl -n $NAMESPACE get secrets"
echo "  2. If image is private, update deployment/service.yaml (see above)"
echo "  3. Deploy application: ./deploy.sh"
echo ""
