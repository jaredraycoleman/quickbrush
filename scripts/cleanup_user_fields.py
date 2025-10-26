#!/usr/bin/env python3
"""
Migration script to remove deprecated fields from User model.

This script removes the following fields:
- is_active (deprecated, unused)
- invitation_code (from invite system removal)
- has_valid_invite (from invite system removal)
"""

from dotenv import find_dotenv, load_dotenv
from pymongo import MongoClient
import os

# Load environment variables
ENV_FILE = find_dotenv()
if ENV_FILE:
    load_dotenv(ENV_FILE)


def migrate():
    """Remove deprecated fields from user documents."""

    # Get MongoDB URI
    mongodb_uri = os.environ.get("MONGODB_URI")
    if not mongodb_uri:
        print("❌ Error: MONGODB_URI environment variable not set")
        return False

    # Connect to MongoDB
    print("Connecting to MongoDB...")
    client = MongoClient(mongodb_uri)

    # Get the database
    db_name = "quickbrush"
    db = client[db_name]

    print(f"Connected to database: {db_name}")

    # Remove deprecated fields from users
    print("\n🧹 Removing deprecated fields from users...")
    users_collection = db.users

    # Check how many users have these fields
    users_with_fields = users_collection.count_documents({
        "$or": [
            {"is_active": {"$exists": True}},
            {"invitation_code": {"$exists": True}},
            {"has_valid_invite": {"$exists": True}}
        ]
    })

    print(f"   Found {users_with_fields} users with deprecated fields")

    if users_with_fields > 0:
        result = users_collection.update_many(
            {},
            {
                "$unset": {
                    "is_active": "",
                    "invitation_code": "",
                    "has_valid_invite": ""
                }
            }
        )

        print(f"   ✅ Cleaned up {result.modified_count} user documents")
    else:
        print(f"   ℹ️  No users with deprecated fields")

    # Verify the changes
    print("\n✅ Verifying changes...")
    remaining = users_collection.count_documents({
        "$or": [
            {"is_active": {"$exists": True}},
            {"invitation_code": {"$exists": True}},
            {"has_valid_invite": {"$exists": True}}
        ]
    })

    if remaining == 0:
        print("   ✅ All deprecated fields removed successfully")
    else:
        print(f"   ⚠️  Warning: {remaining} users still have deprecated fields")

    print("\n✅ Migration complete!")

    client.close()
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("USER MODEL CLEANUP MIGRATION")
    print("=" * 60)
    print()
    print("This script will remove deprecated fields from users:")
    print("  - is_active (deprecated, never used)")
    print("  - invitation_code (from removed invite system)")
    print("  - has_valid_invite (from removed invite system)")
    print()

    migrate()
