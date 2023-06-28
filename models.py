from fastapi.param_functions import Query
from pydantic import BaseModel

MAX_SATS=21_000_000_00_000_000

class CreateCompetition(BaseModel):
    wallet: str
    name: str
    info: str
    closing_datetime: str
    amount_tickets: int = Query(..., ge=0)
    min_bet: int = Query(..., gt=0, lt=MAX_SATS)
    max_bet: int = Query(..., gt=0, lt=MAX_SATS)
    choices: str

class CreateInvoiceForTicket(BaseModel):
    reward_target: str
    amount: int

class Competitions(BaseModel):
    id: str
    wallet: str
    name: str
    info: str
    closing_datetime: str
    amount_tickets: int
    min_bet: int
    max_bet: int
    sold: int
    choices: str
    winning_choice: int
    state: str
    time: int


class Tickets(BaseModel):
    id: str
    wallet: str
    competition: str
    amount: int
    reward_target: str
    time: int
