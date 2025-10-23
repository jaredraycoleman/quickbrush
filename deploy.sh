#!/bin/bash

set -e  # Exit on error

# cd to the directory of the script
cd "$(dirname "$0")"

echo "🚀 Starting Quickbrush deployment..."

# Zip foundry-module to static/foundry-module/quickbrush.zip
echo "📦 Zipping Foundry module..."
zip -r static/foundry-module/quickbrush.zip foundry-module
cp foundry-module/module.json static/foundry-module/module.json

# Build and push the Docker image
echo "📦 Building Docker image..."
docker compose build --push

# Update deployment ID to force pod restart
echo "🔄 Updating deployment ID..."
sed -i "s/DEPLOYID-.*$/DEPLOYID-$(openssl rand -hex 16)/" deployment/service.yaml

# Regenerate app secret key
echo "🔑 Regenerating app secret key..."
new_secret=$(openssl rand -hex 32)
kubectl -n quickbrush delete secret app-secret-key --ignore-not-found
kubectl -n quickbrush create secret generic app-secret-key --from-literal=APP_SECRET_KEY="$new_secret"

# Check if secrets exist, if not prompt user
echo "🔍 Checking for required secrets..."

check_secret() {
    local secret_name=$1
    if ! kubectl -n quickbrush get secret "$secret_name" &> /dev/null; then
        echo "⚠️  Warning: Secret '$secret_name' does not exist!"
        echo "   Please create it before deployment using:"
        echo "   kubectl -n quickbrush create secret generic $secret_name --from-literal=KEY=value"
        return 1
    fi
    return 0
}

# Check all required secrets
MISSING_SECRETS=0
check_secret "auth0-credentials" || MISSING_SECRETS=1
check_secret "mongodb-uri" || MISSING_SECRETS=1
check_secret "stripe-credentials" || MISSING_SECRETS=1
check_secret "stripe-prices" || MISSING_SECRETS=1
check_secret "openai-credentials" || MISSING_SECRETS=1

if [ $MISSING_SECRETS -eq 1 ]; then
    echo ""
    echo "❌ Missing required secrets. Please create them first."
    echo "   See deployment/create-secrets.sh for examples."
    exit 1
fi

# Apply the deployment
echo "☸️  Applying Kubernetes deployment..."
kubectl apply -f deployment/service.yaml

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📊 Check status with:"
echo "   kubectl -n quickbrush get pods"
echo "   kubectl -n quickbrush logs -f deployment/quickbrush-service"
echo ""
echo "🌐 Application will be available at: https://quickbrush.ai"
