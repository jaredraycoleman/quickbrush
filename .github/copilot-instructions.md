# Quickbrush AI Development Guide

## Project Overview

**Quickbrush** is a fantasy RPG artwork generation SaaS built with Flask (web UI) + FastAPI (REST API), using OpenAI's image generation models. The platform supports:
- Multi-client integrations: web dashboard, Obsidian plugin, Foundry VTT module
- Subscription & one-time purchase models via Stripe
- Invitation-based access control with admin management
- Rate limiting and image storage management (max 100 images/user in MongoDB)

## Architecture

### Dual App Structure (Flask + FastAPI)
- **Flask app** (`app.py`): Web UI, OAuth, session management
- **FastAPI app** (`api_routes.py`): REST API mounted at `/api` via `a2wsgi.ASGIMiddleware`
- Both share service layer (`*_service.py` files) to eliminate code duplication

### Data Flow Patterns

**Image Generation Pipeline:**
1. Rate limiting check (`rate_limiter.py`) → fail fast before checking balance
2. Balance check (`stripe_utils.get_subscription_info()`) → subscription allowance from Stripe + purchased packs from MongoDB
3. Generate refined description with GPT-4o (`maker.py:ImageGenerator.get_description()`)
4. Generate image with OpenAI (`maker.py:ImageGenerator.generate_image()`) → returns WebP bytes
5. Save to MongoDB (`image_service.save_generation_with_image()`) → enforces 100 image limit
6. Record usage (`stripe_utils.record_generation()`) → deducts from subscription allowance first, then purchased packs

**Subscription Hierarchy:**
- **Stripe = single source of truth** for subscription state (tier, status, dates)
- **MongoDB** only stores: `stripe_subscription_id`, `current_period_start`, `allowance_used_this_period`
- Call `stripe_utils.check_and_renew_subscription()` on login/generation to sync period and reset allowance

### Service Layer Organization

Each service is single-purpose with minimal dependencies:
- `generation_service.py`: Unified generation logic for web + API
- `image_service.py`: MongoDB image CRUD + 100 image limit enforcement
- `stripe_utils.py`: All Stripe operations (subscriptions, purchases, customer management)
- `api_key_service.py`: API key creation, validation, hashing
- `account_service.py`: Account deletion with cascade cleanup
- `admin_service.py`: User search, token gifting, invitation codes

## Critical Conventions

### Brushstroke Balance Calculation
```python
# ALWAYS use this pattern when checking balance:
subscription_info_tuple = get_subscription_info(user)
monthly_allowance = subscription_info_tuple[1] if subscription_info_tuple else 0
total_balance = user.total_brushstrokes(monthly_allowance)
```
Never read subscription tier/allowance from MongoDB—it's stale. Fetch from Stripe on-demand.

### Reference Images
- Max 3 reference images per generation
- Converted to PNG via `convert_for_openai()` before sending to OpenAI
- Passed through entire pipeline: description generation → image generation
- Auto-extracted in Obsidian plugin from note content

### Image Storage
- Images stored as **WebP binary data** in MongoDB (`Generation.image_data`)
- Limit: 100 images/user enforced in `image_service.enforce_image_limit()`
- Served via `/image/<generation_id>` (Flask) and `/api/image/<generation_id>` (FastAPI)
- Legacy `image_url` and `image_filename` fields are deprecated but kept for backward compatibility

### Rate Limiting
- Two-tier: 1/10sec (short-term) + 50/hour (hourly)
- Stored in MongoDB with TTL index (auto-cleanup after 1 hour)
- Check rate limit **before** balance check to prevent abuse
- Configuration in `config.py:Config.get_rate_limits()`

### Authentication Patterns

**Web (Flask):**
```python
@login_required  # Auth0 OAuth session check
@invite_required  # Has valid invitation code
@admin_required  # User.is_admin == True
```

**API (FastAPI):**
```python
user: User = Depends(get_current_user)  # API key in Authorization header
# Format: "Bearer qb_xxxxx:secret"
```

### Aspect Ratio Defaults
- **Scenes**: Default to `landscape` (1536x1024)
- **Character/Creature/Item**: Default to `square` (1024x1024)
- See `generation_service.generate_image()` lines 106-110

## Development Workflows

### Local Development
```bash
# With Docker (recommended)
docker compose up

# Without Docker
pip install -r requirements.txt
flask --app app:app --debug run

# Access at http://localhost:5000
```

