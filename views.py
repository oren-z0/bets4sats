from datetime import date, datetime
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


@bookie_ext.get("/{competition_id}", response_class=HTMLResponse)
async def display(request: Request, competition_id):
    competition = await get_competition(competition_id)
    if not competition:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Competition does not exist."
        )

    if competition.amount_tickets < 1:
        return bookie_renderer().TemplateResponse(
            "bookie/error.html",
            {
                "request": request,
                "competition_name": competition.name,
                "competition_error": "Sorry, tickets are sold out :(",
            },
        )
    datetime_object = datetime.strptime(competition.closing_date, "%Y-%m-%d").date()
    if date.today() > datetime_object:
        return bookie_renderer().TemplateResponse(
            "bookie/error.html",
            {
                "request": request,
                "competition_name": competition.name,
                "competition_error": "Sorry, ticket closing date has passed :(",
            },
        )

    return bookie_renderer().TemplateResponse(
        "bookie/display.html",
        {
            "request": request,
            "competition_id": competition_id,
            "competition_name": competition.name,
            "competition_info": competition.info,
            "competition_price": competition.price_per_ticket,
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
            "ticket_name": competition.name,
            "ticket_info": competition.info,
        },
    )


@bookie_ext.get("/register/{competition_id}", response_class=HTMLResponse)
async def register(request: Request, competition_id):
    competition = await get_competition(competition_id)
    if not competition:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Competition does not exist."
        )

    return bookie_renderer().TemplateResponse(
        "bookie/register.html",
        {
            "request": request,
            "competition_id": competition_id,
            "competition_name": competition.name,
            "wallet_id": competition.wallet,
        },
    )
