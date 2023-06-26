from fastapi.param_functions import Query
from pydantic import BaseModel


class CreateCompetition(BaseModel):
    wallet: str
    name: str
    info: str
    closing_datetime: str
    amount_tickets: int = Query(..., ge=0)
    price_per_ticket: int = Query(..., ge=0)


class CreateTicket(BaseModel):
    name: str
    reward_target: str


class Competitions(BaseModel):
    id: str
    wallet: str
    name: str
    info: str
    closing_datetime: str
    amount_tickets: int
    price_per_ticket: int
    sold: int
    time: int


class Tickets(BaseModel):
    id: str
    wallet: str
    competition: str
    name: str
    reward_target: str
    paid: bool
    time: int
