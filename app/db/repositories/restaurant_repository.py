import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Restaurant

logger = logging.getLogger(__name__)


class RestaurantRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(
        self, restaurant_id: str, name: Optional[str] = None
    ) -> tuple[Restaurant, bool]:
        stmt = select(Restaurant).where(Restaurant.id == restaurant_id)
        result = await self.session.execute(stmt)
        restaurant = result.scalar_one_or_none()

        if restaurant:
            return restaurant, False

        if name is None:
            name = restaurant_id

        restaurant = Restaurant(id=restaurant_id, name=name)
        self.session.add(restaurant)

        try:
            await self.session.flush()
            logger.info(f"Created new restaurant: {restaurant_id}")
            return restaurant, True
        except IntegrityError:
            await self.session.rollback()
            stmt = select(Restaurant).where(Restaurant.id == restaurant_id)
            result = await self.session.execute(stmt)
            restaurant = result.scalar_one()
            logger.info(
                f"Restaurant {restaurant_id} already exists (race condition handled)"
            )
            return restaurant, False

    async def get_by_id(self, restaurant_id: str) -> Optional[Restaurant]:
        stmt = select(Restaurant).where(Restaurant.id == restaurant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
