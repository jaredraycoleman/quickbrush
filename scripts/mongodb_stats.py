#!/usr/bin/env python3
"""
MongoDB Storage Statistics Script

This script provides detailed statistics about MongoDB storage usage:
- Overall database size and collection sizes
- Per-user storage breakdown
- Image storage analysis
- Collection-level statistics
"""

import os
import sys
from datetime import datetime, timezone
from dotenv import find_dotenv, load_dotenv
from pymongo import MongoClient
from bson import ObjectId

# Load environment variables
ENV_FILE = find_dotenv()
if ENV_FILE:
    load_dotenv(ENV_FILE)


def format_bytes(bytes_size):
    """Convert bytes to human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


def get_database_stats(db):
    """Get overall database statistics."""
    stats = db.command("dbStats")

    print("=" * 80)
    print("DATABASE OVERVIEW")
    print("=" * 80)
    print(f"Database Name:     {stats['db']}")
    print(f"Collections:       {stats['collections']}")
    print(f"Data Size:         {format_bytes(stats['dataSize'])}")
    print(f"Storage Size:      {format_bytes(stats['storageSize'])}")
    print(f"Index Size:        {format_bytes(stats['indexSize'])}")
    print(f"Total Size:        {format_bytes(stats['dataSize'] + stats['indexSize'])}")
    print(f"Average Obj Size:  {format_bytes(stats.get('avgObjSize', 0))}")
    print(f"Documents:         {stats['objects']:,}")
    print()


def get_collection_stats(db):
    """Get statistics for each collection."""
    print("=" * 80)
    print("COLLECTION BREAKDOWN")
    print("=" * 80)

    collections = db.list_collection_names()
    collection_data = []

    for coll_name in collections:
        try:
            stats = db.command("collStats", coll_name)
            collection_data.append({
                'name': coll_name,
                'count': stats.get('count', 0),
                'size': stats.get('size', 0),
                'storageSize': stats.get('storageSize', 0),
                'totalIndexSize': stats.get('totalIndexSize', 0),
                'avgObjSize': stats.get('avgObjSize', 0)
            })
        except Exception as e:
            print(f"Warning: Could not get stats for {coll_name}: {e}")

    # Sort by size
    collection_data.sort(key=lambda x: x['size'], reverse=True)

    print(f"{'Collection':<25} {'Documents':>12} {'Data Size':>15} {'Storage Size':>15} {'Index Size':>15}")
    print("-" * 80)

    for coll in collection_data:
        print(f"{coll['name']:<25} {coll['count']:>12,} {format_bytes(coll['size']):>15} "
              f"{format_bytes(coll['storageSize']):>15} {format_bytes(coll['totalIndexSize']):>15}")

    print()


def get_user_storage_stats(db):
    """Get per-user storage statistics."""
    print("=" * 80)
    print("PER-USER STORAGE BREAKDOWN")
    print("=" * 80)

    users_collection = db.users
    generations_collection = db.generations
    transactions_collection = db.transactions
    api_keys_collection = db.api_keys

    users = list(users_collection.find())

    if not users:
        print("No users found in database.")
        return

    user_stats = []

    for user in users:
        user_id = user['_id']
        email = user.get('email', 'unknown')

        # Count generations and calculate image storage
        generations = list(generations_collection.find({'user': user_id}))
        gen_count = len(generations)

        # Calculate total image storage (from binary data)
        total_image_size = 0
        for gen in generations:
            if 'image_data' in gen and gen['image_data']:
                total_image_size += len(gen['image_data'])

        # Count transactions
        transaction_count = transactions_collection.count_documents({'user': user_id})

        # Count API keys
        api_key_count = api_keys_collection.count_documents({'user': user_id})

        # Get user document size estimate
        import bson
        user_doc_size = len(bson.BSON.encode(user))

        user_stats.append({
            'email': email,
            'user_id': str(user_id),
            'is_admin': user.get('is_admin', False),
            'generations': gen_count,
            'image_storage': total_image_size,
            'transactions': transaction_count,
            'api_keys': api_key_count,
            'user_doc_size': user_doc_size,
            'total_storage': total_image_size + user_doc_size,
            'created_at': user.get('created_at'),
            'purchased_brushstrokes': user.get('purchased_brushstrokes', 0)
        })

    # Sort by total storage
    user_stats.sort(key=lambda x: x['total_storage'], reverse=True)

    print(f"{'Email':<35} {'Admin':<7} {'Gens':>6} {'Tokens':>8} {'Image Storage':>15} {'Total Storage':>15}")
    print("-" * 100)

    total_image_storage = 0
    total_users = len(user_stats)
    total_gens = 0

    for stat in user_stats:
        admin_marker = "✓" if stat['is_admin'] else ""
        print(f"{stat['email']:<35} {admin_marker:<7} {stat['generations']:>6} "
              f"{stat['purchased_brushstrokes']:>8} {format_bytes(stat['image_storage']):>15} "
              f"{format_bytes(stat['total_storage']):>15}")

        total_image_storage += stat['image_storage']
        total_gens += stat['generations']

    print("-" * 100)
    print(f"{'TOTAL':<35} {'':<7} {total_gens:>6} {'':<8} "
          f"{format_bytes(total_image_storage):>15} {format_bytes(sum(u['total_storage'] for u in user_stats)):>15}")
    print()

    # Average statistics
    avg_gens_per_user = total_gens / total_users if total_users > 0 else 0
    avg_storage_per_user = total_image_storage / total_users if total_users > 0 else 0
    avg_storage_per_gen = total_image_storage / total_gens if total_gens > 0 else 0

    print(f"Average generations per user:     {avg_gens_per_user:.2f}")
    print(f"Average storage per user:         {format_bytes(avg_storage_per_user)}")
    print(f"Average storage per generation:   {format_bytes(avg_storage_per_gen)}")
    print()


def get_image_storage_analysis(db):
    """Analyze image storage patterns."""
    print("=" * 80)
    print("IMAGE STORAGE ANALYSIS")
    print("=" * 80)

    generations_collection = db.generations

    # Get all generations with images
    generations = list(generations_collection.find({'image_data': {'$exists': True}}))

    if not generations:
        print("No images found in database.")
        return

    # Analyze by quality
    quality_stats = {}
    aspect_ratio_stats = {}
    generation_type_stats = {}

    total_images = 0
    total_size = 0
    images_with_data = 0

    for gen in generations:
        total_images += 1

        if 'image_data' in gen and gen['image_data']:
            size = len(gen['image_data'])
            images_with_data += 1
            total_size += size

            # By quality
            quality = gen.get('quality', 'unknown')
            if quality not in quality_stats:
                quality_stats[quality] = {'count': 0, 'total_size': 0}
            quality_stats[quality]['count'] += 1
            quality_stats[quality]['total_size'] += size

            # By aspect ratio
            aspect_ratio = gen.get('aspect_ratio', 'unknown')
            if aspect_ratio not in aspect_ratio_stats:
                aspect_ratio_stats[aspect_ratio] = {'count': 0, 'total_size': 0}
            aspect_ratio_stats[aspect_ratio]['count'] += 1
            aspect_ratio_stats[aspect_ratio]['total_size'] += size

            # By generation type
            gen_type = gen.get('generation_type', 'unknown')
            if gen_type not in generation_type_stats:
                generation_type_stats[gen_type] = {'count': 0, 'total_size': 0}
            generation_type_stats[gen_type]['count'] += 1
            generation_type_stats[gen_type]['total_size'] += size

    print(f"Total generations:        {total_images:,}")
    print(f"Generations with images:  {images_with_data:,}")
    print(f"Total image storage:      {format_bytes(total_size)}")
    print()

    # Quality breakdown
    if quality_stats:
        print("By Quality:")
        print(f"  {'Quality':<15} {'Count':>10} {'Total Size':>15} {'Avg Size':>15}")
        for quality, stats in sorted(quality_stats.items()):
            avg_size = stats['total_size'] / stats['count'] if stats['count'] > 0 else 0
            print(f"  {quality:<15} {stats['count']:>10,} {format_bytes(stats['total_size']):>15} {format_bytes(avg_size):>15}")
        print()

    # Aspect ratio breakdown
    if aspect_ratio_stats:
        print("By Aspect Ratio:")
        print(f"  {'Aspect Ratio':<15} {'Count':>10} {'Total Size':>15} {'Avg Size':>15}")
        for ratio, stats in sorted(aspect_ratio_stats.items()):
            avg_size = stats['total_size'] / stats['count'] if stats['count'] > 0 else 0
            print(f"  {ratio:<15} {stats['count']:>10,} {format_bytes(stats['total_size']):>15} {format_bytes(avg_size):>15}")
        print()

    # Generation type breakdown
    if generation_type_stats:
        print("By Generation Type:")
        print(f"  {'Type':<15} {'Count':>10} {'Total Size':>15} {'Avg Size':>15}")
        for gen_type, stats in sorted(generation_type_stats.items()):
            avg_size = stats['total_size'] / stats['count'] if stats['count'] > 0 else 0
            print(f"  {gen_type:<15} {stats['count']:>10,} {format_bytes(stats['total_size']):>15} {format_bytes(avg_size):>15}")
        print()


def get_transaction_stats(db):
    """Get transaction statistics."""
    print("=" * 80)
    print("TRANSACTION ANALYSIS")
    print("=" * 80)

    transactions_collection = db.transactions

    # Get transaction type breakdown
    pipeline = [
        {
            '$group': {
                '_id': '$transaction_type',
                'count': {'$sum': 1},
                'total_amount': {'$sum': '$amount'}
            }
        },
        {
            '$sort': {'count': -1}
        }
    ]

    type_stats = list(transactions_collection.aggregate(pipeline))

    if not type_stats:
        print("No transactions found.")
        return

    print(f"{'Transaction Type':<25} {'Count':>15} {'Total Amount':>20}")
    print("-" * 60)

    total_count = 0
    for stat in type_stats:
        tx_type = stat['_id']
        count = stat['count']
        total_amount = stat['total_amount']
        total_count += count

        print(f"{tx_type:<25} {count:>15,} {total_amount:>20,}")

    print("-" * 60)
    print(f"{'TOTAL':<25} {total_count:>15,}")
    print()


def main():
    """Main function to run all statistics."""
    # Get MongoDB URI
    mongodb_uri = os.environ.get("MONGODB_URI")
    if not mongodb_uri:
        print("❌ Error: MONGODB_URI environment variable not set")
        print("Please ensure your .env file is configured correctly.")
        sys.exit(1)

    # Connect to MongoDB
    try:
        client = MongoClient(mongodb_uri)

        # Get the database name from the URI or use default
        db_name = "quickbrush"
        if '/' in mongodb_uri:
            # Extract DB name from URI if present
            parts = mongodb_uri.split('/')
            if len(parts) > 3 and parts[-1] and '?' not in parts[-1]:
                db_name = parts[-1].split('?')[0]

        db = client[db_name]

        print("\n" + "=" * 80)
        print("QUICKBRUSH MONGODB STORAGE STATISTICS")
        print("=" * 80)
        print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("=" * 80)
        print()

        # Run all statistics
        get_database_stats(db)
        get_collection_stats(db)
        get_user_storage_stats(db)
        get_image_storage_analysis(db)
        get_transaction_stats(db)

        print("=" * 80)
        print("Report complete!")
        print("=" * 80)

        client.close()

    except Exception as e:
        print(f"❌ Error connecting to MongoDB: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
