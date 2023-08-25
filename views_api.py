from http import HTTPStatus
from datetime import datetime
import json
import hmac

from fastapi import Depends, Query
from loguru import logger
import shortuuid
from starlette.exceptions import HTTPException

from lnbits.core.crud import get_user
from lnbits.core.services import create_invoice
from lnbits.decorators import WalletTypeInfo, get_key_type

from . import bets4sats_ext
from .tasks import reward_ticket_ids_queue
from .helpers import get_lnurlp_parameters, send_ticket
from .crud import (
    cas_competition_state,
    create_competition,
    delete_competition,
    delete_competition_tickets,
    delete_ticket,
    get_competition,
    get_state_competition_tickets,
    get_wallet_competition_tickets,
    get_competitions,
    get_ticket,
    get_tickets,
    sum_choices_amounts,
    update_competition,
    update_competition_winners,
)
from .models import CompleteCompetition, CreateCompetition, CreateInvoiceForTicket, UpdateCompetition

# Competitions


@bets4sats_ext.get("/api/v1/competitions")
async def api_competitions(
    all_wallets: bool = Query(False), wallet: WalletTypeInfo = Depends(get_key_type)
):
    wallet_ids = [wallet.wallet.id]

    if all_wallets:
        user = await get_user(wallet.wallet.user)
        wallet_ids = user.wallet_ids if user else []

    return [competition.dict() for competition in await get_competitions(wallet_ids)]


@bets4sats_ext.post("/api/v1/competitions")
async def api_competition_create(data: CreateCompetition):
    choices = json.loads(data.choices)
    if not isinstance(choices, list):
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Choices must be a list")
    if not all(isinstance(choice, dict) and isinstance(choice.get("title"), str) and choice["title"] for choice in choices):
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Choices title must be a non-empty string")
    if len(choices) < 2:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Must have at least 2 choices")
    try:
        datetime.strptime(data.closing_datetime, "%Y-%m-%dT%H:%M:%S.%fZ")
    except:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Invalid closing_datetime")

    competition = await create_competition(data=data)

    return competition.dict()

@bets4sats_ext.patch("/api/v1/competitions/{competition_id}")
async def api_competition_update(data: UpdateCompetition, competition_id: str, wallet: WalletTypeInfo = Depends(get_key_type)):
    if data.amount_tickets is not None and data.amount_tickets < 0:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="amount_tickets cannot be negative")
    if data.closing_datetime is not None:
      try:
          datetime.strptime(data.closing_datetime, "%Y-%m-%dT%H:%M:%S.%fZ")
      except:
          raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Invalid closing_datetime")        
    competition = await get_competition(competition_id)
    if not competition:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Competition not found")
    if competition.wallet != wallet.wallet.id:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Not your competition"
        )
    if competition.state != "INITIAL":
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Cannot change competition after closing")

    competition = await update_competition(competition_id, data)
    if competition is None:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Cannot update competition when no longer in INITIAL state"
        )
    return competition.dict()

@bets4sats_ext.post("/api/v1/competitions/{competition_id}/complete")
async def api_competition_complete(data: CompleteCompetition, competition_id: str, wallet: WalletTypeInfo = Depends(get_key_type)):
    if data.winning_choice < -1:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="winning_choice cannot be below -1")
    
    competition = await get_competition(competition_id)
    if not competition:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="competition not found")
    if competition.wallet != wallet.wallet.id:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Not your competition"
        )
    cas_result = await cas_competition_state(competition_id, "INITIAL", "COMPLETED_PAYING")
    if not cas_result:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="competition already completed")
    # refetch competition after cas
    competition = await get_competition(competition_id)
    choices = json.loads(competition.choices)
    if data.winning_choice >= len(choices):
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="winning_choice too high")
    if data.winning_choice >= 0 and choices[data.winning_choice]["total"] == 0:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="no bet on winning choice")
    for choice in choices:
        choice["pre_agg_total"] = choice["total"]
        choice["total"] = 0
    choice_amount_sums = await sum_choices_amounts(competition.id)
    for choice_amount_sum in choice_amount_sums:
        choices[choice_amount_sum.choice]["total"] = choice_amount_sum.amount_sum
    await update_competition_winners(competition_id, json.dumps(choices), data.winning_choice)
    unpaid_tickets = await get_state_competition_tickets(competition_id, ["WON_UNPAID", "CANCELLED_UNPAID"])
    for ticket in unpaid_tickets:
        reward_ticket_ids_queue.put_nowait(ticket.id)
    competition = await get_competition(competition_id)
    return competition.dict()

@bets4sats_ext.delete("/api/v1/competitions/{competition_id}")
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


@bets4sats_ext.get("/api/v1/tickets")
async def api_tickets(
    all_wallets: bool = Query(False), wallet: WalletTypeInfo = Depends(get_key_type)
):
    wallet_ids = [wallet.wallet.id]

    if all_wallets:
        user = await get_user(wallet.wallet.user)
        wallet_ids = user.wallet_ids if user else []

    return [ticket.dict() for ticket in await get_tickets(wallet_ids)]


@bets4sats_ext.post("/api/v1/tickets/{competition_id}")
async def api_ticket_make_ticket(competition_id, data: CreateInvoiceForTicket):
    competition = await get_competition(competition_id)
    if not competition:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Competition does not exist."
        )
    if competition.state != "INITIAL" or competition.amount_tickets <= 0 or datetime.utcnow() > datetime.strptime(competition.closing_datetime, "%Y-%m-%dT%H:%M:%S.%fZ"):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="Competition is close for new tickets."
        )    
    if data.amount < competition.min_bet or data.amount > competition.max_bet:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Amount must be between Min-Bet and Max-Bet"
        )
    if data.choice < 0 or data.choice >= len(json.loads(competition.choices)):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Invalid choice"
        )
    if data.reward_target:
        try:
            await get_lnurlp_parameters(data.reward_target)
        except Exception as error:
            logger.warning(f"Failed to get lnurlp parameters {error}")
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN, detail="Bad lightning address or lnurl-pay"
            )            
    ticket_id = shortuuid.random()
    payment_request = None
    try:
        _payment_hash, payment_request = await create_invoice(
            wallet_id=competition.wallet,
            amount=data.amount,
            memo=f"Bets4SatsTicketId:{competition_id}.{ticket_id}",
            extra={"tag": "bets4sats", "reward_target": data.reward_target, "choice": data.choice},
        )
    except Exception as e:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(e))
    return {"ticket_id": ticket_id, "payment_request": payment_request}


@bets4sats_ext.get("/api/v1/tickets/{competition_id}/{ticket_id}")
async def api_ticket_send_ticket(competition_id, ticket_id):
    response = await send_ticket(competition_id, ticket_id)
    return response

@bets4sats_ext.delete("/api/v1/tickets/{ticket_id}")
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


@bets4sats_ext.get("/api/v1/competitiontickets/{competition_id}/{register_id}")
async def api_competition_tickets(competition_id, register_id):
    competition = await get_competition(competition_id)
    if competition is None or not hmac.compare_digest(competition.register_id, register_id):
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Competition does not exist."
        )
    return [
        ticket.dict()
        for ticket in await get_wallet_competition_tickets(competition_id)
    ]


@bets4sats_ext.get("/api/v1/register/ticket/{ticket_id}")
async def api_competition_register_ticket(ticket_id):
    ticket = await get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Ticket does not exist."
        )

    return ticket.dict()
