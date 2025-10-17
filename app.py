import uuid
import pathlib
from urllib.parse import quote_plus, urlencode
from pydantic import BaseModel, ValidationError
from werkzeug.utils import secure_filename
from flask import (
    Flask,
    render_template,
    redirect,
    session,
    url_for,
    request,
    flash,
)
from dotenv import find_dotenv, load_dotenv

from config import Config
from auth import oauth, login_required
from database import init_db
from models import (
    get_or_create_user, User, Generation,
    ImageGenerationType, ImageQuality, QUALITY_COSTS
)
from maker import (
    token_cost,
    SceneImageGenerator,
    CreatureImageGenerator,
    ItemImageGenerator,
    CharacterImageGenerator,
    QUALITY,
    IMAGE_SIZE
)
from stripe_utils import (
    create_portal_session,
    get_or_create_stripe_customer,
    record_generation,
    create_subscription_checkout,
    create_pack_checkout,
    handle_checkout_completed,
    handle_subscription_created,
    handle_subscription_updated,
    handle_subscription_deleted,
    handle_invoice_paid,
    verify_webhook_signature,
    cancel_subscription,
)
from api_key_service import get_user_api_keys, create_api_key, revoke_api_key
from datetime import datetime, timezone


# ---------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------
ENV_FILE = find_dotenv()
if ENV_FILE:
    load_dotenv(ENV_FILE)

app = Flask(__name__)
app.secret_key = Config.APP_SECRET_KEY

# Initialize MongoDB
init_db()

# Initialize Auth0 (via auth.py)
oauth.init_app(app)

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------

def get_current_user() -> User:
    """Get current user from session and MongoDB."""
    if "user" not in session:
        return None

    auth0_user = session["user"]
    userinfo = auth0_user.get("userinfo", {})

    auth0_sub = userinfo.get("sub")
    email = userinfo.get("email")
    name = userinfo.get("name")
    picture = userinfo.get("picture")

    if not auth0_sub or not email:
        return None

    # Get or create user in MongoDB
    user = get_or_create_user(auth0_sub, email, name, picture)
    return user

# ---------------------------------------------------------
# Routes
# ---------------------------------------------------------

@app.route("/")
def home():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/login")
def login():
    return oauth.auth0.authorize_redirect( # type: ignore
        redirect_uri=url_for("callback", _external=True)
    )

@app.route("/callback")
def callback():
    token = oauth.auth0.authorize_access_token() # type: ignore
    session["user"] = token
    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(
        "https://" + Config.AUTH0_DOMAIN
        + "/v2/logout?"
        + urlencode(
            {
                "returnTo": url_for("home", _external=True),
                "client_id": Config.AUTH0_CLIENT_ID,
            },
            quote_via=quote_plus,
        )
    )

@app.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("login"))

    # Get subscription info
    subscription = user.subscription if user.subscription else None
    subscription_info = None
    if subscription:
        subscription_info = {
            "tier": subscription.tier,
            "status": subscription.status,
            "monthly_allowance": subscription.monthly_allowance,
            "allowance_used": subscription.allowance_used_this_period,
            "allowance_remaining": subscription.remaining_allowance(),
            "current_period_end": subscription.current_period_end,
            "cancel_at_period_end": subscription.cancel_at_period_end,
        }

    # Get API keys
    api_keys = get_user_api_keys(user, include_inactive=False)

    # Get Stripe price IDs (with fallbacks for missing config)
    try:
        stripe_prices = {
            "basic": Config.STRIPE_PRICE_BASIC,
            "pro": Config.STRIPE_PRICE_PRO,
            "premium": Config.STRIPE_PRICE_PREMIUM,
            "ultimate": Config.STRIPE_PRICE_ULTIMATE,
            "pack_250": Config.STRIPE_PRICE_PACK_250,
            "pack_500": Config.STRIPE_PRICE_PACK_500,
            "pack_1000": Config.STRIPE_PRICE_PACK_1000,
            "pack_5000": Config.STRIPE_PRICE_PACK_5000,
        }
    except Exception as e:
        # If Stripe prices aren't configured yet, use placeholders
        print(f"Warning: Stripe prices not configured: {e}")
        stripe_prices = {
            "basic": "CONFIGURE_IN_ENV",
            "pro": "CONFIGURE_IN_ENV",
            "premium": "CONFIGURE_IN_ENV",
            "ultimate": "CONFIGURE_IN_ENV",
            "pack_250": "CONFIGURE_IN_ENV",
            "pack_500": "CONFIGURE_IN_ENV",
            "pack_1000": "CONFIGURE_IN_ENV",
            "pack_5000": "CONFIGURE_IN_ENV",
        }

    return render_template(
        "dashboard.html",
        user=user,
        subscription=subscription_info,
        total_brushstrokes=user.total_brushstrokes(),
        purchased_brushstrokes=user.purchased_brushstrokes,
        api_keys=api_keys,
        stripe_prices=stripe_prices
    )


