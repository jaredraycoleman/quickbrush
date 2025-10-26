from typing import Optional
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
    jsonify,
)
from dotenv import find_dotenv, load_dotenv
import logging
import sys

from config import Config
from auth import oauth, login_required, admin_required, invite_required
from database import init_db
from models import get_or_create_user, User, get_user_by_auth0_sub, InvitationCode
from maker import QUALITY, IMAGE_SIZE
from stripe_utils import (
    create_portal_session,
    create_pack_checkout,
    create_subscription_checkout,
    handle_checkout_completed,
    check_and_renew_subscription,
    get_subscription_info,
)
from api_key_service import get_user_api_keys, create_api_key, revoke_api_key
from account_service import delete_user_account, get_account_deletion_summary
from image_service import get_user_generations, get_generation_by_id, get_remaining_image_slots
from generation_service import generate_image as generate_image_shared
from flask import send_file
from io import BytesIO
import tempfile


# ---------------------------------------------------------
# Configure logging to stdout for Kubernetes
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------
ENV_FILE = find_dotenv()
if ENV_FILE:
    load_dotenv(ENV_FILE)

app = Flask(__name__)
app.secret_key = Config.APP_SECRET_KEY

# Configure session for better OAuth compatibility
app.config['SESSION_COOKIE_SECURE'] = Config.FLASK_ENV == "production"  # HTTPS only in production
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent XSS
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection while allowing OAuth redirects
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

# Initialize MongoDB (fails gracefully if not configured)
db_connected = init_db()
if not db_connected:
    print("=" * 80)
    print("⚠️  WARNING: MongoDB is not connected!")
    print("=" * 80)
    print("To fix this:")
    print("1. Configure MongoDB Atlas IP whitelist (see instructions below)")
    print("2. Set MONGODB_URI secret in Kubernetes")
    print("")
    print("The application will start but database features will be unavailable.")
    print("=" * 80)

# Initialize Auth0 (via auth.py)
oauth.init_app(app)

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------

def get_current_user() -> Optional[User]:
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

    # Check if subscription needs renewal
    check_and_renew_subscription(user)

    # Auto-grant access if invite codes are disabled globally
    # This ensures any logged-in user gets access when invite codes are disabled
    if not user.is_admin and not user.has_valid_invite:
        from models import AppSettings
        settings = AppSettings.get_settings()

        if not settings.invite_codes_enabled:
            user.has_valid_invite = True
            user.save()

    return user

# ---------------------------------------------------------
# Template Context Processor
# ---------------------------------------------------------

@app.context_processor
def inject_current_user():
    """Make current_user available in all templates."""
    return dict(current_user=get_current_user() if "user" in session else None)

# ---------------------------------------------------------
# Routes
# ---------------------------------------------------------

@app.route("/")
def home():
    """Homepage - shows the About page for everyone."""
    current_user = None
    if "user" in session:
        current_user = get_current_user()

    return render_template(
        "about.html",
        current_user=current_user,
        invitation_form_submitted=False
    )

@app.route("/login")
def login():
    # Store the next URL in session to redirect after authentication
    next_url = request.args.get("next")
    if next_url:
        session["next_url"] = next_url

    return oauth.auth0.authorize_redirect( # type: ignore
        redirect_uri=url_for("callback", _external=True, _scheme="https" if Config.FLASK_ENV == "production" else "http")
    )

@app.route("/callback")
def callback():
    try:
        token = oauth.auth0.authorize_access_token() # type: ignore
        session["user"] = token

        # Get the next URL from session (if any)
        next_url = session.pop("next_url", None)

        # Validate next_url to prevent open redirect vulnerability
        if next_url:
            from urllib.parse import urlparse
            # Only allow relative URLs or same-host URLs
            parsed = urlparse(next_url)
            if not parsed.netloc or parsed.netloc == request.host:
                return redirect(next_url)

        # Default: redirect to home (About page) after login
        # Users with invites can navigate to dashboard from there
        return redirect(url_for("home"))
    except Exception as e:
        # Log the error for debugging
        import traceback
        print(f"OAuth callback error: {e}")
        traceback.print_exc()

        # Clear any existing session data
        session.clear()

        # Provide user-friendly error message
        flash(
            "Authentication failed. This can happen if you took too long to log in or used the back button. "
            "Please try logging in again.",
            "warning"
        )
        return redirect(url_for("home"))

@app.route("/privacy")
def privacy():
    """Privacy policy page."""
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    """Terms and conditions page."""
    return render_template("terms.html")


@app.route("/support")
def support():
    """Support page."""
    return render_template("support.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(
        "https://" + Config.AUTH0_DOMAIN
        + "/v2/logout?"
        + urlencode(
            {
                "returnTo": url_for("home", _external=True, _scheme="https" if Config.FLASK_ENV == "production" else "http"),
                "client_id": Config.AUTH0_CLIENT_ID,
            },
            quote_via=quote_plus,
        )
    )

