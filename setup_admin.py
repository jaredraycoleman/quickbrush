#!/usr/bin/env python3
"""
Setup script to create the first admin user.

This script should be run once to set up your first admin user.
After that, admins can manage other users.

Usage:
    python3 setup_admin.py <email>

Example:
    python3 setup_admin.py admin@example.com
"""

import sys
from dotenv import find_dotenv, load_dotenv
from database import init_db
from models import User

# Load environment variables
ENV_FILE = find_dotenv()
if ENV_FILE:
    load_dotenv(ENV_FILE)

def setup_admin(email: str):
    """Set up an admin user by email."""

    # Initialize database
    if not init_db():
        print("❌ Error: Could not connect to MongoDB")
        print("Please check your MONGODB_URI environment variable.")
        return False

    # Find user by email
    user = User.objects(email=email).first()  # type: ignore

    if not user:
        print(f"❌ Error: No user found with email '{email}'")
        print("\nPlease make sure:")
        print("1. The user has logged in at least once (so they're in the database)")
        print("2. The email matches exactly (case-sensitive)")
        return False

    # Check if already admin
    if user.is_admin:
        print(f"ℹ️  User '{email}' is already an admin.")
        return True

    # Make admin
    user.is_admin = True
    user.save()

    print(f"✅ Success! User '{email}' is now an admin.")
    print(f"\nUser details:")
    print(f"  Name: {user.name}")
    print(f"  Email: {user.email}")
    print(f"  Auth0 ID: {user.auth0_sub}")
    print(f"  Admin: {user.is_admin}")

    print("\n🎉 You can now:")
    print("  1. Log in to the application")
    print("  2. Navigate to the Admin panel")
    print("  3. Manage users and gift tokens")

    return True


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 setup_admin.py <email>")
        print("\nExample:")
        print("  python3 setup_admin.py admin@example.com")
        sys.exit(1)

    email = sys.argv[1]
    success = setup_admin(email)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
