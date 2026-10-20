"""Remove expired or cancelled upload sessions and their quarantine objects."""

import asyncio
from datetime import timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from vetorthoplan.config.settings import get_settings
from vetorthoplan.infrastructure.clock import SystemClock
from vetorthoplan.infrastructure.database.image_upload_repository import (
    SqlAlchemyImageUploadRepository,
)
from vetorthoplan.infrastructure.storage import S3PresignedPostStorage


async def cleanup() -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    storage = S3PresignedPostStorage(
        bucket=settings.storage_bucket,
        region=settings.storage_region,
        endpoint_url=settings.storage_endpoint_url,
        expires_in_seconds=settings.upload_url_expires_seconds,
    )
    removed = 0
    failures = 0
    try:
        async with sessions() as session:
            repository = SqlAlchemyImageUploadRepository(session)
            while True:
                cleanup_cutoff = SystemClock().now() - timedelta(minutes=15)
                expired = await repository.list_expired(cleanup_cutoff, limit=500)
                if not expired:
                    break
                for upload in expired:
                    try:
                        await storage.delete_object(upload.object_key)
                        await repository.delete(upload.tenant_id, upload.id)
                        await session.commit()
                        removed += 1
                    except Exception:
                        await session.rollback()
                        failures += 1
                        print(f"Não foi possível limpar a sessão {upload.id}")
                if failures:
                    break
                if len(expired) < 500:
                    break
    finally:
        await engine.dispose()
    print(f"Sessões removidas: {removed}; falhas: {failures}")
    return failures


def main() -> None:
    failures = asyncio.run(cleanup())
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