@app.route("/dashboard")
@login_required
@invite_required
def dashboard():
    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("login"))

    # Get subscription info from Stripe (single source of truth)
    subscription_info_tuple = get_subscription_info(user)
    subscription_info = None
    monthly_allowance = 0

    if subscription_info_tuple and subscription_info_tuple[0]:
        sub_dict, monthly_allowance = subscription_info_tuple
        allowance_used = user.subscription.allowance_used_this_period if user.subscription else 0 # type: ignore
        if not sub_dict:
            flash("Error retrieving subscription information", "danger")
            return redirect(url_for("login"))
        subscription_info = {
            "tier": sub_dict["tier"],
            "status": sub_dict["status"],
            "monthly_allowance": monthly_allowance,
            "allowance_used": allowance_used,
            "allowance_remaining": max(0, monthly_allowance - allowance_used), # type: ignore
            "current_period_end": sub_dict["current_period_end"],
            "cancel_at_period_end": sub_dict["cancel_at_period_end"],
            "scheduled_change": sub_dict.get("scheduled_change"),  # Include scheduled plan changes
        }

    # Get API keys
    api_keys = get_user_api_keys(user, include_inactive=False)

    # Get Stripe price IDs for both packs and subscriptions
    try:
        stripe_prices = {
            # Packs
            "pack_250": Config.STRIPE_PRICE_PACK_250,
            "pack_500": Config.STRIPE_PRICE_PACK_500,
            "pack_1000": Config.STRIPE_PRICE_PACK_1000,
            "pack_2500": Config.STRIPE_PRICE_PACK_2500,
            # Subscriptions
            "basic": Config.STRIPE_PRICE_BASIC,
            "pro": Config.STRIPE_PRICE_PRO,
            "premium": Config.STRIPE_PRICE_PREMIUM,
            "ultimate": Config.STRIPE_PRICE_ULTIMATE,
        }
    except Exception as e:
        # If Stripe prices aren't configured yet, use placeholders
        print(f"Warning: Stripe prices not configured: {e}")
        stripe_prices = {
            "pack_250": "CONFIGURE_IN_ENV",
            "pack_500": "CONFIGURE_IN_ENV",
            "pack_1000": "CONFIGURE_IN_ENV",
            "pack_2500": "CONFIGURE_IN_ENV",
            "basic": "CONFIGURE_IN_ENV",
            "pro": "CONFIGURE_IN_ENV",
            "premium": "CONFIGURE_IN_ENV",
            "ultimate": "CONFIGURE_IN_ENV",
        }

    return render_template(
        "dashboard.html",
        user=user,
        subscription=subscription_info,
        total_brushstrokes=user.total_brushstrokes(monthly_allowance),
        purchased_brushstrokes=user.purchased_brushstrokes,
        api_keys=api_keys,
        stripe_prices=stripe_prices,
        foundry_module_url=url_for(
            "static",
            filename="foundry-module/module.json",
            _external=True,
            _scheme="https" if Config.FLASK_ENV == "production" else "http"
        )
    )


@app.route("/portal")
@login_required
def portal():
    """Redirect to Stripe Customer Portal for subscription management."""
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


@app.route("/subscribe")
@login_required
def subscribe():
    """Initiate subscription purchase."""
    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    price_id = request.args.get("price_id")
    if not price_id:
        flash("Missing price_id parameter", "danger")
        return redirect(url_for("dashboard"))

    # Check if user already has a subscription
    if user.subscription and user.subscription.stripe_subscription_id: # type: ignore
        flash("You already have an active subscription. Use the portal to manage it.", "warning")
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

    # Get newly created API key from session (if exists)
    new_api_key = session.pop("new_api_key", None)
    new_api_key_name = session.pop("new_api_key_name", None)

    return render_template(
        "api_keys.html",
        api_keys=keys,
        user=user,
        new_api_key=new_api_key,
        new_api_key_name=new_api_key_name
    )


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

        # Store the key temporarily in session to display in modal
        session["new_api_key"] = full_key
        session["new_api_key_name"] = name

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
    api_key = APIKey.objects(key_id=key_id, user=user).first() # type: ignore

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
# ACCOUNT MANAGEMENT ROUTES
# ---------------------------------------------------------

@app.route("/settings")
@login_required
def settings_page():
    """Account settings page."""
    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    # Get deletion summary
    deletion_summary = get_account_deletion_summary(user)

    return render_template(
        "settings.html",
        user=user,
        deletion_summary=deletion_summary
    )


