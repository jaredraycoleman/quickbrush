import json
from os import environ as env
from urllib.parse import quote_plus, urlencode

from flask import Flask, render_template, redirect, session, url_for, request
from dotenv import find_dotenv, load_dotenv
from auth import oauth, login_required
from stripe_utils import start_subscription, create_portal_session, get_or_create_customer, record_usage
from maker import token_cost

# Load environment variables
ENV_FILE = find_dotenv()
if ENV_FILE:
    load_dotenv(ENV_FILE)

app = Flask(__name__)
app.secret_key = env.get("APP_SECRET_KEY", "replace-with-random-secret")

# Initialize Auth0 (via auth.py)
oauth.init_app(app)

@app.route("/")
def home():
    return render_template("login.html")

@app.route("/login")
def login():
    return oauth.auth0.authorize_redirect(
        redirect_uri=url_for("callback", _external=True)
    )

@app.route("/callback")
def callback():
    token = oauth.auth0.authorize_access_token()
    session["user"] = token
    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(
        "https://" + env.get("AUTH0_DOMAIN")
        + "/v2/logout?"
        + urlencode(
            {
                "returnTo": url_for("home", _external=True),
                "client_id": env.get("AUTH0_CLIENT_ID"),
            },
            quote_via=quote_plus,
        )
    )

@app.route("/dashboard")
@login_required
def dashboard():
    user = session["user"]
    cust = get_or_create_customer(user)
    usage = 0 # get_current_usage(cust.id)  # your Stripe logic
    current_cost = 0.0 # calculate_cost(usage)  # pricing tier logic
    return render_template("dashboard.html", user=user, customer=cust, usage=usage, current_cost=current_cost)


@app.route("/subscribe")
@login_required
def subscribe():
    user = session["user"]
    url = start_subscription(user)
    if url is None:
        return "Error creating subscription session", 500
    return redirect(url)

@app.route("/portal")
@login_required
def portal():
    user = session["user"]
    url = create_portal_session(user)
    return redirect(url)

@app.post("/generate")
@login_required
def generate():
    """Simplified endpoint just to simulate usage."""
    user = session["user"]
    quality = request.form.get("quality", "medium")
    tokens_used = token_cost(quality)
    cust = get_or_create_customer(user)
    record_usage(cust.id, tokens_used)
    return f"Generated image ({quality}) — {tokens_used} tokens recorded!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(env.get("PORT", 5000)), debug=True)
