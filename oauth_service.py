"""
OAuth 2.0 service for managing applications, authorization codes, and tokens.

This module implements the OAuth 2.0 authorization server functionality,
allowing third-party applications to authenticate users and access the API.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from models import (
    User,
    OAuthApplication,
    OAuthAuthorizationCode,
    OAuthToken,
    OAuthAuthorization,
)


# ========================================
# OAUTH APPLICATION MANAGEMENT
# ========================================

def create_oauth_application(
    owner: User,
    name: str,
    redirect_uris: list[str],
    description: str = "",
    homepage_url: str = "",
    allowed_scopes: list[str] | None = None,
) -> tuple[OAuthApplication, str]:
    """
    Create a new OAuth application.

    Args:
        owner: User who owns this application
        name: Application name
        redirect_uris: List of allowed redirect URIs
        description: Application description
        homepage_url: Application homepage URL
        allowed_scopes: List of scopes this app can request

    Returns:
        (application, client_secret) - The secret is only returned once
    """
    if allowed_scopes is None:
        allowed_scopes = ["read:user", "write:generate"]

    # Generate client credentials
    client_id, client_secret = OAuthApplication.generate_client_credentials()

    # Create application
    app = OAuthApplication(
        client_id=client_id,
        client_secret_hash=OAuthApplication.hash_secret(client_secret),
        name=name,
        description=description,
        homepage_url=homepage_url,
        redirect_uris=redirect_uris,
        allowed_scopes=allowed_scopes,
        owner=owner,
    )
    app.save()

    return app, client_secret


def get_oauth_application_by_client_id(client_id: str) -> Optional[OAuthApplication]:
    """Get OAuth application by client_id."""
    try:
        return OAuthApplication.objects(client_id=client_id, is_active=True).first()  # type: ignore
    except Exception as e:
        print(f"Error fetching OAuth application: {e}")
        return None


def verify_oauth_application(client_id: str, client_secret: str) -> Optional[OAuthApplication]:
    """
    Verify OAuth application credentials.

    Returns:
        Application if credentials are valid, None otherwise
    """
    app = get_oauth_application_by_client_id(client_id)
    if not app:
        return None

    if not app.verify_secret(client_secret):
        return None

    return app


def update_oauth_application(
    app: OAuthApplication,
    name: str | None = None,
    description: str | None = None,
    homepage_url: str | None = None,
    redirect_uris: list[str] | None = None,
) -> OAuthApplication:
    """Update an OAuth application."""
    if name is not None:
        app.name = name
    if description is not None:
        app.description = description
    if homepage_url is not None:
        app.homepage_url = homepage_url
    if redirect_uris is not None:
        app.redirect_uris = redirect_uris

    app.updated_at = datetime.now(timezone.utc)
    app.save()
    return app


def delete_oauth_application(app: OAuthApplication):
    """Delete an OAuth application and revoke all associated tokens."""
    # Revoke all authorizations (which will revoke all tokens)
    authorizations = OAuthAuthorization.objects(application=app, is_active=True)
    for auth in authorizations:
        auth.revoke()

    # Delete the application
    app.delete()


# ========================================
# AUTHORIZATION CODE FLOW
# ========================================

def create_authorization_code(
    application: OAuthApplication,
    user: User,
    redirect_uri: str,
    scopes: list[str],
    code_challenge: str | None = None,
    code_challenge_method: str = "S256",
) -> OAuthAuthorizationCode:
    """
    Create an authorization code for the OAuth flow.

    Args:
        application: The OAuth application requesting authorization
        user: The user granting authorization
        redirect_uri: The redirect URI to send the code to
        scopes: List of scopes being authorized
        code_challenge: PKCE code challenge (optional but recommended)
        code_challenge_method: PKCE method (S256 or plain)

    Returns:
        Authorization code object
    """
    # Validate redirect URI
    if not application.is_redirect_uri_allowed(redirect_uri):
        raise ValueError(f"Redirect URI not allowed: {redirect_uri}")

    # Validate scopes
    for scope in scopes:
        if scope not in application.allowed_scopes:
            raise ValueError(f"Scope not allowed: {scope}")

    # Generate code
    code = OAuthAuthorizationCode.generate_code()

    # Create authorization code (expires in 10 minutes)
    auth_code = OAuthAuthorizationCode(
        code=code,
        application=application,
        user=user,
        redirect_uri=redirect_uri,
        scopes=scopes,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    auth_code.save()

    return auth_code


def get_authorization_code(code: str) -> Optional[OAuthAuthorizationCode]:
    """Get authorization code by code string."""
    try:
        return OAuthAuthorizationCode.objects(code=code, is_used=False).first()  # type: ignore
    except Exception as e:
        print(f"Error fetching authorization code: {e}")
        return None


def exchange_authorization_code(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code_verifier: str | None = None,
) -> Optional[dict]:
    """
    Exchange an authorization code for an access token.

    Args:
        code: The authorization code
        client_id: The application client_id
        client_secret: The application client_secret
        redirect_uri: Must match the redirect_uri used to obtain the code
        code_verifier: PKCE code verifier (required if PKCE was used)

    Returns:
        Token response dict with access_token, token_type, expires_in, refresh_token, scope
        or None if exchange fails
    """
    # Verify application credentials
    app = verify_oauth_application(client_id, client_secret)
    if not app:
        return None

    # Get authorization code
    auth_code = get_authorization_code(code)
    if not auth_code:
        return None

    # Verify code belongs to this application
    if auth_code.application.id != app.id:  # type: ignore
        return None

    # Verify redirect URI matches
    if auth_code.redirect_uri != redirect_uri:
        return None

    # Check if expired
    if auth_code.is_expired():
        return None

    # Verify PKCE if used
    if auth_code.code_challenge:
        if not code_verifier:
            return None
        if not auth_code.verify_pkce(code_verifier):
            return None

    # Mark code as used
    auth_code.is_used = True
    auth_code.used_at = datetime.now(timezone.utc)
    auth_code.save()

    # Create access token
    token_data = create_access_token(app, auth_code.user, auth_code.scopes)

    # Update or create authorization record
    update_or_create_authorization(auth_code.user, app, auth_code.scopes)

    return token_data


# ========================================
# TOKEN MANAGEMENT
# ========================================

def create_access_token(
    application: OAuthApplication,
    user: User,
    scopes: list[str],
    access_token_lifetime_hours: int = 1,
    refresh_token_lifetime_days: int = 30,
) -> dict:
    """
    Create an access token and refresh token.

    Args:
        application: The OAuth application
        user: The user the token is for
        scopes: List of scopes granted
        access_token_lifetime_hours: Access token lifetime in hours
        refresh_token_lifetime_days: Refresh token lifetime in days

    Returns:
        Token response dict
    """
    # Generate tokens
    access_token, refresh_token = OAuthToken.generate_tokens()

    # Create token record
    token = OAuthToken(
        access_token=access_token,
        refresh_token=refresh_token,
        application=application,
        user=user,
        scopes=scopes,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=access_token_lifetime_hours),
        refresh_token_expires_at=datetime.now(timezone.utc) + timedelta(days=refresh_token_lifetime_days),
    )
    token.save()

    # Update application stats
    application.last_used_at = datetime.now(timezone.utc)
    application.total_requests += 1  # type: ignore
    application.save()

    # Return token response
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": access_token_lifetime_hours * 3600,  # seconds
        "refresh_token": refresh_token,
        "scope": " ".join(scopes),
    }


def get_token_by_access_token(access_token: str) -> Optional[OAuthToken]:
    """Get token by access_token string."""
    try:
        return OAuthToken.objects(access_token=access_token).first()  # type: ignore
    except Exception as e:
        print(f"Error fetching OAuth token: {e}")
        return None


def get_token_by_refresh_token(refresh_token: str) -> Optional[OAuthToken]:
    """Get token by refresh_token string."""
    try:
        return OAuthToken.objects(refresh_token=refresh_token).first()  # type: ignore
    except Exception as e:
        print(f"Error fetching OAuth token: {e}")
        return None


def verify_access_token(access_token: str) -> Optional[tuple[OAuthToken, User]]:
    """
    Verify an access token and return the token and associated user.

    Returns:
        (token, user) if valid, None otherwise
    """
    token = get_token_by_access_token(access_token)
    if not token:
        return None

    if not token.is_valid():
        return None

    # Record usage
    token.record_usage()
    token.save()

    # Update authorization last used
    auth = OAuthAuthorization.objects(
        user=token.user,
        application=token.application,
        is_active=True
    ).first()
    if auth:
        auth.last_used_at = datetime.now(timezone.utc)
        auth.save()

    return token, token.user


def refresh_access_token(refresh_token: str) -> Optional[dict]:
    """
    Refresh an access token using a refresh token.

    Args:
        refresh_token: The refresh token

    Returns:
        New token response dict or None if refresh fails
    """
    # Get token by refresh token
    old_token = get_token_by_refresh_token(refresh_token)
    if not old_token:
        return None

    # Check if refresh token is expired
    if old_token.refresh_token_expires_at and old_token.refresh_token_expires_at < datetime.now(timezone.utc):
        return None

    # Check if token is revoked
    if old_token.is_revoked:
        return None

    # Revoke old token
    old_token.revoke()
    old_token.save()

    # Create new token with same scopes
    return create_access_token(old_token.application, old_token.user, old_token.scopes)


def revoke_token(access_token: str) -> bool:
    """
    Revoke an access token.

    Returns:
        True if token was revoked, False otherwise
    """
    token = get_token_by_access_token(access_token)
    if not token:
        return False

    token.revoke()
    token.save()
    return True


# ========================================
# AUTHORIZATION MANAGEMENT
# ========================================

def update_or_create_authorization(
    user: User,
    application: OAuthApplication,
    scopes: list[str],
) -> OAuthAuthorization:
    """
    Update or create an authorization record.

    This tracks that a user has authorized an application.
    """
    # Check if authorization already exists
    auth = OAuthAuthorization.objects(user=user, application=application).first()

    if auth:
        # Update existing authorization
        auth.scopes = scopes
        auth.is_active = True
        auth.last_used_at = datetime.now(timezone.utc)
        auth.revoked_at = None
        auth.save()
    else:
        # Create new authorization
        auth = OAuthAuthorization(
            user=user,
            application=application,
            scopes=scopes,
        )
        auth.save()

        # Update application user count
        application.total_users += 1  # type: ignore
        application.save()

    return auth


def get_user_authorizations(user: User) -> list[OAuthAuthorization]:
    """Get all active authorizations for a user."""
    return list(OAuthAuthorization.objects(user=user, is_active=True))  # type: ignore


def revoke_authorization(user: User, application: OAuthApplication) -> bool:
    """
    Revoke a user's authorization for an application.

    This will also revoke all associated tokens.

    Returns:
        True if authorization was revoked, False if not found
    """
    auth = OAuthAuthorization.objects(user=user, application=application, is_active=True).first()
    if not auth:
        return False

    auth.revoke()
    return True


# ========================================
# SCOPE VALIDATION
# ========================================

AVAILABLE_SCOPES = {
    "read:user": "Read your user profile and account information",
    "write:generate": "Generate images on your behalf",
    "read:generations": "View your image generation history",
    "read:account": "View your account balance and usage",
}


def validate_scopes(requested_scopes: list[str]) -> tuple[bool, list[str]]:
    """
    Validate requested scopes.

    Returns:
        (valid, invalid_scopes) - True if all scopes are valid, False otherwise
    """
    invalid_scopes = [scope for scope in requested_scopes if scope not in AVAILABLE_SCOPES]
    return len(invalid_scopes) == 0, invalid_scopes


def parse_scope_string(scope_string: str) -> list[str]:
    """Parse a space-separated scope string into a list."""
    return [s.strip() for s in scope_string.split() if s.strip()]