@app.route("/account/delete", methods=["POST"])
@login_required
def delete_account():
    """Delete user account and all associated data."""
    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    # Verify confirmation
    confirmation = request.form.get("confirmation")
    if confirmation != "DELETE":
        flash("Please type 'DELETE' to confirm account deletion", "danger")
        return redirect(url_for("settings_page"))

    # Perform deletion
    success, message = delete_user_account(user)

    if success:
        # Clear session and redirect to home
        session.clear()
        flash("Your account has been permanently deleted.", "success")
        return redirect(url_for("home"))
    else:
        flash(f"Failed to delete account: {message}", "danger")
        return redirect(url_for("settings_page"))


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
@invite_required
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
            "image_name": request.form.get("image_name", ""),
            "quality": request.form.get("quality", "medium"),
            "aspect_ratio": request.form.get("aspect_ratio"),
            "gen_type": request.form.get("gen_type", "character"),
        }

        # Validate input data
        try:
            data = GenerateRequest(
                text=form_data["text"],
                prompt=form_data["prompt"],
                quality=form_data["quality"], # type: ignore
                size="1024x1024",  # Deprecated, will be determined by aspect_ratio
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

        # Validate image name is not empty
        if not form_data["image_name"].strip():
            flash("Please provide a name for your image.", "warning")
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
                    # Save to temp file
                    with tempfile.NamedTemporaryFile(delete=False, suffix=pathlib.Path(filename).suffix) as tmp:
                        file.save(tmp.name)
                        reference_paths.append(pathlib.Path(tmp.name))
        except Exception as e:
            flash(f"Error uploading reference images: {str(e)}", "warning")
            # Continue without reference images

        gen_type = form_data["gen_type"]

        try:
            # Use shared generation service
            result = generate_image_shared(
                user=user,
                text=data.text,
                generation_type=gen_type,
                quality=data.quality,
                image_name=form_data["image_name"].strip(),
                aspect_ratio=form_data["aspect_ratio"],
                prompt=data.prompt,
                reference_image_paths=reference_paths,
                source="web"
            )

            if result.success:
                # Success!
                flash(
                    f"Image generated successfully! Used {result.brushstrokes_used} brushstrokes. "
                    f"({result.remaining_image_slots} image slots remaining)",
                    "success"
                )
                return render_template(
                    "generate.html",
                    generated_image_id=result.generation_id,
                    quality=data.quality,
                    aspect_ratio=form_data["aspect_ratio"],
                    description=result.refined_description,
                    text=data.text,
                    prompt=data.prompt,
                    image_name=form_data["image_name"],
                    gen_type=gen_type,
                )
            else:
                # Generation failed
                flash(result.error_message or "Unknown error", "danger")
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
    return render_template("generate.html", gen_type="character", quality="medium")


# ---------------------------------------------------------
# IMAGE LIBRARY AND SERVING ROUTES
# ---------------------------------------------------------

@app.route("/image/<generation_id>")
@login_required
def serve_image(generation_id: str):
    """Serve an image from MongoDB."""
    user = get_current_user()
    if not user:
        return "Unauthorized", 401

    generation = get_generation_by_id(generation_id, user)
    if not generation or not generation.image_data:
        return "Image not found", 404

    # Use generated name if available, otherwise fall back to generation_id
    import re
    if generation.image_name:
        filename = str(generation.image_name)
        # Sanitize filename (remove invalid characters)
        filename = re.sub(r'[^\w\s-]', '', filename).strip()
        filename = re.sub(r'[-\s]+', '-', filename)
    else:
        filename = f"generated_{generation_id}"
    filename = f"{filename}.webp"

    # Serve the WebP image
    return send_file(
        BytesIO(generation.image_data), # type: ignore
        mimetype="image/webp",
        as_attachment=False,
        download_name=filename
    )


@app.route("/library")
@login_required
@invite_required
def library():
    """View user's generation library."""
    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    # Get user's generations
    generations = get_user_generations(user, limit=100, include_without_images=False)

    # Get remaining image slots
    remaining_slots = get_remaining_image_slots(user)

    return render_template(
        "library.html",
        user=user,
        generations=generations,
        remaining_slots=remaining_slots,
        max_images=100
    )


# ---------------------------------------------------------
# ABOUT PAGE
# ---------------------------------------------------------

@app.route("/showcase")
def showcase():
    """Showcase page - accessible to everyone."""
    return render_template("showcase.html")


@app.route("/redeem-invite", methods=["POST"])
@login_required
def redeem_invite():
    """Redeem an invitation code."""
    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("index"))

    code = request.form.get("invitation_code", "").strip()
    if not code:
        flash("Please enter an invitation code.", "warning")
        return redirect(url_for("index"))

    # Import here to avoid circular dependency
    from admin_service import redeem_invitation_code

    success, message = redeem_invitation_code(code, user)
    if success:
        flash(message, "success")
        return redirect(url_for("dashboard"))
    else:
        flash(message, "danger")
        return redirect(url_for("index"))


