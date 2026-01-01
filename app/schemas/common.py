from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class BaseResponse(BaseModel):
    success: bool = True
    meta: dict = Field(default_factory=dict)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[dict] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
    meta: dict = Field(default_factory=dict)
