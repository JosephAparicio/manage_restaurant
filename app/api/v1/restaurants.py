from fastapi import APIRouter

from app.api.dependencies import SessionDep
from app.schemas.balance import RestaurantBalance
from app.services.balance_calculator import BalanceCalculator

router = APIRouter()


@router.get("/{restaurant_id}/balance", response_model=RestaurantBalance)
async def get_restaurant_balance(
    restaurant_id: str, session: SessionDep, currency: str = "PEN"
) -> RestaurantBalance:
    calculator = BalanceCalculator(session)
    return await calculator.get_balance(restaurant_id, currency)
