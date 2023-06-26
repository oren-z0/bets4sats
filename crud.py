from typing import List, Optional, Union

from lnbits.helpers import urlsafe_short_hash

from . import db
from .models import CreateCompetition, Competitions, Tickets

# TICKETS


async def create_ticket(
    payment_hash: str, wallet: str, competition: str, name: str, reward_target: str
) -> Tickets:
    await db.execute(
        """
        INSERT INTO bookie.ticket (id, wallet, competition, name, reward_target, registered, paid)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (payment_hash, wallet, competition, name, reward_target, False, True),
    )

    # UPDATE COMPETITION DATA ON SOLD TICKET
    competitiondata = await get_competition(competition)
    assert competitiondata, "Couldn't get competition from ticket being paid"
    sold = competitiondata.sold + 1
    amount_tickets = competitiondata.amount_tickets - 1
    await db.execute(
        """
        UPDATE bookie.competitions
        SET sold = ?, amount_tickets = ?
        WHERE id = ?
        """,
        (sold, amount_tickets, competition),
    )

    ticket = await get_ticket(payment_hash)
    assert ticket, "Newly created ticket couldn't be retrieved"
    return ticket


async def get_ticket(payment_hash: str) -> Optional[Tickets]:
    row = await db.fetchone("SELECT * FROM bookie.ticket WHERE id = ?", (payment_hash,))
    return Tickets(**row) if row else None


async def get_tickets(wallet_ids: Union[str, List[str]]) -> List[Tickets]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]

    q = ",".join(["?"] * len(wallet_ids))
    rows = await db.fetchall(
        f"SELECT * FROM bookie.ticket WHERE wallet IN ({q})", (*wallet_ids,)
    )
    return [Tickets(**row) for row in rows]


async def delete_ticket(payment_hash: str) -> None:
    await db.execute("DELETE FROM bookie.ticket WHERE id = ?", (payment_hash,))


async def delete_competition_tickets(competition_id: str) -> None:
    await db.execute("DELETE FROM bookie.ticket WHERE competition = ?", (competition_id,))


# COMPETITIONS


async def create_competition(data: CreateCompetition) -> Competitions:
    competition_id = urlsafe_short_hash()
    await db.execute(
        """
        INSERT INTO bookie.competitions (id, wallet, name, info, closing_datetime, amount_tickets, price_per_ticket, sold)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            competition_id,
            data.wallet,
            data.name,
            data.info,
            data.closing_datetime,
            data.amount_tickets,
            data.price_per_ticket,
            0,
        ),
    )

    competition = await get_competition(competition_id)
    assert competition, "Newly created competition couldn't be retrieved"
    return competition


async def update_competition(competition_id: str, **kwargs) -> Competitions:
    q = ", ".join([f"{field[0]} = ?" for field in kwargs.items()])
    await db.execute(
        f"UPDATE bookie.competitions SET {q} WHERE id = ?", (*kwargs.values(), competition_id)
    )
    competition = await get_competition(competition_id)
    assert competition, "Newly updated competition couldn't be retrieved"
    return competition


async def get_competition(competition_id: str) -> Optional[Competitions]:
    row = await db.fetchone("SELECT * FROM bookie.competitions WHERE id = ?", (competition_id,))
    return Competitions(**row) if row else None


async def get_competitions(wallet_ids: Union[str, List[str]]) -> List[Competitions]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]

    q = ",".join(["?"] * len(wallet_ids))
    rows = await db.fetchall(
        f"SELECT * FROM bookie.competitions WHERE wallet IN ({q})", (*wallet_ids,)
    )

    return [Competitions(**row) for row in rows]


async def delete_competition(competition_id: str) -> None:
    await db.execute("DELETE FROM bookie.competitions WHERE id = ?", (competition_id,))


# COMPETITIONTICKETS


async def get_wallet_competition_tickets(competition_id: str, wallet_id: str) -> List[Tickets]:
    rows = await db.fetchall(
        "SELECT * FROM bookie.ticket WHERE wallet = ? AND competition = ?",
        (wallet_id, competition_id),
    )
    return [Tickets(**row) for row in rows]


async def reg_ticket(ticket_id: str) -> List[Tickets]:
    await db.execute(
        "UPDATE bookie.ticket SET registered = ? WHERE id = ?", (True, ticket_id)
    )
    ticket = await db.fetchone("SELECT * FROM bookie.ticket WHERE id = ?", (ticket_id,))
    rows = await db.fetchall(
        "SELECT * FROM bookie.ticket WHERE competition = ?", (ticket[1],)
    )
    return [Tickets(**row) for row in rows]
