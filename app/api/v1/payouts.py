import logging

from fastapi import APIRouter, BackgroundTasks, status

from app.api.dependencies import SessionDep
from app.db.repositories import PayoutRepository
from app.db.session import AsyncSessionLocal
from app.exceptions import NotFoundException, SystemException
from app.schemas.payouts import PayoutCreate, PayoutResponse
from app.services.payout_generator import PayoutGenerator

logger = logging.getLogger(__name__)
router = APIRouter()


async def process_batch_payouts(payout_data: PayoutCreate) -> None:
    """Proceso asíncrono batch para generar payouts en segundo plano."""
    try:
        logger.info(
            f"Background task started for restaurant {payout_data.restaurant_id}"
        )
        async with AsyncSessionLocal() as session:
            async with session.begin():
                generator = PayoutGenerator(session)
                await generator.generate_payout(payout_data)
        logger.info(
            f"Background task completed for restaurant {payout_data.restaurant_id}"
        )
    except Exception as e:
        logger.error(
            f"Background task failed for restaurant {payout_data.restaurant_id}: {e}",
            exc_info=True,
        )


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run_payouts(
    payout_data: PayoutCreate, background_tasks: BackgroundTasks
) -> dict:
    """
    Iniciar proceso batch asíncrono para generar payouts.

    Retorna inmediatamente. El proceso se ejecuta en segundo plano.
    """
    logger.info(f"Payout batch initiated for restaurant {payout_data.restaurant_id}")
    background_tasks.add_task(process_batch_payouts, payout_data)

    return {
        "message": "Payout process initiated",
        "restaurant_id": payout_data.restaurant_id,
    }


@router.get("/{payout_id}", response_model=PayoutResponse)
async def get_payout(payout_id: int, session: SessionDep) -> PayoutResponse:
    payout_repo = PayoutRepository(session)
    payout = await payout_repo.get_by_id(payout_id)

    if not payout:
        raise NotFoundException(
            message=f"Payout not found: {payout_id}", details={"payout_id": payout_id}
        )

    return PayoutResponse.model_validate(payout)