# ---------------------------------------------------------
# ADMIN PANEL
# ---------------------------------------------------------

@app.route("/admin")
@login_required
@admin_required
def admin_panel():
    """Admin panel for user management."""
    from admin_service import search_users, get_invitation_codes, get_user_stats, get_app_settings
    from datetime import datetime, timezone

    # Get search query if any
    search_query = request.args.get("search", "").strip()

    # Search users
    users = search_users(search_query, limit=50)

    # Get invitation codes (unused only by default)
    invitation_codes = get_invitation_codes(include_used=False, limit=100)

    # Get statistics
    stats = get_user_stats()

    # Get app settings
    app_settings = get_app_settings()

    return render_template(
        "admin.html",
        users=users,
        invitation_codes=invitation_codes,
        stats=stats,
        app_settings=app_settings,
        search_query=search_query,
        now=datetime.now(timezone.utc)
    )


@app.route("/admin/user/<user_id>")
@login_required
@admin_required
def admin_user_details(user_id: str):
    """Get detailed user information (AJAX endpoint)."""
    from admin_service import get_user_details

    details = get_user_details(user_id)
    if not details:
        return {"error": "User not found"}, 404

    # Convert user object to dict for JSON serialization
    user = details["user"]
    user_dict = {
        "_id": str(user.id),
        "email": user.email,
        "name": user.name,
        "auth0_sub": user.auth0_sub,
        "is_admin": user.is_admin,
        "has_access": user.has_valid_invite,
        "purchased_brushstrokes": user.purchased_brushstrokes,
        "stripe_customer_id": user.stripe_customer_id,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }

    # Convert transactions to dicts
    transactions = []
    for txn in details.get("recent_transactions", []):
        transactions.append({
            "transaction_type": txn.transaction_type,
            "amount": txn.amount,
            "created_at": txn.created_at.isoformat() if txn.created_at else None,
        })

    return {
        "user": user_dict,
        "recent_transactions": transactions,
        "invitation_info": details.get("invitation_info"),
    }


@app.route("/admin/gift-tokens", methods=["POST"])
@login_required
@admin_required
def admin_gift_tokens():
    """Gift tokens to a user (AJAX endpoint)."""
    from admin_service import gift_tokens

    admin_user = get_current_user()
    if not admin_user:
        return {"error": "Admin user not found"}, 401

    data = request.get_json()
    user_id = data.get("user_id")
    amount = data.get("amount")
    description = data.get("description", "")

    if not user_id or not amount:
        return {"error": "Missing required fields"}, 400

    try:
        amount = int(amount)
        if amount <= 0:
            return {"error": "Amount must be positive"}, 400
    except ValueError:
        return {"error": "Invalid amount"}, 400

    success = gift_tokens(admin_user, user_id, amount, description)
    if success:
        return {"success": True}
    else:
        return {"error": "Failed to gift tokens"}, 500


@app.route("/admin/toggle-admin", methods=["POST"])
@login_required
@admin_required
def admin_toggle_admin():
    """Toggle admin status for a user (AJAX endpoint)."""
    from admin_service import toggle_admin_status

    data = request.get_json()
    user_id = data.get("user_id")

    if not user_id:
        return {"error": "Missing user_id"}, 400

    new_status = toggle_admin_status(user_id)
    if new_status is not None:
        return {"success": True, "is_admin": new_status}
    else:
        return {"error": "User not found"}, 404


@app.route("/admin/grant-access", methods=["POST"])
@login_required
@admin_required
def admin_grant_access():
    """Manually grant invite access to a user (AJAX endpoint)."""
    from admin_service import grant_invite_access

    admin_user = get_current_user()
    if not admin_user:
        return {"error": "Admin user not found"}, 401

    data = request.get_json()
    user_id = data.get("user_id")

    if not user_id:
        return {"error": "Missing user_id"}, 400

    success = grant_invite_access(user_id, admin_user)
    if success:
        return {"success": True}
    else:
        return {"error": "Failed to grant access"}, 500