### Running Tests
```bash
pytest tests/
# Note: Most tests in tests/test_api.py require MongoDB + valid API keys
```

### Deployment (Kubernetes)
```bash
./deploy.sh  # Builds image, regenerates secrets, applies k8s config
```
See `deployment/README.md` for detailed steps. Key points:
- Secrets managed via `deployment/create-secrets.sh`
- Traefik ingress for SSL
- Gunicorn with 4 workers (adjust for CPU cores)

### Admin Setup
```bash
python setup_admin.py  # Creates first admin user + invitation codes
```

## Integration Points

### Obsidian Plugin (`quickbrush-obsidian-plugin/`)
- TypeScript plugin compiled with esbuild
- Auto-extracts text from active note (excluding frontmatter)
- Auto-selects first 3 embedded images as references
- Saves images to `quickbrush-images/` folder
- Creates timestamped gallery notes in `quickbrush-gallery/`

### Foundry VTT Module (`foundry-module/`)
- JavaScript module with journal button integration
- Manifest served at `/foundry-module/module.json`
- Auto-creates "Quickbrush Gallery" journal entry
- Uses Foundry's file picker for image storage

### API Client Pattern
```javascript
// Reference implementation in foundry-module/scripts/quickbrush.js
const response = await fetch('https://quickbrush.ai/api/generate', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${apiKey}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    text: description,
    generation_type: 'character',
    quality: 'medium',
    aspect_ratio: 'square'
  })
});
```

## Common Pitfalls

1. **Never store subscription state in MongoDB**—always fetch from Stripe via `get_subscription_info()`
2. **Check rate limits before balance checks**—prevents exposing balance to rate-limited users
3. **Use `generation_service.generate_image()` for all generation**—don't duplicate logic in routes
4. **WebP format required**—convert all generated images from PNG to WebP before saving
5. **Max 100 images enforced**—`enforce_image_limit()` deletes oldest images automatically
6. **API keys are hashed**—never log or expose the secret portion after creation
7. **Reference images must be PNG**—use `convert_for_openai()` if format differs
8. **Stripe webhooks not used**—all state pulled on-demand (login, generation, etc.)

## Code Patterns to Follow

### Adding a New Generation Type
1. Create class in `maker.py` inheriting from `ImageGenerator`
2. Implement `get_description()` and `get_prompt()`
3. Add to `generator_map` in `generation_service.generate_image()` (line ~125)
4. Add enum value to `models.ImageGenerationType`
5. Update UI dropdowns in `templates/generate.html`
6. Update API schema in `api_routes.py:GenerateImageRequest`

### Adding a New Service
- Create `{feature}_service.py` with focused, single-purpose functions
- Accept `User` object as first parameter (dependency injection)
- Return simple data structures or service-specific result classes
- Handle errors gracefully—log and return error messages, don't raise
- Example: `account_service.delete_user_account()` returns `(bool, str)` tuple

### Environment Variables
All config in `config.py:Config` class—never read `os.environ` elsewhere. Required vars:
- Auth0: `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `AUTH0_CALLBACK_URL`, `AUTH0_AUDIENCE`
- MongoDB: `MONGODB_URI`, `MONGODB_DB_NAME`
- Stripe: `STRIPE_SECRET_KEY`, 8 price IDs (`STRIPE_PRICE_*`)
- OpenAI: `OPENAI_API_KEY`

## External Dependencies

- **OpenAI**: Image generation (`gpt-image-1-mini` model) + description refinement (`gpt-4o`)
- **Stripe**: Subscriptions & payments (no webhooks—state pulled on-demand)
- **MongoDB**: Primary datastore (MongoDB Atlas hosted)
- **Auth0**: OAuth authentication for web UI

## File Organization Logic

- `app.py`: Flask routes (web UI only)
- `api_routes.py`: FastAPI routes (API only)
- `models.py`: MongoEngine schemas (single source of truth for data structure)
- `*_service.py`: Business logic (shared between Flask & FastAPI)
- `maker.py`: OpenAI image generation logic (generator classes)
- `config.py`: Environment variables & constants
- `templates/`: Jinja2 HTML templates (Flask only)
- `static/`: CSS, JS, images for web UI

---

**When in doubt:** Check `generation_service.py` for the canonical generation pipeline, `stripe_utils.py` for subscription logic, and `models.py` for data structures.
