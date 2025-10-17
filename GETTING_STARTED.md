# Getting Started with the Refactored Quickbrush

This is your step-by-step guide to get the new system running.

## 📋 Prerequisites Checklist

- [ ] Python 3.8+ installed
- [ ] pip installed
- [ ] MongoDB instance available (Digital Ocean recommended)
- [ ] Stripe account (test mode is fine for now)
- [ ] Auth0 account configured
- [ ] OpenAI API key

---

## 🚀 Quick Start (30 minutes)

### Step 1: Install Dependencies (2 minutes)

```bash
cd /home/jared/quickbrush
pip install -r requirements.txt
```

### Step 2: Set Up Environment Variables (5 minutes)

```bash
# Copy the example file
cp .env.example .env

# Edit with your values
nano .env  # or use your preferred editor
```

**Required variables to fill in:**
```bash
# Keep existing Auth0 and OpenAI values
# Add these new ones:

# MongoDB (Digital Ocean)
MONGODB_URI=mongodb://username:password@your-host:27017/quickbrush?authSource=admin
MONGODB_DB_NAME=quickbrush

# Stripe webhook secret (get this after step 5)
STRIPE_WEBHOOK_SECRET=whsec_xxxxx

# Stripe price IDs (get these from step 3)
STRIPE_PRICE_BASIC=price_xxxxx
STRIPE_PRICE_PRO=price_xxxxx
STRIPE_PRICE_PREMIUM=price_xxxxx
STRIPE_PRICE_ULTIMATE=price_xxxxx
STRIPE_PRICE_PACK_250=price_xxxxx
STRIPE_PRICE_PACK_500=price_xxxxx
STRIPE_PRICE_PACK_1000=price_xxxxx
STRIPE_PRICE_PACK_5000=price_xxxxx
```

### Step 3: Create Stripe Products (10 minutes)

