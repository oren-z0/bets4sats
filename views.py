import json
from datetime import datetime
from http import HTTPStatus

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException
from starlette.responses import HTMLResponse

from lnbits.core.models import User
from lnbits.decorators import check_user_exists

from . import bookie_ext, bookie_renderer
from .crud import get_competition, get_ticket

templates = Jinja2Templates(directory="templates")


@bookie_ext.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return bookie_renderer().TemplateResponse(
        "bookie/index.html", {"request": request, "user": user.dict()}
    )


@bookie_ext.get("/competitions/{competition_id}", response_class=HTMLResponse)
async def display(request: Request, competition_id):
    competition = await get_competition(competition_id)
    if not competition:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Competition does not exist."
        )

    return bookie_renderer().TemplateResponse(
        "bookie/display.html",
        {
            "request": request,
            "competition_id": competition_id,
            "competition_name": competition.name,
            "competition_info": competition.info,
            "competition_banner": json.dumps(competition.banner),
            "competition_state": competition.state,
            "competition_closing_datetime": competition.closing_datetime,
            "competition_choices": competition.choices,
            "competition_winning_choice": competition.winning_choice,
            "competition_amount_tickets": competition.amount_tickets,
            "competition_min_bet": competition.min_bet,
            "competition_max_bet": competition.max_bet,
        },
    )


@bookie_ext.get("/ticket/{ticket_id}", response_class=HTMLResponse)
async def ticket(request: Request, ticket_id):
    ticket = await get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Ticket does not exist."
        )

    competition = await get_competition(ticket.competition)
    if not competition:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Competition does not exist."
        )

    return bookie_renderer().TemplateResponse(
        "bookie/ticket.html",
        {
            "request": request,
            "ticket_id": ticket_id,
            "ticket_amount": ticket.amount,
            "competition_name": competition.name,
            "competition_id": competition.id,
            "ticket_choice": json.loads(competition.choices)[ticket.choice]["title"],
            "ticket_state": ticket.state,
        },
    )


@bookie_ext.get("/register/{wallet_id}/{competition_id}", response_class=HTMLResponse)
async def register(request: Request, wallet_id, competition_id):
    competition = await get_competition(competition_id)
    if not competition:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Competition does not exist."
        )
    if competition.wallet != wallet_id:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Competition not found in wallet."
        )
    return bookie_renderer().TemplateResponse(
        "bookie/register.html",
        {
            "request": request,
            "competition_id": competition_id,
            "competition_name": competition.name,
            "competition_choices": competition.choices,
            "wallet_id": wallet_id,
        },
    )
