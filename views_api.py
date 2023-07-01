from http import HTTPStatus
from datetime import datetime
import json

from fastapi import Depends, Query
import shortuuid
from starlette.exceptions import HTTPException

from lnbits.core.crud import get_user, get_standalone_payment, get_payments
from lnbits.core.models import PaymentFilters
from lnbits.core.services import create_invoice
from lnbits.core.views.api import api_payment
from lnbits.db import Filters, Filter
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
from .models import CreateCompetition, CreateInvoiceForTicket

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


@bookie_ext.post("/api/v1/tickets/{competition_id}")
async def api_ticket_make_ticket(competition_id, data: CreateInvoiceForTicket):
    competition = await get_competition(competition_id)
    if not competition:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Competition does not exist."
        )
    # if competition.state != "INITIAL" or competition.amount_tickets <= 0 or datetime.utcnow() > datetime.strptime(competition.closing_datetime, "%Y-%m-%dT%H:%M:%S.%fZ"):
    #     raise HTTPException(
    #         status_code=HTTPStatus.FORBIDDEN,
    #         detail="Competition is close for new tickets."
    #     )    
    # if data.amount < competition.min_bet or data.amount > competition.max_bet:
    #     raise HTTPException(
    #         status_code=HTTPStatus.FORBIDDEN, detail="Amount must be between Min-Bet and Max-Bet"
    #     )
    # if data.choice < 0 or data.choice >= len(json.loads(competition.choices)):
    #     raise HTTPException(
    #         status_code=HTTPStatus.FORBIDDEN, detail="Invalid choice"
    #     )
    ticket_id = shortuuid.random()
    payment_request = None
    try:
        _payment_hash, payment_request = await create_invoice(
            wallet_id=competition.wallet,
            amount=data.amount,
            memo=f"BookieTicketId:{competition_id}.{ticket_id}",
            extra={"tag": "bookie", "reward_target": data.reward_target, "choice": data.choice},
        )
    except Exception as e:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(e))
    return {"ticket_id": ticket_id, "payment_request": payment_request}


@bookie_ext.get("/api/v1/tickets/{competition_id}/{ticket_id}")
async def api_ticket_send_ticket(competition_id, ticket_id):
    competition = await get_competition(competition_id)
    if not competition:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Competition could not be fetched.",
        )

    all_payments = await get_payments(
        wallet_id=competition.wallet,
        incoming=True,
        limit=1,
        filters=Filters(
            filters=[Filter(
              field="memo",
              values=[f"BookieTicketId:{competition_id}.{ticket_id}"],
              model=PaymentFilters
            )],
            model=PaymentFilters,
        )
    )
    if not all_payments:
        raise HTTPException(
              status_code=HTTPStatus.NOT_FOUND,
              detail="Payment of given ticket-id could not be fetched.",
          )
    payment, = all_payments
    if payment.pending:
        await payment.check_status()
    if payment.pending:
        return {"paid": False}
    exists = await get_ticket(ticket_id)
    if exists:
        return {"paid": True}
    if competition.state != "INITIAL" or competition.amount_tickets <= 0 or datetime.utcnow() > datetime.strptime(competition.closing_datetime, "%Y-%m-%dT%H:%M:%S.%fZ"):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="Competition is close for new tickets. If you think you should get a refund, please contact the admin."
        )

    await create_ticket(
        ticket_id=ticket_id,
        wallet=competition.wallet,
        competition=competition_id,
        amount=payment.sat,
        reward_target=str(payment.extra.get("reward_target")),
        choice=int(payment.extra.get("choice"))
    )
    return {"paid": True}


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

    return ticket.dict()
