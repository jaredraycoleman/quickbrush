# Quickbrush Deployment Guide

This directory contains Kubernetes deployment configuration for Quickbrush.

## Prerequisites

- Docker installed and configured
- kubectl configured with cluster access
- Kubernetes cluster with Traefik ingress controller
- cert-manager installed for SSL certificates
- Docker Hub account (or update image registry in files)
- **For private images:** Docker Hub credentials (see `DOCKER_PRIVATE_IMAGE.md`)

## Initial Setup

### 1. Configure Secrets

All sensitive configuration is stored in Kubernetes secrets. Run the helper script:

```bash
./deployment/create-secrets.sh
```

This will prompt you for:
- Auth0 credentials (client ID, client secret)
- MongoDB URI
- Stripe credentials (secret key, webhook secret)
- Stripe price IDs (all 8 price IDs)
- OpenAI API key

**Alternatively**, create secrets manually:

```bash
# Auth0
kubectl -n quickbrush create secret generic auth0-credentials \
  --from-literal=AUTH0_CLIENT_ID=your_client_id \
  --from-literal=AUTH0_CLIENT_SECRET=your_client_secret

# MongoDB
kubectl -n quickbrush create secret generic mongodb-uri \
  --from-literal=MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/quickbrush

# Stripe
kubectl -n quickbrush create secret generic stripe-credentials \
  --from-literal=STRIPE_SECRET_KEY=sk_live_...

# Stripe Prices
kubectl -n quickbrush create secret generic stripe-prices \
  --from-literal=STRIPE_PRICE_BASIC=price_... \
  --from-literal=STRIPE_PRICE_PRO=price_... \
  --from-literal=STRIPE_PRICE_PREMIUM=price_... \
  --from-literal=STRIPE_PRICE_ULTIMATE=price_... \
  --from-literal=STRIPE_PRICE_PACK_250=price_... \
  --from-literal=STRIPE_PRICE_PACK_500=price_... \
  --from-literal=STRIPE_PRICE_PACK_1000=price_... \
  --from-literal=STRIPE_PRICE_PACK_2500=price_...

# OpenAI
kubectl -n quickbrush create secret generic openai-credentials \
  --from-literal=OPENAI_API_KEY=sk-...
```

### 2. Update Configuration

Edit `deployment/service.yaml` if needed:

- Update `AUTH0_DOMAIN` (line 39)
- Update `AUTH0_AUDIENCE` (line 41)
- Update domain to your actual domain (currently: `quickbrush.online`)

### 3. Build and Push Docker Image

```bash
docker compose build --push
```

This builds and pushes to `jaredraycoleman/quickbrush:latest`.

**To use a different registry**, update the image name in:
- `docker-compose.yaml`
- `deployment/service.yaml`

## Deployment

### Deploy to Kubernetes

```bash
./deploy.sh
```

This script will:
1. Build and push the Docker image
2. Regenerate deployment ID (forces pod restart)
3. Regenerate app secret key
4. Check for required secrets
5. Apply Kubernetes configuration

### Manual Deployment

```bash
# Build and push
docker compose build --push

# Apply configuration
kubectl apply -f deployment/service.yaml
```

## Monitoring

### Check Deployment Status

```bash
# Check pods
kubectl -n quickbrush get pods

# Check deployment
kubectl -n quickbrush get deployment

# Check service
kubectl -n quickbrush get service

# Check ingress
kubectl -n quickbrush get ingress
```

### View Logs

```bash
# Follow logs
kubectl -n quickbrush logs -f deployment/quickbrush-service

# Logs from specific pod
kubectl -n quickbrush logs -f <pod-name>

# Logs from all pods
kubectl -n quickbrush logs -f -l app.kubernetes.io/name=quickbrush-service
```

### Debug Pod Issues

```bash
# Describe pod
kubectl -n quickbrush describe pod <pod-name>

# Get events
kubectl -n quickbrush get events --sort-by='.lastTimestamp'

# Execute shell in pod
kubectl -n quickbrush exec -it <pod-name> -- /bin/bash
```

## Scaling

### Manual Scaling

```bash
# Scale to 3 replicas
kubectl -n quickbrush scale deployment quickbrush-service --replicas=3
```