@app.route("/admin/create-invite", methods=["POST"])
@login_required
@admin_required
def admin_create_invite():
    """Create a new invitation code."""
    from admin_service import create_invitation_code
    from datetime import datetime, timezone

    admin_user = get_current_user()
    if not admin_user:
        flash("Error loading user data", "danger")
        return redirect(url_for("admin_panel"))

    description = request.form.get("description", "").strip()
    expires_at_str = request.form.get("expires_at", "").strip()

    expires_at = None
    if expires_at_str:
        try:
            # Parse datetime-local format (YYYY-MM-DDTHH:MM)
            expires_at = datetime.fromisoformat(expires_at_str).replace(tzinfo=timezone.utc)
        except ValueError:
            flash("Invalid expiration date format", "danger")
            return redirect(url_for("admin_panel"))

    invitation = create_invitation_code(admin_user, description, expires_at)
    if invitation:
        flash(f"Invitation code created: {invitation.code}", "success")
    else:
        flash("Failed to create invitation code", "danger")

    return redirect(url_for("admin_panel"))


@app.route("/admin/delete-invite/<code_id>", methods=["POST"])
@login_required
@admin_required
def admin_delete_invite(code_id: str):
    """Delete an invitation code."""
    from admin_service import delete_invitation_code

    success = delete_invitation_code(code_id)
    if success:
        flash("Invitation code deleted", "success")
    else:
        flash("Failed to delete invitation code", "danger")

    return redirect(url_for("admin_panel"))


@app.route("/admin/toggle-invite-codes", methods=["POST"])
@login_required
@admin_required
def admin_toggle_invite_codes():
    """Toggle the global invite codes requirement."""
    from admin_service import toggle_invite_codes

    admin_user = get_current_user()
    if not admin_user:
        return {"error": "Admin user not found"}, 401

    try:
        new_value = toggle_invite_codes(admin_user)
        return {"success": True, "invite_codes_enabled": new_value}
    except Exception as e:
        return {"error": str(e)}, 500


@app.route("/admin/bulk-revoke-access", methods=["POST"])
@login_required
@admin_required
def admin_bulk_revoke_access():
    """Bulk revoke access for users with no tokens and no subscription."""
    from admin_service import bulk_revoke_access

    try:
        count = bulk_revoke_access()
        return {"success": True, "count": count}
    except Exception as e:
        return {"error": str(e)}, 500


@app.route("/admin/toggle-access", methods=["POST"])
@login_required
@admin_required
def admin_toggle_access():
    """Toggle access for a user (AJAX endpoint)."""
    from admin_service import toggle_access

    data = request.get_json()
    user_id = data.get("user_id")

    if not user_id:
        return {"error": "Missing user_id"}, 400

    new_status = toggle_access(user_id)
    if new_status is not None:
        return {"success": True, "has_access": new_status}
    else:
        return {"error": "User not found"}, 404


@app.route("/admin/remove-tokens", methods=["POST"])
@login_required
@admin_required
def admin_remove_tokens():
    """Remove tokens from a user (AJAX endpoint)."""
    from admin_service import remove_tokens

    admin_user = get_current_user()
    if not admin_user:
        return {"error": "Admin user not found"}, 401

    data = request.get_json()
    user_id = data.get("user_id")
    amount = data.get("amount")
    description = data.get("description", "")

    if not user_id or not amount:
        return {"error": "Missing required fields"}, 400

    try:
        amount = int(amount)
        if amount <= 0:
            return {"error": "Amount must be positive"}, 400
    except ValueError:
        return {"error": "Invalid amount"}, 400

    success = remove_tokens(admin_user, user_id, amount, description)
    if success:
        return {"success": True}
    else:
        return {"error": "Failed to remove tokens"}, 500


@app.route("/admin/delete-user", methods=["POST"])
@login_required
@admin_required
def admin_delete_user():
    """Delete a user account (AJAX endpoint)."""
    from admin_service import delete_user_account

    admin_user = get_current_user()
    if not admin_user:
        return {"error": "Admin user not found"}, 401

    data = request.get_json()
    user_id = data.get("user_id")

    if not user_id:
        return {"error": "Missing user_id"}, 400

    success = delete_user_account(admin_user, user_id)
    if success:
        return {"success": True}
    else:
        return {"error": "Failed to delete user. Cannot delete admin accounts."}, 500


# ---------------------------------------------------------
# OAUTH PROVIDER ROUTES
# ---------------------------------------------------------

