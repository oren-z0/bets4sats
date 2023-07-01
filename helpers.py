from typing import Dict, Optional
from urllib.parse import urlparse, quote
import json

from lnbits import lnurl, bolt11
from lnbits.core.services import fee_reserve, pay_invoice
import httpx
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
    final_amount_msat = amount_msat - fee_reserve(amount_msat)
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
    try:
        decoded_payment_request = bolt11.decode(pr)
    except:
        raise Exception("Failed to parse bolt11 payment request")
    if decoded_payment_request.amount_msat > final_amount_msat:
        raise Exception("Amount in invoice is higher than requested")
    # Should we check invoice description?
    payment_hash = await pay_invoice(
        wallet_id=wallet_id,
        payment_request=pr,
        description=description,
        extra=extra,
        max_sat=(amount_msat // 1000) + 1, # safety
    )
    return payment_hash, final_amount_msat


