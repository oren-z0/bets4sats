from http import HTTPStatus

from fastapi import Depends, Query
from starlette.exceptions import HTTPException

from lnbits.core.crud import get_user
from lnbits.core.services import create_invoice
from lnbits.core.views.api import api_payment
from lnbits.decorators import WalletTypeInfo, get_key_type

from . import bookie_ext
from .crud import (
    create_competition,
    create_ticket,
    delete_competition,
    delete_competition_tickets,
    delete_ticket,
    get_competition,
    get_wallet_competition_tickets,
    get_competitions,
    get_ticket,
    get_tickets,
    update_competition,
)
from .models import CreateCompetition, CreateTicket

# Competitions


@bookie_ext.get("/api/v1/competitions")
async def api_competitions(
    all_wallets: bool = Query(False), wallet: WalletTypeInfo = Depends(get_key_type)
):
    wallet_ids = [wallet.wallet.id]

    if all_wallets:
        user = await get_user(wallet.wallet.user)
        wallet_ids = user.wallet_ids if user else []

    return [competition.dict() for competition in await get_competitions(wallet_ids)]


@bookie_ext.post("/api/v1/competitions")
@bookie_ext.put("/api/v1/competitions/{competition_id}")
async def api_competition_create(
    data: CreateCompetition, competition_id=None, wallet: WalletTypeInfo = Depends(get_key_type)
):
    if competition_id:
        competition = await get_competition(competition_id)
        if not competition:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND, detail="Competition does not exist."
            )

        if competition.wallet != wallet.wallet.id:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN, detail="Not your competition."
            )
        competition = await update_competition(competition_id, **data.dict())
    else:
        competition = await create_competition(data=data)

    return competition.dict()


@bookie_ext.delete("/api/v1/competitions/{competition_id}")
async def api_form_delete(competition_id, wallet: WalletTypeInfo = Depends(get_key_type)):
    competition = await get_competition(competition_id)
    if not competition:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Competition does not exist."
        )

    if competition.wallet != wallet.wallet.id:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Not your competition.")

    await delete_competition(competition_id)
    await delete_competition_tickets(competition_id)
    return "", HTTPStatus.NO_CONTENT


#########Tickets##########


@bookie_ext.get("/api/v1/tickets")
async def api_tickets(
    all_wallets: bool = Query(False), wallet: WalletTypeInfo = Depends(get_key_type)
):
    wallet_ids = [wallet.wallet.id]

    if all_wallets:
        user = await get_user(wallet.wallet.user)
        wallet_ids = user.wallet_ids if user else []

    return [ticket.dict() for ticket in await get_tickets(wallet_ids)]


@bookie_ext.get("/api/v1/tickets/{competition_id}/{name}/{reward_target}")
async def api_ticket_make_ticket(competition_id, name, reward_target):
    competition = await get_competition(competition_id)
    if not competition:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Competition does not exist."
        )
    try:
        payment_hash, payment_request = await create_invoice(
            wallet_id=competition.wallet,
            amount=competition.price_per_ticket,
            memo=f"{competition_id}",
            extra={"tag": "competitions", "name": name, "reward_target": reward_target},
        )
    except Exception as e:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(e))
    return {"payment_hash": payment_hash, "payment_request": payment_request}


@bookie_ext.post("/api/v1/tickets/{competition_id}/{payment_hash}")
async def api_ticket_send_ticket(competition_id, payment_hash, data: CreateTicket):
    competition = await get_competition(competition_id)
    if not competition:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Competition could not be fetched.",
        )

    status = await api_payment(payment_hash)
    if status["paid"]:

        exists = await get_ticket(payment_hash)
        if exists:
            return {"paid": True, "ticket_id": exists.id}

        ticket = await create_ticket(
            payment_hash=payment_hash,
            wallet=competition.wallet,
            competition=competition_id,
            name=data.name,
            reward_target=data.reward_target,
        )
        if not ticket:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="Competition could not be fetched.",
            )
        return {"paid": True, "ticket_id": ticket.id}
    return {"paid": False}


@bookie_ext.delete("/api/v1/tickets/{ticket_id}")
async def api_ticket_delete(ticket_id, wallet: WalletTypeInfo = Depends(get_key_type)):
    ticket = await get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Ticket does not exist."
        )

    if ticket.wallet != wallet.wallet.id:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Not your ticket.")

    await delete_ticket(ticket_id)
    return "", HTTPStatus.NO_CONTENT


# Competition Tickets


@bookie_ext.get("/api/v1/competitiontickets/{wallet_id}/{competition_id}")
async def api_competition_tickets(wallet_id, competition_id):
    return [
        ticket.dict()
        for ticket in await get_wallet_competition_tickets(wallet_id=wallet_id, competition_id=competition_id)
    ]


@bookie_ext.get("/api/v1/register/ticket/{ticket_id}")
async def api_competition_register_ticket(ticket_id):
    ticket = await get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Ticket does not exist."
        )

    if not ticket.paid:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Ticket not paid for."
        )

    return ticket.dict()
