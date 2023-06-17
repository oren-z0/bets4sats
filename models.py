from fastapi.param_functions import Query
from pydantic import BaseModel


class CreateCompetition(BaseModel):
    wallet: str
    name: str
    info: str
    closing_date: str
    competition_end_date: str
    amount_tickets: int = Query(..., ge=0)
    price_per_ticket: int = Query(..., ge=0)


class CreateTicket(BaseModel):
    name: str
    email: str


class Competitions(BaseModel):
    id: str
    wallet: str
    name: str
    info: str
    closing_date: str
    competition_end_date: str
    amount_tickets: int
    price_per_ticket: int
    sold: int
    time: int


class Tickets(BaseModel):
    id: str
    wallet: str
    competition: str
    name: str
    email: str
    registered: bool
    paid: bool
    time: int