### Update Replicas Permanently

Edit `deployment/service.yaml` line 11:
```yaml
spec:
  replicas: 3  # Change this number
```

Then redeploy:
```bash
kubectl apply -f deployment/service.yaml
```

## Updating

### Update Application Code

1. Make changes to code
2. Run deployment script:
   ```bash
   ./deploy.sh
   ```

### Update Environment Variables

1. Edit `deployment/service.yaml`
2. Apply changes:
   ```bash
   kubectl apply -f deployment/service.yaml
   ```

### Update Secrets

```bash
# Update a secret
kubectl -n quickbrush delete secret stripe-credentials
kubectl -n quickbrush create secret generic stripe-credentials \
  --from-literal=STRIPE_SECRET_KEY=new_value

# Restart pods to pick up new secret
kubectl -n quickbrush rollout restart deployment quickbrush-service
```

## SSL Certificate

The deployment uses cert-manager with Let's Encrypt for automatic SSL.

### Check Certificate Status

```bash
kubectl -n quickbrush describe certificate quickbrush-service-cert
```

### Manual Certificate Request

If automatic SSL fails:

```bash
kubectl -n quickbrush delete certificate quickbrush-service-cert
kubectl apply -f deployment/service.yaml
```

## Rollback

### Rollback to Previous Version

```bash
kubectl -n quickbrush rollout undo deployment quickbrush-service
```

### Rollback to Specific Revision

```bash
# View history
kubectl -n quickbrush rollout history deployment quickbrush-service

# Rollback to revision
kubectl -n quickbrush rollout undo deployment quickbrush-service --to-revision=2
```

## Cleanup

### Delete Everything

```bash
kubectl delete namespace quickbrush
```

### Delete Just the Deployment

```bash
kubectl -n quickbrush delete deployment quickbrush-service
kubectl -n quickbrush delete service quickbrush-service
kubectl -n quickbrush delete ingress quickbrush-service-ingress
```

## Local Development

### Run with Docker Compose

```bash
# Development mode with hot reload
docker compose up

# Access at http://localhost:5000
```

### Run without Docker

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
flask --app app:app --debug run
```

## Troubleshooting

### Pods Not Starting

```bash
# Check pod status
kubectl -n quickbrush get pods

# Describe pod
kubectl -n quickbrush describe pod <pod-name>

# Check logs
kubectl -n quickbrush logs <pod-name>
```

Common issues:
- Missing secrets → Run `deployment/create-secrets.sh`
- Image pull errors → Check Docker Hub credentials
- Port conflicts → Check if port 80 is available

### Database Connection Issues

```bash
# Test MongoDB connection from pod
kubectl -n quickbrush exec -it <pod-name> -- python -c "
from pymongo import MongoClient
import os
client = MongoClient(os.environ['MONGODB_URI'])
print(client.server_info())
"
```

### SSL Certificate Issues

```bash
# Check cert-manager logs
kubectl -n cert-manager logs -l app=cert-manager

# Check certificate
kubectl -n quickbrush describe certificate quickbrush-service-cert

# Check certificate request
kubectl -n quickbrush get certificaterequest
```

## Health Checks

The deployment includes health checks:

- **Liveness**: `/api/health` - Checks if app is alive
- **Readiness**: `/api/health` - Checks if app is ready to serve traffic

Test manually:
```bash
curl https://quickbrush.online/api/health
```

## Performance Tuning

### Resource Limits

Current settings (per pod):
- Requests: 512Mi RAM, 0.25 CPU
- Limits: 1Gi RAM, 1 CPU

Adjust in `deployment/service.yaml` lines 119-126.

### Gunicorn Workers

Current: 4 workers (Dockerfile line 23)

Adjust for your needs:
```dockerfile
CMD ["gunicorn", "app:app", "-b", "0.0.0.0:80", "--workers", "8"]
```

Formula: `(2 * CPU_CORES) + 1`

## Support

For issues:
1. Check logs: `kubectl -n quickbrush logs -f deployment/quickbrush-service`
2. Check events: `kubectl -n quickbrush get events`
3. Verify secrets exist: `kubectl -n quickbrush get secrets`
