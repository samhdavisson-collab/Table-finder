import os
import json
from datetime import date, datetime
import boto3
if os.path.exists(".env"):
    from dotenv import load_dotenv
    load_dotenv()
# -----------------------------
# Config
# -----------------------------
BUCKET_NAME = os.environ["R2_BUCKET"]
ACCOUNT_ID = os.environ["R2_ACCOUNT_ID"]

ENDPOINT_URL = f"https://{ACCOUNT_ID}.r2.cloudflarestorage.com"

from botocore.config import Config
import boto3
import os

R2_ACCOUNT_ID = os.environ["R2_ACCOUNT_ID"]
R2_ACCESS_KEY_ID = os.environ["R2_ACCESS_KEY_ID"]
R2_SECRET_ACCESS_KEY = os.environ["R2_SECRET_ACCESS_KEY"]

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    region_name="auto",
    config=Config(
        signature_version="s3v4",
        retries={"max_attempts": 5},
    ),
)

TODAY = date.today()
print(f"🕒 Today is {TODAY}")

# -----------------------------
# Helpers
# -----------------------------
def list_meta_files():
    """Find all meta.json files under events/"""
    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix="events/"):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith("meta.json"):
                yield obj["Key"]


def delete_prefix(prefix):
    """Delete all objects under a prefix"""
    print(f"🗑️  Deleting all files under: {prefix}")

    paginator = s3.get_paginator("list_objects_v2")
    to_delete = []

    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
        for obj in page.get("Contents", []):
            to_delete.append({"Key": obj["Key"]})

    if not to_delete:
        print("⚠️  Nothing found to delete")
        return

    # Delete in batches of 1000 (S3 limit)
    for i in range(0, len(to_delete), 1000):
        batch = to_delete[i : i + 1000]
        s3.delete_objects(
            Bucket=BUCKET_NAME,
            Delete={"Objects": batch},
        )

    print(f"✅ Deleted {len(to_delete)} objects")


# -----------------------------
# Main cleanup loop
# -----------------------------
deleted_anything = False

for meta_key in list_meta_files():
    print("\n----------------------------------------")
    print(f"📄 Checking {meta_key}")

    try:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=meta_key)
        meta = json.loads(obj["Body"].read())
    except Exception as e:
        print(f"❌ Failed to read meta.json: {e}")
        continue

    delete_after_str = meta.get("delete_after")

    if not delete_after_str:
        print("⏭️  SKIP: no delete_after field")
        continue

    try:
        delete_after = datetime.strptime(delete_after_str, "%Y-%m-%d").date()
    except ValueError:
        print(f"❌ Invalid delete_after format: {delete_after_str}")
        continue

    print(f"📅 delete_after = {delete_after}")

    if delete_after > TODAY:
        print("⏭️  SKIP: delete_after is in the future")
        continue

    # Determine event folder
    prefix = meta_key.rsplit("/", 1)[0] + "/"
    print(f"🔥 DELETE triggered for event prefix: {prefix}")

    delete_prefix(prefix)
    deleted_anything = True

if not deleted_anything:
    print("\n✨ Cleanup finished — nothing needed deletion")
else:
    print("\n🎉 Cleanup finished — expired events deleted")
