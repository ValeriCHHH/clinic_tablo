from pydantic import BaseModel
from typing import Optional


class StatusUpdate(BaseModel):
    room_id: int
    doctor_id: Optional[int] = None
    status: str
    status_note: Optional[str] = ""


class TickerUpdate(BaseModel):
    text: str
