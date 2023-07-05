import asyncio
import json

from lnbits.core.models import Payment
from lnbits.helpers import get_current_extension_name
from lnbits.tasks import register_invoice_listener
from loguru import logger

from .crud import cas_competition_state, get_ticket, cas_ticket_state, get_competition, update_ticket, is_competition_payment_complete
from .helpers import pay_lnurlp, send_ticket

PRIZE_FEE_PERCENT = 1

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
        and "bookie" == payment.extra.get("tag")
        and isinstance(payment.extra.get("reward_target"), str)
        and isinstance(payment.extra.get("choice"), int)
        and payment.memo and payment.memo.startswith("BookieTicketId:")
    ):
        competition_id, ticket_id = (payment.memo[len("BookieTicketId:"):].split(".") + [""])[:2]
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
    logger.info("on_reward_ticket_id: called", ticket_id)
    ticket = await get_ticket(ticket_id)
    if not ticket:
        logger.warning("on_reward_ticket_id: ticket not found, deleted before handled?", ticket_id)
        return
    logger.info("on_reward_ticket_id: handling ticket:", ticket)
    new_state = {
        "WON_UNPAID": "WON_PAYING",
        "WON_PAYMENT_FAILED": "WON_PAYING",
        "CANCELLED_UNPAID": "CANCELLED_PAYING",
        "CANCELLED_PAYMENT_FAILED": "CANCELLED_PAYING"
    }.get(ticket.state)
    logger.info("on_reward_ticket_id: new state:", ticket_id, new_state)
    if not new_state:
        return
    cas_success = await cas_ticket_state(ticket_id, ticket.state, new_state)
    if not cas_success:
        logger.info("on_reward_ticket_id: cas failed:", ticket_id)
        return
    final_reward_msat = 0
    try:
        # get ticket again
        ticket = await get_ticket(ticket_id)
        if not ticket:
            logger.info("on_reward_ticket_id: failed to re-get ticket:", ticket_id)
            return
        if ticket.state == "CANCELLED_PAYING":
            reward_msat = ticket.amount * 1000
            description_prefix = "BookieRefund"
        else: # WON_PAYING
            competition = await get_competition(ticket.competition)
            choices = json.loads(competition.choices)
            total_msat = sum(choice["total"] for choice in choices) * 1000
            reward_msat = total_msat * ticket.amount * (100 - PRIZE_FEE_PERCENT) // (choices[ticket.choice]["total"] * 100)
            description_prefix = "BookieReward"
        logger.info("on_reward_ticket_id: paying lnurlp:", ticket_id)
        payment_hash, final_reward_msat = await pay_lnurlp(
            ticket.wallet,
            ticket.reward_target,
            reward_msat,
            f"{description_prefix}:{ticket.competition}.{ticket.id}",
            {"tag":"bookie"}
        )
    except Exception as exception:
        logger.warning("on_reward_ticket_id: failed:", ticket_id, exception)
        await update_ticket(
            ticket_id,
            state={
                "CANCELLED_PAYING": "CANCELLED_PAYMENT_FAILED",
                "WON_PAYING": "WON_PAYMENT_FAILED"
            }[ticket.state],
            reward_failure=str(exception)
        )
    else:
        logger.warning("on_reward_ticket_id: updating ticket to paid:", ticket_id)
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
    logger.warning("on_reward_ticket_id: competition_complete:", ticket_id, competition_complete)
    if competition_complete:
        await cas_competition_state(
            ticket.competition,
            old_state="COMPLETED_PAYING",
            state="COMPLETED_PAID"
        )