@app.route("/oauth/authorize", methods=["GET", "POST"])
@login_required
def oauth_authorize():
    """OAuth authorization endpoint."""
    from oauth_service import get_oauth_application_by_client_id, create_authorization_code, parse_scope_string, validate_scopes

    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("login"))

    # Get OAuth parameters
    client_id = request.args.get("client_id")
    redirect_uri = request.args.get("redirect_uri")
    response_type = request.args.get("response_type", "code")
    scope = request.args.get("scope", "read:user")
    state = request.args.get("state", "")
    code_challenge = request.args.get("code_challenge")
    code_challenge_method = request.args.get("code_challenge_method", "S256")

    # Validate required parameters
    if not client_id or not redirect_uri:
        return render_template(
            "oauth_error.html",
            error="invalid_request",
            error_description="Missing required parameters (client_id, redirect_uri)"
        ), 400

    # Get application
    app_obj = get_oauth_application_by_client_id(client_id)
    if not app_obj:
        return render_template(
            "oauth_error.html",
            error="invalid_client",
            error_description="Unknown client_id"
        ), 400

    # Validate redirect URI
    if not app_obj.is_redirect_uri_allowed(redirect_uri):
        return render_template(
            "oauth_error.html",
            error="invalid_request",
            error_description=f"Redirect URI not allowed: {redirect_uri}"
        ), 400

    # Validate response_type
    if response_type != "code":
        error_url = f"{redirect_uri}?error=unsupported_response_type&error_description=Only+code+is+supported&state={state}"
        return redirect(error_url)

    # Parse and validate scopes
    requested_scopes = parse_scope_string(scope)
    scopes_valid, invalid_scopes = validate_scopes(requested_scopes)
    if not scopes_valid:
        error_url = f"{redirect_uri}?error=invalid_scope&error_description=Invalid+scopes:+{'+'.join(invalid_scopes)}&state={state}"
        return redirect(error_url)

    # Check if user already approved this app with these scopes
    from models import OAuthAuthorization
    existing_auth = OAuthAuthorization.objects(user=user, application=app_obj, is_active=True).first()

    # If POST request, user is approving/denying
    if request.method == "POST":
        action = request.form.get("action")

        if action == "deny":
            # User denied authorization
            error_url = f"{redirect_uri}?error=access_denied&error_description=User+denied+authorization&state={state}"
            return redirect(error_url)

        elif action == "approve":
            # Create authorization code
            try:
                auth_code = create_authorization_code(
                    application=app_obj,
                    user=user,
                    redirect_uri=redirect_uri,
                    scopes=requested_scopes,
                    code_challenge=code_challenge,
                    code_challenge_method=code_challenge_method,
                )

                # Redirect back to application with code
                success_url = f"{redirect_uri}?code={auth_code.code}&state={state}"
                return redirect(success_url)

            except ValueError as e:
                error_url = f"{redirect_uri}?error=invalid_request&error_description={str(e)}&state={state}"
                return redirect(error_url)

    # GET request - show consent page
    from oauth_service import AVAILABLE_SCOPES
    scope_descriptions = {scope: AVAILABLE_SCOPES.get(scope, scope) for scope in requested_scopes}

    return render_template(
        "oauth_consent.html",
        application=app_obj,
        scopes=scope_descriptions,
        redirect_uri=redirect_uri,
        state=state,
        existing_auth=existing_auth
    )


@app.route("/oauth/token", methods=["POST"])
def oauth_token():
    """OAuth token endpoint."""
    try:
        logger.info("=== OAuth Token Request Started ===")
        logger.info(f"Content-Type: {request.content_type}")
        logger.info(f"Method: {request.method}")
        logger.info(f"Headers: {dict(request.headers)}")

        from oauth_service import exchange_authorization_code, refresh_access_token, verify_oauth_application

        # Get JSON data once (if present) using silent=True to avoid exceptions
        json_data = request.get_json(silent=True)

        # Log request data for debugging
        logger.info(f"Form data: {dict(request.form)}")
        logger.info(f"JSON data: {json_data}")

        # Get token request parameters (can be in body or as form data)
        grant_type = request.form.get("grant_type") or (json_data.get("grant_type") if json_data else None)

        logger.info(f"Grant type: {grant_type}")

        if not grant_type:
            return jsonify({
                "error": "invalid_request",
                "error_description": "Missing grant_type"
            }), 400

        # Authorization code grant
        if grant_type == "authorization_code":
            code = request.form.get("code") or (json_data.get("code") if json_data else None)
            client_id = request.form.get("client_id") or (json_data.get("client_id") if json_data else None)
            client_secret = request.form.get("client_secret") or (json_data.get("client_secret") if json_data else None)
            redirect_uri = request.form.get("redirect_uri") or (json_data.get("redirect_uri") if json_data else None)
            code_verifier = request.form.get("code_verifier") or (json_data.get("code_verifier") if json_data else None)

            logger.info(f"Authorization code exchange request:")
            logger.info(f"  - code: {code[:20]}..." if code else "  - code: None")
            logger.info(f"  - client_id: {client_id}")
            logger.info(f"  - redirect_uri: {redirect_uri}")
            logger.info(f"  - has_client_secret: {bool(client_secret)}")
            logger.info(f"  - has_code_verifier: {bool(code_verifier)}")

            if not all([code, client_id, client_secret, redirect_uri]):
                logger.warning("Missing required parameters for authorization code exchange")
                return jsonify({
                    "error": "invalid_request",
                    "error_description": "Missing required parameters"
                }), 400

            # Exchange code for token
            logger.info("Calling exchange_authorization_code...")
            token_data = exchange_authorization_code(
                code=code,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )

            if not token_data:
                logger.error("Token exchange failed - invalid or expired authorization code")
                return jsonify({
                    "error": "invalid_grant",
                    "error_description": "Invalid or expired authorization code"
                }), 400

            logger.info("Token exchange successful!")
            logger.info(f"Returning token data: {list(token_data.keys())}")
            return jsonify(token_data), 200

        # Refresh token grant
        elif grant_type == "refresh_token":
            refresh_token = request.form.get("refresh_token") or (json_data.get("refresh_token") if json_data else None)

            if not refresh_token:
                return jsonify({
                    "error": "invalid_request",
                    "error_description": "Missing refresh_token"
                }), 400

            token_data = refresh_access_token(refresh_token)

            if not token_data:
                return jsonify({
                    "error": "invalid_grant",
                    "error_description": "Invalid or expired refresh token"
                }), 400

            return jsonify(token_data), 200

        else:
            return jsonify({
                "error": "unsupported_grant_type",
                "error_description": f"Grant type '{grant_type}' is not supported"
            }), 400

    except Exception as e:
        # Log the error with full traceback
        import traceback
        logger.error("=== OAuth Token Endpoint Error ===")
        logger.error(f"Error: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")

        # Return JSON error response
        return jsonify({
            "error": "server_error",
            "error_description": f"Internal server error: {str(e)}"
        }), 500


