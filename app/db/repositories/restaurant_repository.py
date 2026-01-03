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

    async def list_active_restaurant_ids(self) -> list[str]:
        stmt = select(Restaurant.id).where(Restaurant.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

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
        created = False
        try:
            async with self.session.begin_nested():
                self.session.add(restaurant)
                await self.session.flush()
                created = True
        except IntegrityError:
            logger.info(
                "Restaurant already exists (race condition handled) restaurant_id=%s",
                restaurant_id,
                extra={"restaurant_id": restaurant_id},
            )

        if created:
            logger.info(
                "Created new restaurant restaurant_id=%s",
                restaurant_id,
                extra={"restaurant_id": restaurant_id},
            )
            return restaurant, True

        stmt = select(Restaurant).where(Restaurant.id == restaurant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one(), False

    async def get_by_id(self, restaurant_id: str) -> Optional[Restaurant]:
        stmt = select(Restaurant).where(Restaurant.id == restaurant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
