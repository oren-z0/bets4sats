from typing import Dict, Optional
from datetime import datetime
from http import HTTPStatus
from urllib.parse import urlparse, quote
import json

from lnbits import lnurl, bolt11
from lnbits.core.services import fee_reserve, pay_invoice
from lnbits.core.crud import get_payments
from lnbits.core.models import PaymentFilters
from lnbits.db import Filters, Filter
from starlette.exceptions import HTTPException
import httpx
from loguru import logger

from .crud import create_ticket, get_competition, get_ticket
from .models import LnurlpParameters

# Similar to /api/v1/lnurlscan/{code}
async def get_lnurlp_parameters(code: str) -> LnurlpParameters:
    try:
        url = lnurl.decode(code)
    except:
        name_domain = code.split("@")
        if len(name_domain) == 2 and len(name_domain[1].split(".")) >= 2:
            name, domain = name_domain
            url = (
                ("http://" if domain.endswith(".onion") else "https://")
                + domain
                + "/.well-known/lnurlp/"
                + name
            )
        else:
            raise Exception("Malformed lnurlp or lightning-address")
    try:
        parsed_url = urlparse(url)
    except:
        raise Exception("Unparsable lnurlp or lightning-address")
    if "tag=login" in parsed_url.query.split("&"):
        raise Exception("Invalid lnurlp - this is a login lnurl")
    async with httpx.AsyncClient() as client:
        r = await client.get(url, timeout=5)
        if r.is_error:
            raise Exception("Failed to get lnurlp parameters")
    try:
        data = json.loads(r.text)
    except json.decoder.JSONDecodeError:
        raise Exception("Failed to decode lnurlp parameters json")
    
    if not isinstance(data, dict):
        raise Exception("Failed to decode lnurlp parameters object")

    if data.get("tag") != "payRequest":
        raise Exception("Unexpected lnurlp tag: should be payRequest")
    
    minSendable = data.get("minSendable")
    maxSendable = data.get("maxSendable")
    callback = data.get("callback")
    commentAllowed = data.get("commentAllowed")

    if not isinstance(minSendable, int) or not isinstance(maxSendable, int) or not isinstance(callback, str):
        raise Exception("Unexpected lnurlp parameters types")
    
    return LnurlpParameters(
        minSendable=minSendable,
        maxSendable=maxSendable,
        callback=callback,
        commentAllowed=commentAllowed if isinstance(commentAllowed, int) else 0,
    )

async def pay_lnurlp(wallet_id: str, code: str, amount_msat: int, description: str, extra: Optional[Dict]) -> tuple[str, int]:
    # Deduct lightning fees
    # This may actually deduct too much, because the final fee will be
    # fee_reserve(final_amount_msat) <= fee_reserve(amount_msat), but the exact calculation
    # might get complicated if fee_reserve changes.
    logger.info(f"pay_lnurlp: called {code} {amount_msat} {description} {extra}")
    final_amount_msat = amount_msat - fee_reserve(amount_msat)
    logger.info(f"pay_lnurlp: final-amount-msat: {final_amount_msat}")
    if final_amount_msat <= 0:
        raise Exception("Payment is negative or zero after deducting lightning fees")
    params = await get_lnurlp_parameters(code)
    if final_amount_msat < params.minSendable:
        raise Exception("Payment is too small for receiver")
    if final_amount_msat > params.maxSendable:
        raise Exception("Payment is too high for receiver")
    try:
        parsed_callback = urlparse(params.callback)
    except:
        raise Exception("Unparsable lnurlp callback")
    comment = description if len(description) <= params.commentAllowed else ""
    full_callback_url = params.callback + ("&" if parsed_callback.query else "?") + f"amount={amount_msat}" + (
        f"&comment={quote(comment)}" if comment else ""
    )
    async with httpx.AsyncClient() as client:
        r = await client.get(full_callback_url, timeout=5)
        if r.is_error:
            raise Exception("Failed to call callback url")
    try:
        data = json.loads(r.text)
    except json.decoder.JSONDecodeError:
        raise Exception("Failed to decode callback response json")
    if not isinstance(data, dict):
        raise Exception("Failed to decode callback response object")
    pr = data.get("pr")
    if not isinstance(pr, str):
        raise Exception("Unexpected callback response parameters types")
    logger.info(f"pay_lnurlp: decoding pr {pr}")
    try:
        decoded_payment_request = bolt11.decode(pr)
    except:
        raise Exception("Failed to parse bolt11 payment request")
    logger.info(f"pay_lnurlp: decoded pr: {decoded_payment_request}")
    if decoded_payment_request.amount_msat > final_amount_msat:
        raise Exception("Amount in invoice is higher than requested")
    logger.info("pay_lnurlp: paying invoice")
    # Should we check invoice description?
    payment_hash = await pay_invoice(
        wallet_id=wallet_id,
        payment_request=pr,
        description=description,
        extra=extra,
        max_sat=(amount_msat // 1000) + 1, # safety
    )
    return payment_hash, final_amount_msat

# Used both in api and in tasks:
async def send_ticket(competition_id, ticket_id):
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
    # Danger: Not safe against parallel requests
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
