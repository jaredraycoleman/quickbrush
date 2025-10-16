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
    get_or_create_customer,
    record_usage,
    get_credits_balance,
    get_credit_grants,
    get_auto_recharge_settings,
    set_auto_recharge_settings,
    create_checkout_session,
    handle_checkout_webhook,
)


# ---------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------
ENV_FILE = find_dotenv()
if ENV_FILE:
    load_dotenv(ENV_FILE)

app = Flask(__name__)
app.secret_key = Config.APP_SECRET_KEY

# Initialize Auth0 (via auth.py)
oauth.init_app(app)

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
    user = session["user"]
    cust = get_or_create_customer(user)

    # Get credits balance and auto-recharge settings
    credits_balance = get_credits_balance(cust.id)
    auto_recharge_settings = get_auto_recharge_settings(cust.id)
    credit_grants = get_credit_grants(cust.id)

    return render_template(
        "dashboard.html",
        user=user,
        customer=cust,
        credits_balance=credits_balance,
        auto_recharge_settings=auto_recharge_settings,
        credit_grants=credit_grants,
    )


@app.route("/portal")
@login_required
def portal():
    user = session["user"]
    url = create_portal_session(user)
    return redirect(url)


# ---------------------------------------------------------
# CREDITS & AUTO-RECHARGE ROUTES
# ---------------------------------------------------------

@app.route("/buy-credits")
@login_required
def buy_credits():
    """Initiate a checkout session to purchase credits."""
    user = session["user"]
    cust = get_or_create_customer(user)

    # Get the amount from query params (default to $5)
    amount_cents = int(request.args.get("amount", 500))

    # Validate amount
    if amount_cents not in Config.CREDIT_PACKAGES:
        flash(f"Invalid credit package amount: ${amount_cents/100:.2f}", "danger")
        return redirect(url_for("dashboard"))

    # Create checkout session
    success_url = url_for("checkout_success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}"
    cancel_url = url_for("dashboard", _external=True)

    checkout_url = create_checkout_session(
        customer_id=cust.id,
        amount_cents=amount_cents,
        success_url=success_url,
        cancel_url=cancel_url,
    )

    if checkout_url:
        return redirect(checkout_url)
    else:
        flash("Failed to create checkout session. Please try again.", "danger")
        return redirect(url_for("dashboard"))


@app.route("/checkout-success")
@login_required
def checkout_success():
    """Handle successful checkout and add credits to the user's account."""
    session_id = request.args.get("session_id")
    if not session_id:
        flash("Invalid checkout session.", "danger")
        return redirect(url_for("dashboard"))

    # Handle the webhook to add credits
    success = handle_checkout_webhook(session_id)
    if success:
        flash("Credits added successfully! Thank you for your purchase.", "success")
    else:
        flash("There was an issue adding your credits. Please contact support.", "warning")

    return redirect(url_for("dashboard"))


@app.route("/settings/auto-recharge", methods=["GET", "POST"])
@login_required
def auto_recharge_settings():
    """View and update auto-recharge settings."""
    user = session["user"]
    cust = get_or_create_customer(user)

    if request.method == "POST":
        # Update settings
        enabled = request.form.get("enabled") == "on"
        amount_str = request.form.get("amount", str(Config.DEFAULT_AUTO_RECHARGE_AMOUNT))

        try:
            amount = int(amount_str)
            success = set_auto_recharge_settings(cust.id, enabled, amount)
            if success:
                flash("Auto-recharge settings updated successfully!", "success")
            else:
                flash("Failed to update auto-recharge settings.", "danger")
        except ValueError:
            flash("Invalid recharge amount.", "danger")

        return redirect(url_for("dashboard"))

    # GET request - show current settings
    settings = get_auto_recharge_settings(cust.id)
    return render_template(
        "auto_recharge_settings.html",
        settings=settings,
        credit_packages=Config.CREDIT_PACKAGES,
    )

# ---------------------------------------------------------
# NEW: Image Generation Page
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

        # Get customer and check credits
        user = session["user"]
        try:
            cust = get_or_create_customer(user)
        except Exception as e:
            flash(f"Failed to retrieve customer information: {str(e)}", "danger")
            return render_template("generate.html", **form_data, error=True)

        brushstrokes_needed = token_cost(data.quality)
        current_balance = get_credits_balance(cust.id)

        if current_balance < brushstrokes_needed:
            flash(
                f"Insufficient credits! You need {brushstrokes_needed} brushstrokes but only have {current_balance}. "
                f'<a href="{url_for("dashboard")}" class="alert-link">Purchase more credits</a>.',
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

            # Step 3: Record usage (deduct credits)
            try:
                success = record_usage(cust.id, brushstrokes_needed)
                if not success:
                    # This shouldn't happen as we already checked balance, but handle it anyway
                    flash("Warning: Image generated but credits may not have been deducted. Please check your balance.", "warning")
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
# Run
# ---------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(5000), debug=True)
