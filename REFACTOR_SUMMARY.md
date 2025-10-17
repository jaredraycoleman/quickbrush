# Quickbrush Refactor Summary

## What Was Done

I've successfully refactored your Quickbrush application with the following major changes:

### 1. ✅ Removed Stripe Billing Credits and Meters
- Completely removed the old credits-based billing system
- Removed auto-recharge functionality
- Removed meter event tracking
- No more 30-day credit expiration

### 2. ✅ Implemented Subscription-Based Model
**New subscription tiers:**
- **Basic**: $5/month → 250 brushstrokes/month
- **Pro**: $10/month → 500 brushstrokes/month
- **Premium**: $20/month → 1000 brushstrokes/month
- **Ultimate**: $50/month → 5000 brushstrokes/month

**Features:**
- Monthly allowance resets each billing cycle
- Subscription allowance used first, then purchased packs
- Cancel anytime (keeps access until period end)
- Managed via Stripe Customer Portal

### 3. ✅ Added One-Time Brushstroke Packs
Users can purchase non-expiring brushstroke packs:
- **250 brushstrokes** for $10 ($0.04 each)
- **500 brushstrokes** for $20 ($0.04 each)
- **1000 brushstrokes** for $40 ($0.04 each)
- **5000 brushstrokes** for $200 ($0.04 each)

**Pricing strategy:** Packs are 50% more expensive per brushstroke than subscriptions, incentivizing subscriptions.

### 4. ✅ MongoDB Integration
**New database with 5 collections:**

1. **users** - User accounts with Auth0 & Stripe integration
2. **api_keys** - API key management with hashing
3. **generations** - Complete image generation history
4. **transactions** - Full audit trail of all brushstroke movements
5. **logs** - Application logging (optional)

**Benefits:**
- Reliable data persistence
- Fast queries with proper indexes
- Complete transaction history
- No more reliance on Stripe metadata

### 5. ✅ Improved Auth0-Stripe Integration
**Before:** Searched Stripe for customers by auth0_sub metadata (unreliable, allows duplicates)

**After:**
- Customer ID stored in MongoDB User model
- Created on-demand when needed
- Single source of truth
- No duplicate customers

### 6. ✅ API Key System
Users can now create and manage API keys:
- Create unlimited keys with custom names
- Optional expiration dates
- Revoke anytime
- Track usage (last used, total requests)
- Secure hashing (SHA256)
- Format: `qb_xxxxx:secret`

### 7. ✅ RESTful API with FastAPI
**New API endpoints:**
- `POST /api/generate` - Generate images programmatically
- `GET /api/user` - Get account info
- `GET /api/generations` - List generation history
- `POST /api/keys` - Create API key
- `DELETE /api/keys/{key_id}` - Revoke API key

**Features:**
- OpenAPI documentation at `/api/docs`
- Pydantic request validation
- Bearer token authentication
- Comprehensive error handling

### 8. ✅ Stripe Webhooks
Properly handles all subscription events:
- `checkout.session.completed` - One-time purchases & subscription signups
- `customer.subscription.created` - New subscriptions
- `customer.subscription.updated` - Plan changes, cancellations
- `customer.subscription.deleted` - Subscription end
- `invoice.paid` - Monthly renewals (resets allowance)

### 9. ✅ Updated Flask Routes
**New routes:**
- `/subscribe?price_id=xxx` - Subscribe to a plan
- `/cancel-subscription` - Cancel subscription
- `/buy-pack?price_id=xxx` - Purchase brushstroke pack
- `/checkout-success` - Handle successful payments
- `/webhooks/stripe` - Stripe webhook endpoint
- `/api-keys` - Manage API keys
- `/api-keys/create` - Create new API key
- `/api-keys/revoke/{key_id}` - Revoke API key

**Updated routes:**
- `/dashboard` - Now shows subscription info, pack balance, API keys
- `/generate` - Uses new MongoDB-based user system
- `/portal` - Still redirects to Stripe Customer Portal

---

## File Changes

### New Files Created
1. `models.py` - MongoDB schema definitions (600+ lines)
2. `database.py` - MongoDB connection management
3. `api_routes.py` - FastAPI REST API (400+ lines)
4. `api_key_service.py` - API key CRUD operations
5. `requirements.txt` - All Python dependencies
6. `.env.example` - Environment variable template
7. `REFACTOR_README.md` - Complete documentation
8. `templates/api_keys.html` - API key management UI

### Modified Files
1. `config.py` - Added MongoDB config, new Stripe price IDs
2. `stripe_utils.py` - Completely rewritten (640 lines → subscription/pack model)
3. `app.py` - Refactored to use MongoDB, new routes (380 → 640 lines)

### Files to Update (Next Steps)
1. `templates/dashboard.html` - Need to update UI for subscriptions
2. `templates/base.html` - Might need style updates

---

## Configuration Required

