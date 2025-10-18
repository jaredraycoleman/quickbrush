#!/usr/bin/env python3
"""
Helper script to properly format MongoDB Atlas connection string.
Handles URL encoding of special characters in username/password.
"""

import urllib.parse
import sys

def fix_mongodb_uri():
    print("=" * 80)
    print("MongoDB Atlas Connection String Fixer")
    print("=" * 80)
    print()

    # Get connection details
    print("Please provide your MongoDB Atlas connection details:")
    print()

    username = input("Username: ").strip()
    password = input("Password: ").strip()
    cluster = input("Cluster address (e.g., cluster0.xxxxx.mongodb.net): ").strip()
    database = input("Database name [quickbrush]: ").strip() or "quickbrush"

    print()
    print("Encoding special characters...")

    # URL encode username and password
    encoded_username = urllib.parse.quote_plus(username)
    encoded_password = urllib.parse.quote_plus(password)

    # Build proper connection string with SSL/TLS parameters
    connection_string = (
        f"mongodb+srv://{encoded_username}:{encoded_password}@{cluster}/"
        f"?retryWrites=true&w=majority&ssl=true&tlsAllowInvalidCertificates=false"
    )

    print()
    print("=" * 80)
    print("✅ Your properly formatted MongoDB URI:")
    print("=" * 80)
    print()
    print(connection_string)
    print()
    print("=" * 80)
    print("To update your Kubernetes secret, run:")
    print("=" * 80)
    print()
    print("kubectl -n quickbrush delete secret mongodb-uri --ignore-not-found")
    print()
    print(f"kubectl -n quickbrush create secret generic mongodb-uri \\")
    print(f"  --from-literal=MONGODB_URI='{connection_string}'")
    print()
    print("kubectl -n quickbrush rollout restart deployment quickbrush-service")
    print()
    print("=" * 80)

    # Show what characters were encoded
    if encoded_username != username:
        print()
        print(f"ℹ️  Username had special characters and was encoded:")
        print(f"   Original: {username}")
        print(f"   Encoded:  {encoded_username}")

    if encoded_password != password:
        print()
        print(f"ℹ️  Password had special characters and was encoded:")
        print(f"   Original: {password}")
        print(f"   Encoded:  {encoded_password}")
        print()
        print("Common special characters that need encoding:")
        print("  @ → %40    # → %23    $ → %24    % → %25")
        print("  & → %26    / → %2F    : → %3A    = → %3D")
        print("  ? → %3F    + → %2B    , → %2C    space → %20")

if __name__ == "__main__":
    try:
        fix_mongodb_uri()
    except KeyboardInterrupt:
        print("\n\nAborted.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
