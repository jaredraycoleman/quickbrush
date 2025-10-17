# Quickbrush Refactor Documentation

## Overview

This refactor transitions Quickbrush from using Stripe Billing Credits and Meters to a subscription-based model with MongoDB for data persistence.

## Key Changes

### 1. **Data Storage**
- **Before**: Data stored in Stripe customer metadata
- **After**: MongoDB database with proper schemas for Users, Generations, Transactions, API Keys, and Logs

### 2. **Billing Model**
- **Before**: Stripe Billing Credits with meters, auto-recharge
- **After**: Subscriptions + One-time pack purchases

### 3. **Subscription Tiers**
| Tier | Price | Monthly Brushstrokes |
|------|-------|---------------------|
| Basic | $5/month | 250 |
| Pro | $10/month | 500 |
| Premium | $20/month | 1000 |
| Ultimate | $50/month | 5000 |

### 4. **One-Time Packs** (Never expire)
| Pack | Price | Brushstrokes | Cost per brushstroke |
|------|-------|--------------|---------------------|
| Small | $10 | 250 | $0.04 |
| Medium | $20 | 500 | $0.04 |
| Large | $40 | 1000 | $0.04 |
| Mega | $200 | 5000 | $0.04 |

**Note**: Packs are 50% more expensive per brushstroke than subscriptions ($0.04 vs $0.02).

### 5. **New Features**
- ✅ API key management (create, revoke, track usage)
- ✅ RESTful API for image generation
- ✅ OpenAPI documentation at `/api/docs`
- ✅ Complete transaction history in MongoDB
- ✅ Reliable Auth0-Stripe customer ID mapping

---

## Setup Instructions

### Prerequisites
1. Python 3.8+
2. MongoDB instance (Digital Ocean or local)
3. Stripe account with test mode enabled
4. Auth0 account
5. OpenAI API key

### Installation

1. **Install dependencies**
```bash
pip install -r requirements.txt
```

2. **Set up environment variables**
```bash
cp .env.example .env
# Edit .env with your actual values
```

3. **Create Stripe Products**

You need to create the following in your Stripe Dashboard:

**Subscriptions** (recurring=true):
- Basic: $5/month
- Pro: $10/month
- Premium: $20/month
- Ultimate: $50/month

**One-time packs** (recurring=false):
- Pack 250: $10
- Pack 500: $20
- Pack 1000: $40
- Pack 5000: $200

After creating, copy the `price_xxxxx` IDs to your `.env` file.

4. **Configure Stripe Webhooks**

In Stripe Dashboard, create a webhook endpoint pointing to:
```
https://yourdomain.com/webhooks/stripe
```

Subscribe to these events:
- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.paid`

Copy the webhook signing secret to `STRIPE_WEBHOOK_SECRET` in `.env`.

5. **Set up MongoDB**

Create a MongoDB database (recommended: Digital Ocean Managed MongoDB).

Add connection string to `.env`:
```
MONGODB_URI=mongodb://username:password@host:port/dbname?authSource=admin
```

6. **Initialize database**
```bash
python -c "from database import init_db, test_connection; init_db(); test_connection()"
```

7. **Run the application**
```bash
python app.py
```

The application will be available at:
- Web interface: http://localhost:5000
- API documentation: http://localhost:5000/api/docs

---

## Architecture

### File Structure
```
quickbrush/
├── app.py                  # Main Flask application
├── api_routes.py           # FastAPI routes for REST API
├── auth.py                 # Auth0 authentication
├── config.py               # Configuration management
├── database.py             # MongoDB connection
├── models.py               # MongoDB data models
├── stripe_utils.py         # Stripe integration
├── api_key_service.py      # API key management
├── maker.py                # Image generation logic
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template
└── templates/              # HTML templates
    ├── dashboard.html      # User dashboard
    ├── generate.html       # Image generation UI
    ├── api_keys.html       # API key management
    └── ...
