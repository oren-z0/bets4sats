import asyncio

from fastapi import APIRouter
from fastapi.staticfiles import StaticFiles

from lnbits.db import Database
from lnbits.helpers import template_renderer
from lnbits.tasks import catch_everything_and_restart

db = Database("ext_bookie")


bookie_ext: APIRouter = APIRouter(prefix="/bookie", tags=["Bookie"])

bookie_static_files = [
    {
        "path": "/bookie/static",
        "app": StaticFiles(packages=[("lnbits", "extensions/bookie/static")]),
        "name": "bookie_static",
    }
]


def bookie_renderer():
    return template_renderer(["lnbits/extensions/bookie/templates"])


from .tasks import wait_for_paid_invoices
from .views import *  # noqa: F401,F403
from .views_api import *  # noqa: F401,F403


def bookie_start():
    loop = asyncio.get_event_loop()
    loop.create_task(catch_everything_and_restart(wait_for_paid_invoices))
