from fastapi import APIRouter, Response, status

from app.api.dependencies import SessionDep
from app.schemas.events import ProcessorEventCreate, ProcessorEventResponse
from app.services.event_processor import EventProcessor

router = APIRouter()


@router.post(
    "/events",
    response_model=ProcessorEventResponse,
)
async def process_event(
    event_data: ProcessorEventCreate, session: SessionDep, response: Response
) -> ProcessorEventResponse:
    async with session.begin():
        processor = EventProcessor(session)
        event, is_new = await processor.process_event(event_data)

        result = ProcessorEventResponse.model_validate(event)
        result.idempotent = not is_new

        response.status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK

        return result
