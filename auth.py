from functools import wraps
from flask import session, redirect, url_for, flash
from authlib.integrations.flask_client import OAuth
from os import environ as env

oauth = OAuth()

# Register the Auth0 provider immediately on import
oauth.register(
    "auth0",
    client_id=env.get("AUTH0_CLIENT_ID"),
    client_secret=env.get("AUTH0_CLIENT_SECRET"),
    client_kwargs={
        "scope": "openid profile email",
    },
    server_metadata_url=f'https://{env.get("AUTH0_DOMAIN")}/.well-known/openid-configuration'
)

def login_required(f):
    """Require user to be logged in."""
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask import request
        if "user" not in session:
            # Save the current URL to redirect back after login
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    """Require user to be an admin."""
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask import request
        if "user" not in session:
            return redirect(url_for("login", next=request.url))

        # Import here to avoid circular dependency
        from models import get_or_create_user

        # Get or create user (this handles new users)
        userinfo = session["user"].get("userinfo", {})
        auth0_sub = userinfo.get("sub")
        email = userinfo.get("email")
        name = userinfo.get("name")
        picture = userinfo.get("picture")

        if not auth0_sub or not email:
            flash("Invalid session. Please log in again.", "danger")
            return redirect(url_for("login"))

        user = get_or_create_user(auth0_sub, email, name, picture)

        if not user.is_admin:
            flash("You need admin privileges to access this page.", "danger")
            return redirect(url_for("home"))

        return f(*args, **kwargs)
    return decorated
