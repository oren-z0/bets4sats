import asyncio
import json
from time import sleep

from lnbits.core.models import Payment
from lnbits.helpers import get_current_extension_name
from lnbits.tasks import register_invoice_listener
from loguru import logger

from .crud import cas_competition_state, get_ticket, cas_ticket_state, get_competition, update_ticket, is_competition_payment_complete, get_all_competitions, TICKET_PURGE_TIME
from .helpers import pay_lnurlp, send_ticket

PRIZE_FEE_PERCENT = 1

async def purge_tickets_loop():
    while True:
        sleep(TICKET_PURGE_TIME // 2)
        await competitions = await get_all_competitions()
        for competition in competitions:
            await purge_expired_tickets(competition.id)

reward_ticket_ids_queue = asyncio.Queue()

async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    register_invoice_listener(invoice_queue, get_current_extension_name())

    while True:
        payment = await invoice_queue.get()
        await on_invoice_paid(payment)


async def on_invoice_paid(payment: Payment) -> None:
    # (avoid loops)
    if (
        payment.extra
        and "bets4sats" == payment.extra.get("tag")
        and isinstance(payment.extra.get("reward_target"), str)
        and isinstance(payment.extra.get("choice"), int)
        and payment.memo and payment.memo.startswith("Bets4SatsTicketId:")
    ):
        competition_id, ticket_id = (payment.memo[len("Bets4SatsTicketId:"):].split(".") + [""])[:2]
        await send_ticket(
            competition_id,
            ticket_id,
        )
    return

async def wait_for_reward_ticket_ids():
    logger.info("wait_for_reward_ticket_ids: started")
    while True:
        ticket_id = await reward_ticket_ids_queue.get()
        await on_reward_ticket_id(ticket_id)

async def on_reward_ticket_id(ticket_id: str) -> None:
    logger.info(f"on_reward_ticket_id: called {ticket_id}")
    ticket = await get_ticket(ticket_id)
    if not ticket:
        logger.warning(f"on_reward_ticket_id: ticket not found, deleted before handled? {ticket_id}")
        return
    logger.info(f"on_reward_ticket_id: handling ticket: {ticket}")
    new_state = {
        "WON_UNPAID": "WON_PAYING",
        "WON_PAYMENT_FAILED": "WON_PAYING",
        "CANCELLED_UNPAID": "CANCELLED_PAYING",
        "CANCELLED_PAYMENT_FAILED": "CANCELLED_PAYING"
    }.get(ticket.state)
    logger.info(f"on_reward_ticket_id: new state: {ticket_id} {new_state}")
    if not new_state:
        return
    cas_success = await cas_ticket_state(ticket_id, ticket.state, new_state)
    if not cas_success:
        logger.info(f"on_reward_ticket_id: cas failed: {ticket_id}")
        return
    final_reward_msat = 0
    try:
        # get ticket again
        ticket = await get_ticket(ticket_id)
        if not ticket:
            logger.info(f"on_reward_ticket_id: failed to re-get ticket: {ticket_id}")
            return
        if ticket.state == "CANCELLED_PAYING":
            reward_msat = ticket.amount * 1000
            description_prefix = "Bets4SatsRefund"
        else: # WON_PAYING
            competition = await get_competition(ticket.competition)
            logger.info(f"on_reward_ticket_id: got competition: {ticket_id} {competition}")
            choices = json.loads(competition.choices)
            logger.info(f"on_reward_ticket_id: calculating reward: {ticket_id}")
            total_msat = sum(choice["total"] for choice in choices) * 1000
            reward_msat = total_msat * ticket.amount * (100 - PRIZE_FEE_PERCENT) // (choices[ticket.choice]["total"] * 100)
            description_prefix = "Bets4SatsReward"
        logger.info(f"on_reward_ticket_id: reward_msat: {ticket_id} {reward_msat}")
        logger.info(f"on_reward_ticket_id: paying lnurlp: {ticket_id}")
        payment_hash, final_reward_msat = await pay_lnurlp(
            ticket.wallet,
            ticket.reward_target,
            reward_msat,
            f"{description_prefix}:{ticket.competition}.{ticket.id}",
            {"tag":"bets4sats"}
        )
    except Exception as exception:
        logger.warning(f"on_reward_ticket_id: failed: {ticket_id} {exception}")
        await update_ticket(
            ticket_id,
            state={
                "CANCELLED_PAYING": "CANCELLED_PAYMENT_FAILED",
                "WON_PAYING": "WON_PAYMENT_FAILED"
            }[ticket.state],
            reward_failure=str(exception)
        )
    else:
        logger.info(f"on_reward_ticket_id: updating ticket to paid: {ticket_id}")
        await update_ticket(
            ticket.id,
            state={
                "CANCELLED_PAYING": "CANCELLED_PAID",
                "WON_PAYING": "WON_PAID"
            }[ticket.state],
            reward_failure="",
            reward_msat=final_reward_msat,
            reward_payment_hash=payment_hash
        )
    competition_complete = await is_competition_payment_complete(ticket.competition)
    logger.info(f"on_reward_ticket_id: competition_complete: {ticket_id} {competition_complete}")
    if competition_complete:
        await cas_competition_state(
            ticket.competition,
            "COMPLETED_PAYING",
            "COMPLETED_PAID"
        )
