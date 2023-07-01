from urllib.parse import urlparse
import json

from lnbits import lnurl
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
            raise Exception("Unparseable lnurlp or lightning-address")
    parsed_url = urlparse(url)
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