@app.route("/portal")
@login_required
def portal():
    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    try:
        url = create_portal_session(user)
        return redirect(url)
    except Exception as e:
        flash(f"Error creating portal session: {str(e)}", "danger")
        return redirect(url_for("dashboard"))


# ---------------------------------------------------------
# SUBSCRIPTION ROUTES
# ---------------------------------------------------------

@app.route("/subscribe")
@login_required
def subscribe():
    """Initiate subscription checkout."""
    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    price_id = request.args.get("price_id")
    if not price_id:
        flash("Missing price_id parameter", "danger")
        return redirect(url_for("dashboard"))

    # Validate price_id
    tiers = Config.get_subscription_tiers()
    if price_id not in tiers:
        flash("Invalid subscription tier", "danger")
        return redirect(url_for("dashboard"))

    # Create checkout session
    success_url = url_for("checkout_success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}"
    cancel_url = url_for("dashboard", _external=True)

    checkout_url = create_subscription_checkout(user, price_id, success_url, cancel_url)

    if checkout_url:
        return redirect(checkout_url)
    else:
        flash("Failed to create checkout session. Please try again.", "danger")
        return redirect(url_for("dashboard"))


@app.route("/cancel-subscription", methods=["POST"])
@login_required
def cancel_subscription_route():
    """Cancel user's subscription."""
    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    success = cancel_subscription(user)
    if success:
        flash("Subscription canceled. You'll retain access until the end of your billing period.", "success")
    else:
        flash("Failed to cancel subscription. Please try again or contact support.", "danger")

    return redirect(url_for("dashboard"))


# ---------------------------------------------------------
# PURCHASE ROUTES
# ---------------------------------------------------------

@app.route("/buy-pack")
@login_required
def buy_pack():
    """Initiate brushstroke pack purchase."""
    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    price_id = request.args.get("price_id")
    if not price_id:
        flash("Missing price_id parameter", "danger")
        return redirect(url_for("dashboard"))

    # Validate price_id
    packs = Config.get_brushstroke_packs()
    if price_id not in packs:
        flash("Invalid brushstroke pack", "danger")
        return redirect(url_for("dashboard"))

    # Create checkout session
    success_url = url_for("checkout_success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}"
    cancel_url = url_for("dashboard", _external=True)

    checkout_url = create_pack_checkout(user, price_id, success_url, cancel_url)

    if checkout_url:
        return redirect(checkout_url)
    else:
        flash("Failed to create checkout session. Please try again.", "danger")
        return redirect(url_for("dashboard"))


@app.route("/checkout-success")
@login_required
def checkout_success():
    """Handle successful checkout."""
    session_id = request.args.get("session_id")
    if not session_id:
        flash("Invalid checkout session.", "danger")
        return redirect(url_for("dashboard"))

    # Handle the checkout completion
    success = handle_checkout_completed(session_id)
    if success:
        flash("Payment successful! Your account has been updated.", "success")
    else:
        flash("There was an issue processing your payment. Please contact support if this persists.", "warning")

    return redirect(url_for("dashboard"))


# ---------------------------------------------------------
# STRIPE WEBHOOKS
# ---------------------------------------------------------

@app.route("/webhooks/stripe", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhooks."""
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    # Verify signature
    if not verify_webhook_signature(payload, sig_header):
        return {"error": "Invalid signature"}, 400

    try:
        import json
        event = json.loads(payload)
    except Exception as e:
        return {"error": "Invalid payload"}, 400

    event_type = event.get("type")
    data_object = event.get("data", {}).get("object", {})

    # Handle different event types
    if event_type == "checkout.session.completed":
        handle_checkout_completed(data_object.get("id"))

    elif event_type == "customer.subscription.created":
        handle_subscription_created(data_object.get("id"))

    elif event_type == "customer.subscription.updated":
        handle_subscription_updated(data_object.get("id"))

    elif event_type == "customer.subscription.deleted":
        handle_subscription_deleted(data_object.get("id"))

    elif event_type == "invoice.paid":
        handle_invoice_paid(data_object.get("id"))

    else:
        print(f"Unhandled webhook event: {event_type}")

    return {"status": "success"}, 200


# ---------------------------------------------------------
# API KEY MANAGEMENT ROUTES
# ---------------------------------------------------------

@app.route("/api-keys")
@login_required
def api_keys_page():
    """API key management page."""
    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    keys = get_user_api_keys(user, include_inactive=True)

    return render_template("api_keys.html", api_keys=keys, user=user)


@app.route("/api-keys/create", methods=["POST"])
@login_required
def create_api_key_route():
    """Create a new API key."""
    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    name = request.form.get("name")
    if not name:
        flash("API key name is required", "danger")
        return redirect(url_for("api_keys_page"))

    expires_in_days = request.form.get("expires_in_days")
    expires_in_days = int(expires_in_days) if expires_in_days else None

    try:
        api_key, secret = create_api_key(user, name, expires_in_days)
        full_key = f"{api_key.key_id}:{secret}"

        flash(f"API key created successfully! Key: {full_key}", "success")
        flash("Save this key now - it won't be shown again!", "warning")

        return redirect(url_for("api_keys_page"))

    except Exception as e:
        flash(f"Error creating API key: {str(e)}", "danger")
        return redirect(url_for("api_keys_page"))


@app.route("/api-keys/revoke/<key_id>", methods=["POST"])
@login_required
def revoke_api_key_route(key_id: str):
    """Revoke an API key."""
    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    from models import APIKey
    api_key = APIKey.objects(key_id=key_id, user=user).first()

    if not api_key:
        flash("API key not found", "danger")
        return redirect(url_for("api_keys_page"))

    success = revoke_api_key(api_key)
    if success:
        flash("API key revoked successfully", "success")
    else:
        flash("Failed to revoke API key", "danger")

    return redirect(url_for("api_keys_page"))


# ---------------------------------------------------------
# IMAGE GENERATION ROUTES
# ---------------------------------------------------------

GENERATED_DIR = pathlib.Path("static/generated")
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

class GenerateRequest(BaseModel):
    text: str
    prompt: str
    quality: QUALITY = "medium"
    size: IMAGE_SIZE = "1024x1024"

@app.route("/generate", methods=["GET", "POST"])
@login_required
def generate():
    if request.method == "POST":
        user = get_current_user()
        if not user:
            flash("Error loading user data", "danger")
            return redirect(url_for("dashboard"))

        # Capture form data for state preservation
        form_data = {
            "text": request.form.get("text", ""),
            "prompt": request.form.get("prompt", ""),
            "quality": request.form.get("quality", "medium"),
            "size": request.form.get("size", "1024x1024"),
            "gen_type": request.form.get("gen_type", "character"),
        }

        # Validate input data
        try:
            data = GenerateRequest(
                text=form_data["text"],
                prompt=form_data["prompt"],
                quality=form_data["quality"], # type: ignore
                size=form_data["size"], # type: ignore
            )
        except ValidationError as e:
            for err in e.errors():
                field = err['loc'][0] if err['loc'] else 'unknown'
                flash(f"Invalid {field}: {err['msg']}", "danger")
            return render_template("generate.html", **form_data, error=True)

        # Validate description is not empty
        if not data.text.strip():
            flash("Please provide a description for your image.", "warning")
            return render_template("generate.html", **form_data, error=True)

        brushstrokes_needed = token_cost(data.quality)
        current_balance = user.total_brushstrokes()

        if current_balance < brushstrokes_needed:
            flash(
                f"Insufficient brushstrokes! You need {brushstrokes_needed} but only have {current_balance}. "
                f'<a href="{url_for("dashboard")}" class="alert-link">Purchase more brushstrokes</a>.',
                "warning"
            )
            return render_template("generate.html", **form_data, error=True)

        # Handle uploaded reference images (max 3)
        reference_paths = []
        uploaded_files = request.files.getlist("reference_images")
        try:
            for file in uploaded_files[:3]:
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    if not filename:
                        continue
                    # Validate file extension
                    allowed_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
                    if not any(filename.lower().endswith(ext) for ext in allowed_extensions):
                        flash(f"Invalid file type for '{filename}'. Allowed: PNG, JPG, JPEG, WEBP, GIF", "warning")
                        continue
                    save_path = GENERATED_DIR / f"{uuid.uuid4()}_{filename}"
                    file.save(save_path)
                    reference_paths.append(save_path)
        except Exception as e:
            flash(f"Error uploading reference images: {str(e)}", "warning")
            # Continue without reference images

        # Choose generator type
        gen_type = form_data["gen_type"]
        if gen_type == "scene":
            gen = SceneImageGenerator()
        elif gen_type == "creature":
            gen = CreatureImageGenerator()
        elif gen_type == "item":
            gen = ItemImageGenerator()
        else:
            gen = CharacterImageGenerator()

        # Generate the image
        description = None
        image_path = None
        generation = None

        try:
            # Step 1: Generate description from text
            try:
                description = gen.get_description(text=data.text, prompt=data.prompt)
            except Exception as e:
                flash(f"Failed to generate image description: {str(e)}", "danger")
                return render_template("generate.html", **form_data, error=True)

            # Step 2: Generate the image
            output_path = GENERATED_DIR / f"generated_{uuid.uuid4()}.png"
            try:
                image_path = gen.generate_image(
                    description=description,
                    savepath=output_path,
                    reference_images=reference_paths,
                    image_size=data.size,
                    quality=data.quality,
                )
            except Exception as e:
                error_msg = str(e)
                # Provide more helpful error messages for common failures
                if "rate_limit" in error_msg.lower():
                    flash("OpenAI rate limit reached. Please wait a moment and try again.", "warning")
                elif "insufficient_quota" in error_msg.lower():
                    flash("OpenAI API quota exceeded. Please contact support.", "danger")
                elif "invalid_api_key" in error_msg.lower():
                    flash("API configuration error. Please contact support.", "danger")
                else:
                    flash(f"Failed to generate image: {error_msg}", "danger")
                return render_template("generate.html", **form_data, error=True)

            # Step 3: Create generation record
            generation = Generation(
                user=user,
                generation_type=gen_type,
                quality=data.quality,
                user_text=data.text,
                user_prompt=data.prompt,
                refined_description=description,
                image_size=data.size,
                image_url=f"/static/generated/{image_path.name}",
                image_filename=image_path.name,
                brushstrokes_used=brushstrokes_needed,
                status="completed",
                source="web",
                completed_at=datetime.now(timezone.utc),
            )
            generation.save()

            # Step 4: Record usage (deduct brushstrokes)
            try:
                success = record_generation(user, brushstrokes_needed, str(generation.id))
                if not success:
                    # This shouldn't happen as we already checked balance, but handle it anyway
                    flash("Warning: Image generated but brushstrokes may not have been deducted. Please check your balance.", "warning")
            except Exception as e:
                flash(f"Warning: Image generated but failed to record usage: {str(e)}", "warning")

            # Success! Show the generated image
            flash(f"Image generated successfully! Used {brushstrokes_needed} brushstrokes.", "success")
            return render_template(
                "generate.html",
                generated_image=url_for("static", filename=f"generated/{image_path.name}"),
                quality=data.quality,
                description=description,
                text=data.text,
                prompt=data.prompt,
                gen_type=gen_type,
            )

        except Exception as e:
            # Catch-all for unexpected errors
            flash(f"Unexpected error: {str(e)}", "danger")

            # Create failed generation record if not already created
            if not generation:
                generation = Generation(
                    user=user,
                    generation_type=gen_type,
                    quality=data.quality,
                    user_text=data.text,
                    user_prompt=data.prompt,
                    image_size=data.size,
                    brushstrokes_used=0,
                    status="failed",
                    error_message=str(e),
                    source="web",
                )
                generation.save()

            return render_template("generate.html", **form_data, error=True)

        finally:
            # Clean up reference images after generation (success or failure)
            for ref_path in reference_paths:
                try:
                    if ref_path.exists():
                        ref_path.unlink()
                except Exception:
                    pass  # Ignore cleanup errors

    # GET request - show empty form
    return render_template("generate.html", gen_type="character")


# ---------------------------------------------------------
# Mount FastAPI app for API routes
# ---------------------------------------------------------
try:
    from api_routes import api as fastapi_app
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    from fastapi.middleware.wsgi import WSGIMiddleware

    # Mount FastAPI app at /api
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
        "/api": WSGIMiddleware(fastapi_app)
    })
except Exception as e:
    print(f"Warning: Could not mount FastAPI app: {e}")


# ---------------------------------------------------------
# Run
# ---------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(5000), debug=True)
