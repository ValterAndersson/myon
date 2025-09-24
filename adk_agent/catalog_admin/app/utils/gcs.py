from google.cloud import storage


def create_bucket_if_not_exists(bucket_name: str, project: str, location: str) -> None:
    client = storage.Client(project=project)
    name = bucket_name.replace("gs://", "")
    bucket = client.bucket(name)
    if not bucket.exists():
        client.create_bucket(bucket, location=location)


