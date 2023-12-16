import asyncio

from fastapi import APIRouter
from fastapi.staticfiles import StaticFiles

from lnbits.db import Database
from lnbits.helpers import template_renderer
from lnbits.tasks import catch_everything_and_restart

db = Database("ext_bets4sats")


bets4sats_ext: APIRouter = APIRouter(prefix="/bets4sats", tags=["Bets4Sats"])

bets4sats_static_files = [
    {
        "path": "/bets4sats/static",
        "app": StaticFiles(packages=[("lnbits", "extensions/bets4sats/static")]),
        "name": "bets4sats_static",
    }
]


def bets4sats_renderer():
    return template_renderer(["lnbits/extensions/bets4sats/templates"])


from .tasks import wait_for_paid_invoices, wait_for_reward_ticket_ids, purge_tickets_loop
from .views import *  # noqa: F401,F403
from .views_api import *  # noqa: F401,F403


def bets4sats_start():
    loop = asyncio.get_event_loop()
    loop.create_task(catch_everything_and_restart(wait_for_paid_invoices))
    loop.create_task(catch_everything_and_restart(wait_for_reward_ticket_ids))
    loop.create_task(catch_everything_and_restart(purge_tickets_loop))
