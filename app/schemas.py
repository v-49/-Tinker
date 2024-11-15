from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class JobSchema(BaseModel):
    number: Optional[str]
    name: str
    time: Optional[datetime]
    level: Optional[str]
    class Config:
        orm_mode = True

class CheckSchema(BaseModel):
    number: Optional[str]
    name: str
    check_time: Optional[datetime]
    countdown: Optional[str]
    status: Optional[int]
    check_group:Optional[str]
    class Config:
        orm_mode = True
