import argparse
import asyncio
import logging

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from vetorthoplan.application.use_cases import ProcessNextImageIngestion
from vetorthoplan.config.settings import get_settings
from vetorthoplan.infrastructure.clock import SystemClock
from vetorthoplan.infrastructure.database.image_upload_repository import (
    SqlAlchemyImageUploadRepository,
)
from vetorthoplan.infrastructure.database.ingestion_job_queue import (
    SqlAlchemyIngestionJobQueue,
)
from vetorthoplan.infrastructure.image_content import BasicImageContentInspector
from vetorthoplan.infrastructure.storage import S3PresignedPostStorage

logger = logging.getLogger("vetorthoplan.worker")


async def run_worker(*, once: bool) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    storage = S3PresignedPostStorage(
        bucket=settings.storage_bucket,
        region=settings.storage_region,
        endpoint_url=settings.storage_endpoint_url,
        expires_in_seconds=settings.upload_url_expires_seconds,
    )
    try:
        while True:
            async with session_factory() as session:
                use_case = ProcessNextImageIngestion(
                    job_queue=SqlAlchemyIngestionJobQueue(session),
                    upload_repository=SqlAlchemyImageUploadRepository(session),
                    storage=storage,
                    inspector=BasicImageContentInspector(),
                    clock=SystemClock(),
                )
                result = await use_case.execute()
                await session.commit()

            if result is not None:
                logger.info("Job %s finalizado com status %s", result.job.id, result.job.status)
            if once:
                return
            if result is None:
                await asyncio.sleep(settings.worker_poll_seconds)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker de ingestão de imagens do VetOrthoPlan")
    parser.add_argument("--once", action="store_true", help="Processa no máximo um job e encerra")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker(once=args.once))


if __name__ == "__main__":
    main()
