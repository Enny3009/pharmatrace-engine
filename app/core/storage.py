import io
from minio import Minio
from minio.error import S3Error
from app.core.config import settings


def get_minio_client() -> Minio:
    """Instantiate a MinIO client bounded to application settings."""
    return Minio(
        endpoint=settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ROOT_USER,
        secret_key=settings.MINIO_ROOT_PASSWORD,
        secure=settings.MINIO_USE_SSL,
    )


def ensure_coa_bucket_exists() -> None:
    """Guarantees that the immutable regulatory certificates bucket exists."""
    client = get_minio_client()
    bucket = settings.MINIO_BUCKET_COA
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def upload_certificate_pdf(object_name: str, pdf_bytes: bytes) -> str:
    """
    Persists immutable regulatory release PDF to MinIO WORM storage.
    Returns object key path.
    """
    ensure_coa_bucket_exists()
    client = get_minio_client()
    data_stream = io.BytesIO(pdf_bytes)
    client.put_object(
        bucket_name=settings.MINIO_BUCKET_COA,
        object_name=object_name,
        data=data_stream,
        length=len(pdf_bytes),
        content_type="application/pdf",
    )
    return object_name


def get_certificate_pdf_stream(object_name: str) -> io.BytesIO:
    """Retrieves PDF bytes stream from MinIO."""
    client = get_minio_client()
    response = client.get_object(
        bucket_name=settings.MINIO_BUCKET_COA,
        object_name=object_name,
    )
    try:
        return io.BytesIO(response.read())
    finally:
        response.close()
        response.release_conn()