```

### MongoDB Collections

#### `users`
Stores user accounts with Auth0 and Stripe integration.
```python
{
  "_id": ObjectId,
  "auth0_sub": str,
  "email": str,
  "name": str,
  "stripe_customer_id": str,
  "subscription": {
    "tier": str,  # "basic", "pro", "premium", "ultimate"
    "status": str,
    "stripe_subscription_id": str,
    "monthly_allowance": int,
    "allowance_used_this_period": int,
    "current_period_end": datetime
  },
  "purchased_brushstrokes": int,  # Non-expiring packs
  "created_at": datetime,
  "last_login": datetime
}
```

#### `api_keys`
API keys for programmatic access.
```python
{
  "_id": ObjectId,
  "user": User reference,
  "key_id": str,  # Public identifier (qb_xxxxx)
  "key_hash": str,  # SHA256 hash of secret
  "key_prefix": str,  # First 8 chars for identification
  "name": str,
  "is_active": bool,
  "last_used_at": datetime,
  "total_requests": int,
  "created_at": datetime,
  "expires_at": datetime
}
```

#### `generations`
Image generation history.
```python
{
  "_id": ObjectId,
  "user": User reference,
  "generation_type": str,  # "character", "scene", etc.
  "quality": str,  # "low", "medium", "high"
  "user_text": str,
  "refined_description": str,
  "image_url": str,
  "brushstrokes_used": int,
  "status": str,  # "completed", "failed"
  "source": str,  # "web", "api"
  "created_at": datetime
}
```

#### `transactions`
Complete audit trail of brushstrokes.
```python
{
  "_id": ObjectId,
  "user": User reference,
  "transaction_type": str,  # "purchase", "subscription_renewal", "usage"
  "amount": int,  # Positive for credits, negative for usage
  "balance_after": int,
  "stripe_payment_intent_id": str,
  "generation": Generation reference,
  "description": str,
  "created_at": datetime
}
```

---

## API Usage

### Authentication

All API requests require an API key in the Authorization header:
```
Authorization: Bearer qb_xxxxx:secret_key_here
```

### Endpoints

#### Generate Image
```http
POST /api/generate
Content-Type: application/json

{
  "text": "A brave knight with silver armor",
  "prompt": "Fantasy RPG character",
  "generation_type": "character",
  "quality": "medium",
  "size": "1024x1024"
}
```

Response:
```json
{
  "success": true,
  "generation_id": "507f1f77bcf86cd799439011",
  "image_url": "/static/generated/image.png",
  "refined_description": "...",
  "brushstrokes_used": 3,
  "brushstrokes_remaining": 247,
  "message": "Image generated successfully"
}
```

#### Get User Info
```http
GET /api/user
```

Response:
```json
{
  "email": "user@example.com",
  "subscription_tier": "pro",
  "subscription_status": "active",
  "total_brushstrokes": 500,
  "subscription_allowance_remaining": 450,
  "purchased_brushstrokes": 50,
  "current_period_end": "2025-11-16T00:00:00Z"
}
```

#### List Generations
```http
GET /api/generations?limit=10&offset=0
```

#### Create API Key
```http
POST /api/keys
Content-Type: application/json

{
  "name": "My App",
  "expires_in_days": 365
}
```

#### Revoke API Key
```http
DELETE /api/keys/{key_id}
```

### API Documentation

Full interactive API documentation available at:
- Swagger UI: http://localhost:5000/api/docs
- ReDoc: http://localhost:5000/api/redoc
- OpenAPI JSON: http://localhost:5000/api/openapi.json

---

## Migration Guide

### For Existing Users

The new system does NOT automatically migrate existing Stripe customer data. Here's how to handle migration:

1. **Keep old stripe_utils.py as backup**
```bash
cp stripe_utils.py stripe_utils.OLD.py
```

2. **Run migration script** (if you have existing customers)

You'll need to create a script to:
- Fetch all existing Stripe customers
- Create User records in MongoDB
- Map Stripe customer IDs to users
- Optionally grant initial brushstrokes

Example migration script:
```python
from stripe import StripeClient
from models import User, get_or_create_user
from config import Config

client = StripeClient(api_key=Config.STRIPE_SECRET_KEY)

# Fetch all customers
customers = client.v1.customers.list(params={"limit": 100})

for customer in customers.data:
    auth0_sub = customer.metadata.get("auth0_sub")
    if auth0_sub:
        # Create user in MongoDB
        user = get_or_create_user(
            auth0_sub=auth0_sub,
            email=customer.email,
        )

        # Link Stripe customer
        user.stripe_customer_id = customer.id

        # Optionally grant initial brushstrokes
        user.add_purchased_brushstrokes(100)

        user.save()
        print(f"Migrated: {customer.email}")