@app.route("/oauth/revoke", methods=["POST"])
@login_required
def oauth_revoke():
    """Revoke an OAuth token."""
    from oauth_service import revoke_token

    json_data = request.get_json(silent=True)
    token = request.form.get("token") or (json_data.get("token") if json_data else None)

    if not token:
        return jsonify({"error": "invalid_request"}), 400

    revoke_token(token)

    # Always return success per OAuth 2.0 spec (don't leak token validity)
    return jsonify({"success": True}), 200


@app.route("/developer/apps")
@login_required
@admin_required
def developer_apps():
    """Developer dashboard for managing OAuth applications (admin only)."""
    from models import OAuthApplication

    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    # Get all OAuth applications (admin view - not user-specific)
    apps = list(OAuthApplication.objects())

    return render_template(
        "developer_apps.html",
        user=user,
        apps=apps
    )


@app.route("/developer/apps/create", methods=["GET", "POST"])
@login_required
@admin_required
def create_developer_app():
    """Create a new OAuth application."""
    from oauth_service import create_oauth_application

    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        homepage_url = request.form.get("homepage_url", "").strip()
        redirect_uris_raw = request.form.get("redirect_uris", "").strip()

        # Validate inputs
        if not name:
            flash("Application name is required", "danger")
            return render_template("create_oauth_app.html", user=user, form_data=request.form)

        if not redirect_uris_raw:
            flash("At least one redirect URI is required", "danger")
            return render_template("create_oauth_app.html", user=user, form_data=request.form)

        # Parse redirect URIs (one per line)
        redirect_uris = [uri.strip() for uri in redirect_uris_raw.split("\n") if uri.strip()]

        if not redirect_uris:
            flash("At least one redirect URI is required", "danger")
            return render_template("create_oauth_app.html", user=user, form_data=request.form)

        # Create application
        try:
            app_obj, client_secret = create_oauth_application(
                owner=user,
                name=name,
                redirect_uris=redirect_uris,
                description=description,
                homepage_url=homepage_url,
            )

            # Store client secret in session to show once
            session["new_oauth_app_secret"] = client_secret
            session["new_oauth_app_id"] = str(app_obj.id)

            flash(f"OAuth application '{name}' created successfully!", "success")
            return redirect(url_for("developer_app_details", app_id=str(app_obj.id)))

        except Exception as e:
            flash(f"Error creating application: {str(e)}", "danger")
            return render_template("create_oauth_app.html", user=user, form_data=request.form)

    # GET request
    return render_template("create_oauth_app.html", user=user)


@app.route("/developer/apps/<app_id>")
@login_required
@admin_required
def developer_app_details(app_id: str):
    """View OAuth application details (admin only)."""
    from models import OAuthApplication, OAuthAuthorization

    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    # Get application (admin can view any app)
    app_obj = OAuthApplication.objects(id=app_id).first()
    if not app_obj:
        flash("Application not found", "danger")
        return redirect(url_for("developer_apps"))

    # Get authorization count
    auth_count = OAuthAuthorization.objects(application=app_obj, is_active=True).count()

    # Check for newly created app secret
    new_secret = None
    if session.get("new_oauth_app_id") == app_id:
        new_secret = session.pop("new_oauth_app_secret", None)
        session.pop("new_oauth_app_id", None)

    return render_template(
        "oauth_app_details.html",
        user=user,
        app=app_obj,
        auth_count=auth_count,
        new_secret=new_secret
    )