Go to [Stripe Dashboard](https://dashboard.stripe.com/test/products) and create:

#### Subscriptions (4 products)
1. **Product:** "Basic Plan"
   - **Price:** $5.00 USD / month
   - **Billing period:** Monthly
   - **Copy the price ID** (starts with `price_`) → Add to .env as `STRIPE_PRICE_BASIC`

2. **Product:** "Pro Plan"
   - **Price:** $10.00 USD / month
   - **Billing period:** Monthly
   - **Copy price ID** → `STRIPE_PRICE_PRO`

3. **Product:** "Premium Plan"
   - **Price:** $20.00 USD / month
   - **Billing period:** Monthly
   - **Copy price ID** → `STRIPE_PRICE_PREMIUM`

4. **Product:** "Ultimate Plan"
   - **Price:** $50.00 USD / month
   - **Billing period:** Monthly
   - **Copy price ID** → `STRIPE_PRICE_ULTIMATE`

#### One-Time Packs (4 products)
5. **Product:** "250 Brushstrokes Pack"
   - **Price:** $10.00 USD (one-time)
   - **Copy price ID** → `STRIPE_PRICE_PACK_250`

6. **Product:** "500 Brushstrokes Pack"
   - **Price:** $20.00 USD (one-time)
   - **Copy price ID** → `STRIPE_PRICE_PACK_500`

7. **Product:** "1000 Brushstrokes Pack"
   - **Price:** $40.00 USD (one-time)
   - **Copy price ID** → `STRIPE_PRICE_PACK_1000`

8. **Product:** "5000 Brushstrokes Pack"
   - **Price:** $200.00 USD (one-time)
   - **Copy price ID** → `STRIPE_PRICE_PACK_5000`

### Step 4: Test MongoDB Connection (2 minutes)

```bash
python -c "from database import init_db, test_connection; init_db(); test_connection()"
```

✅ You should see: "MongoDB connection test successful"

❌ If it fails:
- Check MONGODB_URI in .env
- Verify MongoDB is running
- Check firewall rules (if using Digital Ocean)

### Step 5: Set Up Stripe Webhooks (5 minutes)

#### For Local Development (Recommended First)
```bash
# Install Stripe CLI if not already
brew install stripe/stripe-cli/stripe  # macOS
# or download from: https://stripe.com/docs/stripe-cli

# Login
stripe login

# Forward webhooks to local server
stripe listen --forward-to localhost:5000/webhooks/stripe
```

The CLI will display a webhook signing secret. **Copy it to your .env as `STRIPE_WEBHOOK_SECRET`**.

#### For Production (Later)
1. Go to [Stripe Webhooks](https://dashboard.stripe.com/test/webhooks)
2. Click "Add endpoint"
3. **Endpoint URL:** `https://yourdomain.com/webhooks/stripe`
4. **Events to send:**
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.paid`
5. Copy the signing secret → `STRIPE_WEBHOOK_SECRET`

### Step 6: Run the Application (1 minute)

```bash
python app.py
```

Visit: http://localhost:5000

---

## ✅ Testing Checklist

### Test 1: Login
- [ ] Go to http://localhost:5000
- [ ] Click "Login"
- [ ] Authenticate with Auth0
- [ ] See the dashboard

### Test 2: Subscribe to a Plan
- [ ] On dashboard, click "Subscribe" (you'll need to add the button)
- [ ] Select Basic plan ($5/month)
- [ ] Use Stripe test card: `4242 4242 4242 4242`
- [ ] Complete checkout
- [ ] Return to dashboard
- [ ] Verify subscription shows up

**Stripe Test Cards:**
- Success: `4242 4242 4242 4242`
- Decline: `4000 0000 0000 0002`
- Requires authentication: `4000 0025 0000 3155`

### Test 3: Purchase a Pack
- [ ] Click "Buy Pack"
- [ ] Select 250 brushstrokes ($10)
- [ ] Complete checkout with test card
- [ ] Verify brushstrokes added to account

### Test 4: Generate an Image
- [ ] Go to /generate
- [ ] Enter description: "A brave knight"
- [ ] Select quality: Medium (3 brushstrokes)
- [ ] Click Generate
- [ ] Verify image appears
- [ ] Check dashboard - brushstrokes should be deducted

### Test 5: Create API Key
- [ ] Go to /api-keys
- [ ] Create new key named "Test Key"
- [ ] Copy the key (it won't be shown again!)
- [ ] Verify it appears in the list

### Test 6: Use API
```bash
# Replace with your actual API key
curl -X POST http://localhost:5000/api/generate \
  -H "Authorization: Bearer qb_xxxxx:your_secret_here" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "A magical wizard",
    "generation_type": "character",
    "quality": "low"
  }'
```

- [ ] Verify response with image URL
- [ ] Check /api-keys - "Last Used" should update

### Test 7: View API Documentation
- [ ] Go to http://localhost:5000/api/docs
- [ ] Browse the interactive API documentation
- [ ] Try the "Try it out" feature

### Test 8: Cancel Subscription
- [ ] Go to dashboard
- [ ] Click "Cancel Subscription"
- [ ] Confirm cancellation
- [ ] Verify status changes to "canceling at period end"
- [ ] Verify you still have access (until period ends)

---

## 🎯 What to Check

### MongoDB Collections
Check that data is being created:

```bash
# Connect to MongoDB
mongo "your-connection-string"

# Switch to database
use quickbrush

# Check users
db.users.find().pretty()

# Check generations
db.generations.find().pretty()

# Check transactions
db.transactions.find().pretty()

# Check API keys
db.api_keys.find().pretty()
```

### Stripe Dashboard
- [ ] Check "Payments" - should see test payments
- [ ] Check "Subscriptions" - should see test subscription
- [ ] Check "Customers" - should see your user
- [ ] Check "Events" - should see webhook events

---

## ⚠️ Common Issues

### "Failed to connect to MongoDB"
**Solution:**
- Verify MONGODB_URI in .env
- Check MongoDB server status
- Ensure firewall allows connection
- Test with: `mongo "your-connection-string"`

### "Invalid subscription price_id"
**Solution:**
- Verify price IDs in .env match Stripe Dashboard
- Make sure you're using test mode prices
- Check for typos (they start with `price_`)

### "Webhook signature verification failed"
**Solution:**
- Make sure STRIPE_WEBHOOK_SECRET is set correctly
- Use `stripe listen` for local development
- Verify webhook endpoint in Stripe Dashboard matches your URL

### "Import errors" when running app
**Solution:**
```bash
pip install -r requirements.txt --upgrade
```

### "User not found" after login
**Solution:**
- Check MongoDB connection
- Verify user was created: `db.users.find()`
- Check app logs for errors

---

## 📱 Dashboard Update Needed

The current dashboard.html needs updates to show:
1. Subscription tier and status
2. Subscribe/upgrade buttons
3. Pack purchase buttons
4. Link to API keys page

Refer to `REFACTOR_README.md` for example HTML structure.

---

## 🚢 Production Deployment

When you're ready for production:

1. **Switch to live mode**
   - Use live Stripe keys (`sk_live_`, not `sk_test_`)
   - Create products in live mode
   - Update webhook endpoint to production URL

2. **Secure your environment**
   - Change APP_SECRET_KEY to strong random value
   - Enable MongoDB authentication
   - Use HTTPS/SSL for all endpoints
   - Set up proper logging

3. **Test thoroughly**
   - Run through all test scenarios with real (small) payments
   - Verify webhooks work from Stripe servers
   - Test subscription renewals
   - Test cancellations

4. **Monitor**
   - Set up alerts for failed webhooks
   - Monitor MongoDB performance
   - Track Stripe dashboard for issues
   - Set up error logging (Sentry, etc.)

---

## 📚 Additional Resources

- **Full Documentation:** See `REFACTOR_README.md`
- **Summary:** See `REFACTOR_SUMMARY.md`
- **Stripe Testing:** https://stripe.com/docs/testing
- **MongoDB Atlas:** https://www.mongodb.com/cloud/atlas
- **FastAPI Docs:** https://fastapi.tiangolo.com/

---

## 🆘 Need Help?

1. Check the logs: `python app.py` shows errors
2. Review `REFACTOR_README.md` for detailed troubleshooting
3. Check Stripe webhook logs for delivery issues
4. Verify MongoDB connection and data

---

## ✨ What's Next?

Once everything is working:
1. [ ] Update dashboard template with new UI
2. [ ] Customize pricing if needed
3. [ ] Add more image generation types
4. [ ] Implement usage analytics
5. [ ] Add email notifications
6. [ ] Set up monitoring
7. [ ] Deploy to production!

---

**Good luck! 🚀**
