import logging

from fastapi import APIRouter, BackgroundTasks, status

from app.api.dependencies import SessionDep
from app.db.repositories import PayoutRepository
from app.db.session import AsyncSessionLocal
from app.exceptions import NotFoundException, SystemException
from app.schemas.payouts import PayoutResponse, PayoutRunRequest
from app.services.payout_generator import PayoutGenerator

logger = logging.getLogger(__name__)
router = APIRouter()


async def process_batch_payouts(payout_data: PayoutRunRequest) -> None:
    """Background task to generate payouts asynchronously within atomic transaction."""
    try:
        logger.info(
            "Background payout batch task started for currency=%s as_of=%s min_amount=%s",
            payout_data.currency,
            payout_data.as_of,
            payout_data.min_amount,
        )
        async with AsyncSessionLocal() as session:
            async with session.begin():
                generator = PayoutGenerator(session)
                await generator.generate_payouts_batch(payout_data)
        logger.info(
            "Background payout batch task completed for currency=%s as_of=%s",
            payout_data.currency,
            payout_data.as_of,
        )
    except Exception as e:
        logger.error(
            "Background payout batch task failed: %s",
            e,
            exc_info=True,
        )


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run_payouts(
    payout_data: PayoutRunRequest, background_tasks: BackgroundTasks
) -> dict:
    logger.info(
        "Payout batch initiated for currency=%s as_of=%s min_amount=%s",
        payout_data.currency,
        payout_data.as_of,
        payout_data.min_amount,
    )
    background_tasks.add_task(process_batch_payouts, payout_data)

    return {
        "message": "Payout process initiated",
        "currency": payout_data.currency,
        "as_of": payout_data.as_of.isoformat(),
        "min_amount": payout_data.min_amount,
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
