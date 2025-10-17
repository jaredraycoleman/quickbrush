# ✅ Setup Complete - Next Steps

Great news! All the code is in place and dependencies are installed. MongoDB is connected and working. Here's what you need to do to get fully operational:

## 🎯 Immediate Tasks (30 minutes)

### 1. Create Stripe Products (15 minutes)

You need to create 8 products in your Stripe Dashboard. Go to: https://dashboard.stripe.com/test/products

#### Create these 4 SUBSCRIPTIONS:
1. **Basic Plan** - $5/month (recurring)
2. **Pro Plan** - $10/month (recurring)
3. **Premium Plan** - $20/month (recurring)
4. **Ultimate Plan** - $50/month (recurring)

#### Create these 4 ONE-TIME PRODUCTS:
5. **250 Brushstrokes Pack** - $10 (one-time)
6. **500 Brushstrokes Pack** - $20 (one-time)
7. **1000 Brushstrokes Pack** - $40 (one-time)
8. **5000 Brushstrokes Pack** - $200 (one-time)

**After creating each, copy the `price_xxxxx` ID** and add them to your `.env` file.

### 2. Update .env File (5 minutes)

Edit your `.env` file and add the price IDs:

```bash
# Subscription Price IDs
STRIPE_PRICE_BASIC=price_xxxxx        # $5/month
STRIPE_PRICE_PRO=price_xxxxx          # $10/month
STRIPE_PRICE_PREMIUM=price_xxxxx      # $20/month
STRIPE_PRICE_ULTIMATE=price_xxxxx     # $50/month

# Pack Price IDs
STRIPE_PRICE_PACK_250=price_xxxxx     # $10
STRIPE_PRICE_PACK_500=price_xxxxx     # $20
STRIPE_PRICE_PACK_1000=price_xxxxx    # $40
STRIPE_PRICE_PACK_5000=price_xxxxx    # $200
```

### 3. Set Up Stripe Webhooks (10 minutes)

For local testing, use Stripe CLI:

```bash
# Install Stripe CLI (if not installed)
# macOS: brew install stripe/stripe-cli/stripe
# Linux/WSL: Follow https://stripe.com/docs/stripe-cli

# Login to Stripe
stripe login

# Forward webhooks to your local server
stripe listen --forward-to localhost:5000/webhooks/stripe
```

Copy the webhook signing secret that appears and add to `.env`:
```bash
STRIPE_WEBHOOK_SECRET=whsec_xxxxx
```

## 🚀 Running the Application

Start the app:
```bash
python app.py
```

Visit:
- **Web UI:** http://localhost:5000
- **API Docs:** http://localhost:5000/api/docs

## 🧪 Testing Checklist

### Test 1: User Registration
- [ ] Visit http://localhost:5000
- [ ] Login with Auth0
- [ ] Check MongoDB: `db.users.find().pretty()`
- [ ] Verify user was created

### Test 2: Generate an Image (No subscription yet)
- [ ] Go to /generate
- [ ] Try to generate (should fail with "insufficient brushstrokes")

### Test 3: Buy a Pack
- [ ] Go to /buy-pack?price_id=YOUR_PACK_250_PRICE_ID
- [ ] Use test card: `4242 4242 4242 4242`
- [ ] Complete purchase
- [ ] Verify brushstrokes added to account
- [ ] Check MongoDB transactions: `db.transactions.find().pretty()`

### Test 4: Generate an Image (With brushstrokes)
- [ ] Go to /generate
- [ ] Generate a character
- [ ] Verify image appears
- [ ] Check brushstrokes deducted
- [ ] Check MongoDB: `db.generations.find().pretty()`

### Test 5: Subscribe
- [ ] Go to /subscribe?price_id=YOUR_BASIC_PRICE_ID
- [ ] Complete subscription
- [ ] Verify subscription shows up
- [ ] Check you have 250 brushstrokes allowance

### Test 6: API Keys
- [ ] Go to /api-keys
- [ ] Create a new key
- [ ] Copy the key (shown once!)
- [ ] Test API:

```bash
curl -X POST http://localhost:5000/api/generate \
  -H "Authorization: Bearer YOUR_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "A wizard",
    "generation_type": "character",
    "quality": "low"
  }'
```

## 📝 Dashboard UI Update Needed

Your `templates/dashboard.html` needs to be updated to show:

1. **Subscription section** with:
   - Current tier
   - Monthly allowance progress
   - Subscribe/upgrade buttons
   - Cancel button

2. **Purchased packs section** with:
   - Total purchased brushstrokes
   - Buy pack buttons

3. **API keys section** with:
   - Link to /api-keys

See example in [REFACTOR_README.md](REFACTOR_README.md) around line 600.

## 🔍 Monitoring

### Check MongoDB Data
```bash
# Connect to your MongoDB
mongo "YOUR_MONGODB_URI"

use quickbrush

# See all users
db.users.find().pretty()

# See transactions
db.transactions.find().sort({created_at: -1}).limit(10).pretty()

# See generations
db.generations.find().sort({created_at: -1}).limit(10).pretty()

# See API keys
db.api_keys.find().pretty()
```

### Check Stripe Dashboard
- **Payments**: https://dashboard.stripe.com/test/payments
- **Subscriptions**: https://dashboard.stripe.com/test/subscriptions
- **Customers**: https://dashboard.stripe.com/test/customers
- **Webhooks**: https://dashboard.stripe.com/test/webhooks

## 🐛 Troubleshooting

### Can't create subscription
- Make sure price IDs in .env are correct
- Check they're from test mode (start with `price_test_`)
- Verify webhook is listening

### Brushstrokes not deducted
- Check MongoDB user record
- Check transactions collection
- Look at app logs for errors

### Webhook not working
- Make sure `stripe listen` is running
- Check webhook secret in .env
- Look at Stripe CLI output for errors

## 📚 Documentation

- **Quick Start**: [GETTING_STARTED.md](GETTING_STARTED.md)
- **Full Documentation**: [REFACTOR_README.md](REFACTOR_README.md)
- **What Changed**: [REFACTOR_SUMMARY.md](REFACTOR_SUMMARY.md)

## 🎉 You're Almost There!

Once you:
1. ✅ Create Stripe products
2. ✅ Add price IDs to .env
3. ✅ Set up webhooks
4. ✅ Update dashboard template

Your app will be fully functional with:
- ✅ MongoDB persistence
- ✅ Subscription billing
- ✅ One-time pack purchases
- ✅ API access with keys
- ✅ Complete transaction history

**Current Status:**
- ✅ MongoDB connected
- ✅ All dependencies installed
- ✅ Code ready to run
- ⏳ Waiting for Stripe products
- ⏳ Waiting for dashboard UI update

Run `python app.py` and start testing!