### Environment Variables Needed
```bash
# MongoDB
MONGODB_URI=mongodb://user:pass@host:port/dbname?authSource=admin
MONGODB_DB_NAME=quickbrush

# Stripe Products (create in Stripe Dashboard)
STRIPE_PRICE_BASIC=price_xxxxx
STRIPE_PRICE_PRO=price_xxxxx
STRIPE_PRICE_PREMIUM=price_xxxxx
STRIPE_PRICE_ULTIMATE=price_xxxxx
STRIPE_PRICE_PACK_250=price_xxxxx
STRIPE_PRICE_PACK_500=price_xxxxx
STRIPE_PRICE_PACK_1000=price_xxxxx
STRIPE_PRICE_PACK_5000=price_xxxxx

# Stripe Webhook
STRIPE_WEBHOOK_SECRET=whsec_xxxxx
```

### Stripe Dashboard Setup Required
1. **Create 4 subscription products** with recurring prices
2. **Create 4 one-time products** with one-time prices
3. **Set up webhook** pointing to `/webhooks/stripe`
4. **Subscribe to events** listed above

---

## Next Steps

### 1. Update Dashboard Template
The dashboard needs UI updates to display:
- Current subscription tier and status
- Monthly allowance progress bar
- Purchased brushstrokes balance
- Subscribe/upgrade buttons
- Pack purchase buttons
- Link to API keys page

Example structure provided in `REFACTOR_README.md`.

### 2. Create Stripe Products
Follow instructions in `REFACTOR_README.md` to:
- Create 4 subscription products
- Create 4 one-time pack products
- Copy price IDs to `.env`

### 3. Set Up MongoDB
- Create Digital Ocean managed database OR
- Install MongoDB locally
- Add connection string to `.env`
- Test connection: `python -c "from database import init_db, test_connection; init_db(); test_connection()"`

### 4. Configure Stripe Webhooks
- Create webhook endpoint in Stripe Dashboard
- Add webhook secret to `.env`
- Test with Stripe CLI: `stripe listen --forward-to localhost:5000/webhooks/stripe`

### 5. Test Everything
Run through the test scenarios in `REFACTOR_README.md`:
- [ ] Subscription signup
- [ ] Pack purchase
- [ ] Image generation (deducting from allowance)
- [ ] Image generation (deducting from packs)
- [ ] API key creation
- [ ] API generation request
- [ ] Subscription cancellation
- [ ] Monthly renewal (test with Stripe CLI)

### 6. Migration (If you have existing users)
Create a migration script to:
- Fetch existing Stripe customers
- Create User records in MongoDB
- Link Stripe customer IDs
- Optionally grant initial brushstrokes

Example provided in `REFACTOR_README.md`.

---

## Architecture Benefits

### Before
- ❌ Data scattered across Stripe metadata
- ❌ Credits expire after 30 days
- ❌ Complex auto-recharge logic
- ❌ Unreliable customer lookups
- ❌ No API access
- ❌ No transaction history
- ❌ Billing meters for analytics only

### After
- ✅ All data in MongoDB (single source of truth)
- ✅ Purchased packs never expire
- ✅ Simple subscription model
- ✅ Reliable customer ID mapping
- ✅ Full REST API with documentation
- ✅ Complete transaction audit trail
- ✅ Standard Stripe subscriptions

---

## Pricing Comparison

### Subscription Model (Recommended)
| Tier | Price | Brushstrokes | Cost/Brushstroke |
|------|-------|--------------|------------------|
| Basic | $5/mo | 250 | $0.02 |
| Pro | $10/mo | 500 | $0.02 |
| Premium | $20/mo | 1000 | $0.02 |
| Ultimate | $50/mo | 5000 | $0.01 |

### One-Time Packs
| Pack | Price | Brushstrokes | Cost/Brushstroke |
|------|-------|--------------|------------------|
| Small | $10 | 250 | $0.04 |
| Medium | $20 | 500 | $0.04 |
| Large | $40 | 1000 | $0.04 |
| Mega | $200 | 5000 | $0.04 |

**Key insight:** Subscriptions are 50-100% cheaper per brushstroke, encouraging recurring revenue.

---

## API Example

```bash
# Create API key (via dashboard UI)
# Then use it:

curl -X POST https://yourdomain.com/api/generate \
  -H "Authorization: Bearer qb_abc123:secret_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "A brave knight",
    "generation_type": "character",
    "quality": "medium"
  }'
```

Response:
```json
{
  "success": true,
  "generation_id": "507f1f77bcf86cd799439011",
  "image_url": "/static/generated/image.png",
  "refined_description": "A brave knight in shining armor...",
  "brushstrokes_used": 3,
  "brushstrokes_remaining": 497,
  "message": "Image generated successfully"
}
```

---

## Questions?

Refer to `REFACTOR_README.md` for:
- Complete setup instructions
- MongoDB schema details
- API documentation
- Testing procedures
- Troubleshooting guide
- Production deployment checklist

---

## Summary Statistics

**Lines of Code:**
- New code: ~3,000 lines
- Models: 600 lines
- Stripe utils: 640 lines (complete rewrite)
- API routes: 400 lines
- App.py: 640 lines (refactored)
- Documentation: 500+ lines

**Files Created:** 8 new files
**Files Modified:** 3 core files
**Collections:** 5 MongoDB collections
**API Endpoints:** 6 new endpoints
**Webhooks:** 5 event handlers

---

## Ready to Deploy!

Once you:
1. Set up MongoDB
2. Create Stripe products
3. Configure webhooks
4. Update dashboard template
5. Test all flows

You'll have a production-ready subscription-based image generation platform with full API access!