```

---

## Dashboard Updates Needed

The dashboard template needs to be updated to show:

1. **Subscription section** (instead of credits)
   - Current tier
   - Monthly allowance
   - Used this period
   - Remaining
   - Renewal date
   - Upgrade/cancel buttons

2. **Purchased packs section**
   - Total purchased brushstrokes
   - Purchase buttons for packs

3. **API keys section**
   - List of active keys
   - Create new key button
   - Revoke button for each key

Example structure for `dashboard.html`:
```html
<div class="subscription-info">
  {% if subscription %}
    <h3>Subscription: {{ subscription.tier|title }}</h3>
    <p>{{ subscription.allowance_remaining }} / {{ subscription.monthly_allowance }} brushstrokes remaining this month</p>
    <p>Renews: {{ subscription.current_period_end|date }}</p>
    {% if not subscription.cancel_at_period_end %}
      <form method="POST" action="/cancel-subscription">
        <button>Cancel Subscription</button>
      </form>
    {% endif %}
  {% else %}
    <h3>No Active Subscription</h3>
    <a href="/subscribe?price_id={{ stripe_prices.basic }}">Subscribe to Basic ($5/mo)</a>
    <a href="/subscribe?price_id={{ stripe_prices.pro }}">Subscribe to Pro ($10/mo)</a>
    <a href="/subscribe?price_id={{ stripe_prices.premium }}">Subscribe to Premium ($20/mo)</a>
    <a href="/subscribe?price_id={{ stripe_prices.ultimate }}">Subscribe to Ultimate ($50/mo)</a>
  {% endif %}
</div>

<div class="purchased-packs">
  <h3>Purchased Packs: {{ purchased_brushstrokes }} brushstrokes</h3>
  <a href="/buy-pack?price_id={{ stripe_prices.pack_250 }}">Buy 250 ($10)</a>
  <a href="/buy-pack?price_id={{ stripe_prices.pack_500 }}">Buy 500 ($20)</a>
  <a href="/buy-pack?price_id={{ stripe_prices.pack_1000 }}">Buy 1000 ($40)</a>
  <a href="/buy-pack?price_id={{ stripe_prices.pack_5000 }}">Buy 5000 ($200)</a>
</div>

<div class="api-keys">
  <h3>API Keys</h3>
  <a href="/api-keys">Manage API Keys</a>
</div>
```

---

## Testing

### Test Subscription Flow
1. Go to dashboard
2. Click subscribe button
3. Complete Stripe checkout
4. Verify subscription appears on dashboard
5. Generate an image
6. Verify brushstrokes deducted from subscription allowance

### Test Pack Purchase
1. Go to dashboard
2. Click buy pack button
3. Complete Stripe checkout
4. Verify brushstrokes added to account
5. Generate images until subscription allowance exhausted
6. Verify system uses purchased pack brushstrokes

### Test API
1. Create API key on dashboard
2. Copy key
3. Make API request:
```bash
curl -X POST http://localhost:5000/api/generate \
  -H "Authorization: Bearer qb_xxxxx:secret" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "A wizard casting a spell",
    "generation_type": "character",
    "quality": "low"
  }'
```

### Test Webhooks (Local Development)
Use Stripe CLI to forward webhooks:
```bash
stripe listen --forward-to localhost:5000/webhooks/stripe
stripe trigger customer.subscription.created
stripe trigger invoice.paid
```

---

## Troubleshooting

### "Failed to connect to MongoDB"
- Check `MONGODB_URI` in `.env`
- Verify MongoDB server is running
- Check firewall rules (Digital Ocean)
- Ensure credentials are correct

### "Invalid subscription price_id"
- Verify price IDs in `.env` match Stripe Dashboard
- Ensure prices are created in correct mode (test/live)

### "Webhook signature verification failed"
- Check `STRIPE_WEBHOOK_SECRET` in `.env`
- Ensure webhook secret is from correct endpoint
- For local development, use Stripe CLI

### "Insufficient brushstrokes"
- Check user balance: `user.total_brushstrokes()`
- Verify subscription status
- Check transaction history in MongoDB

---

## Production Deployment

### Checklist
- [ ] Set up production MongoDB instance
- [ ] Create Stripe products in live mode
- [ ] Configure Auth0 for production domain
- [ ] Set up proper HTTPS/SSL
- [ ] Configure Stripe webhook for production URL
- [ ] Set strong `APP_SECRET_KEY`
- [ ] Enable MongoDB authentication
- [ ] Set up monitoring/logging
- [ ] Configure backup for MongoDB
- [ ] Test all payment flows thoroughly

### Environment Variables (Production)
```bash
# Use production Stripe keys
STRIPE_SECRET_KEY=sk_live_xxxxx
STRIPE_WEBHOOK_SECRET=whsec_live_xxxxx

# Use production Auth0
AUTH0_DOMAIN=production.auth0.com
AUTH0_CALLBACK_URL=https://yourdomain.com/callback

# Use production MongoDB
MONGODB_URI=mongodb://user:pass@production-host:27017/quickbrush?ssl=true&authSource=admin
```

---

## Support

For issues or questions:
1. Check this documentation
2. Review error logs
3. Check MongoDB connection
4. Verify Stripe webhook events
5. Test with Stripe test cards

---

## License

[Your License Here]