@app.route("/developer/apps/<app_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_developer_app(app_id: str):
    """Delete an OAuth application (admin only)."""
    from oauth_service import delete_oauth_application
    from models import OAuthApplication

    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    # Get application (admin can delete any app)
    app_obj = OAuthApplication.objects(id=app_id).first()
    if not app_obj:
        flash("Application not found", "danger")
        return redirect(url_for("developer_apps"))

    # Verify confirmation
    confirmation = request.form.get("confirmation")
    if confirmation != app_obj.name:
        flash(f"Please type '{app_obj.name}' to confirm deletion", "danger")
        return redirect(url_for("developer_app_details", app_id=app_id))

    # Delete application
    try:
        app_name = app_obj.name
        delete_oauth_application(app_obj)
        flash(f"Application '{app_name}' deleted successfully", "success")
        return redirect(url_for("developer_apps"))
    except Exception as e:
        flash(f"Error deleting application: {str(e)}", "danger")
        return redirect(url_for("developer_app_details", app_id=app_id))


@app.route("/developer/apps/<app_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_developer_app(app_id: str):
    """Edit an OAuth application (admin only)."""
    from oauth_service import update_oauth_application
    from models import OAuthApplication

    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    # Get application
    app_obj = OAuthApplication.objects(id=app_id).first()
    if not app_obj:
        flash("Application not found", "danger")
        return redirect(url_for("developer_apps"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        homepage_url = request.form.get("homepage_url", "").strip()
        redirect_uris_raw = request.form.get("redirect_uris", "").strip()

        # Validate inputs
        if not name:
            flash("Application name is required", "danger")
            return render_template("edit_oauth_app.html", user=user, app=app_obj, form_data=request.form)

        if not redirect_uris_raw:
            flash("At least one redirect URI is required", "danger")
            return render_template("edit_oauth_app.html", user=user, app=app_obj, form_data=request.form)

        # Parse redirect URIs (one per line)
        redirect_uris = [uri.strip() for uri in redirect_uris_raw.split("\n") if uri.strip()]

        if not redirect_uris:
            flash("At least one redirect URI is required", "danger")
            return render_template("edit_oauth_app.html", user=user, app=app_obj, form_data=request.form)

        # Update application
        try:
            update_oauth_application(
                app=app_obj,
                name=name,
                description=description,
                homepage_url=homepage_url,
                redirect_uris=redirect_uris,
            )

            flash(f"OAuth application '{name}' updated successfully!", "success")
            return redirect(url_for("developer_app_details", app_id=app_id))

        except Exception as e:
            flash(f"Error updating application: {str(e)}", "danger")
            return render_template("edit_oauth_app.html", user=user, app=app_obj, form_data=request.form)

    # GET request - show edit form
    return render_template("edit_oauth_app.html", user=user, app=app_obj)


@app.route("/settings/authorized-apps")
@login_required
def authorized_apps():
    """View and manage authorized OAuth applications."""
    from oauth_service import get_user_authorizations

    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    authorizations = get_user_authorizations(user)

    return render_template(
        "authorized_apps.html",
        user=user,
        authorizations=authorizations
    )


@app.route("/settings/authorized-apps/<auth_id>/revoke", methods=["POST"])
@login_required
def revoke_app_authorization(auth_id: str):
    """Revoke authorization for an OAuth application."""
    from models import OAuthAuthorization

    user = get_current_user()
    if not user:
        flash("Error loading user data", "danger")
        return redirect(url_for("dashboard"))

    # Get authorization
    auth = OAuthAuthorization.objects(id=auth_id, user=user).first()
    if not auth:
        flash("Authorization not found", "danger")
        return redirect(url_for("authorized_apps"))

    # Revoke authorization
    try:
        app_name = auth.application.name if auth.application else "Unknown"
        auth.revoke()
        flash(f"Access revoked for '{app_name}'", "success")
    except Exception as e:
        flash(f"Error revoking access: {str(e)}", "danger")

    return redirect(url_for("authorized_apps"))


# ---------------------------------------------------------
# Mount FastAPI app for API routes
# ---------------------------------------------------------
try:
    from api_routes import api as fastapi_app
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    from a2wsgi import ASGIMiddleware

    # Mount FastAPI app at /api using a2wsgi to convert ASGI to WSGI
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
        "/api": ASGIMiddleware(fastapi_app) # type: ignore
    })
except Exception as e:
    print(f"Warning: Could not mount FastAPI app: {e}")


# ---------------------------------------------------------
# Run
# ---------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(5000), debug=True)
