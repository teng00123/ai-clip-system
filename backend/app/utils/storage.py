import io
from datetime import timedelta
from urllib3 import Timeout

from minio import Minio
from minio.error import S3Error

from app.config import settings

# MinIO 操作超时：连接 10s，读写 120s（大文件预留足够时间）
_MINIO_TIMEOUT = Timeout(connect=10, read=120)

client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_SECURE,
    http_client=None,  # 使用默认 urllib3，由 Timeout 控制
)
# minio-py 通过 _http 的 pool_manager 控制超时
# 重新初始化带超时的 client
import urllib3

_http = urllib3.PoolManager(
    timeout=_MINIO_TIMEOUT,
    maxsize=10,
    retries=urllib3.Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504]),
)

client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_SECURE,
    http_client=_http,
)


def ensure_bucket():
    if not client.bucket_exists(settings.MINIO_BUCKET):
        client.make_bucket(settings.MINIO_BUCKET)


def upload_file(object_name: str, file_path: str, content_type: str = "application/octet-stream") -> str:
    ensure_bucket()
    client.fput_object(settings.MINIO_BUCKET, object_name, file_path, content_type=content_type)
    return object_name


def upload_bytes(object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    ensure_bucket()
    client.put_object(settings.MINIO_BUCKET, object_name, io.BytesIO(data), len(data), content_type=content_type)
    return object_name


def get_presigned_url(object_name: str, expires_hours: int = 24) -> str:
    return client.presigned_get_object(settings.MINIO_BUCKET, object_name, expires=timedelta(hours=expires_hours))


def download_file(object_name: str, dest_path: str):
    client.fget_object(settings.MINIO_BUCKET, object_name, dest_path)


def remove_object(object_name: str) -> None:
    try:
        client.remove_object(settings.MINIO_BUCKET, object_name)
    except S3Error as exc:
        if exc.code not in {"NoSuchKey", "NoSuchObject"}:
            raise
