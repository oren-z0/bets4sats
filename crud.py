from typing import List, Optional, Union
import json

from lnbits.helpers import urlsafe_short_hash

from . import db
from .models import CreateCompetition, Competition, Ticket

# TICKETS


async def create_ticket(
    ticket_id: str, wallet: str, competition: str, amount: int, reward_target: str,
    choice: int,
) -> Ticket:
    await db.execute(
        """
        INSERT INTO bookie.tickets (id, wallet, competition, amount, reward_target, choice, state, reward_msat, reward_failure, reward_payment_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ticket_id, wallet, competition, amount, reward_target, choice, "INITIAL", 0, "", ""),
    )

    # UPDATE COMPETITION DATA ON SOLD TICKET
    while True:
      competitiondata = await get_competition(competition)
      assert competitiondata, "Couldn't get competition from ticket being paid"
      sold = competitiondata.sold + 1
      amount_tickets = competitiondata.amount_tickets - 1
      choices = json.loads(competitiondata.choices)
      choices[choice]["total"] += amount
      update_result = await db.execute(
          """
          UPDATE bookie.competitions
          SET sold = ?, amount_tickets = ?, choices = ?
          WHERE id = ? AND amount_tickets = ?
          """,
          (sold, amount_tickets, json.dumps(choices), competition, competitiondata.amount_tickets),
      )
      if update_result.rowcount > 0:
          break

    ticket = await get_ticket(ticket_id)
    assert ticket, "Newly created ticket couldn't be retrieved"
    return ticket

async def cas_ticket_state(ticket_id: str, old_state: str, new_state: str) -> bool:
    update_result = await db.execute(
        """
        UPDATE bookie.tickets
        SET state = ?
        WHERE id = ? AND state = ?
        """,
        (old_state, ticket_id, new_state)
    )
    return update_result.rowcount > 0

async def update_ticket(ticket_id: str, **kwargs) -> Ticket:
    q = ", ".join([f"{field[0]} = ?" for field in kwargs.items()])
    await db.execute(
        f"UPDATE bookie.tickets SET {q} WHERE id = ?", (*kwargs.values(), ticket_id)
    )
    ticket = await get_ticket(ticket_id)
    assert ticket, "Newly updated ticket couldn't be retrieved"
    return ticket


async def get_ticket(ticket_id: str) -> Optional[Ticket]:
    row = await db.fetchone("SELECT * FROM bookie.tickets WHERE id = ?", (ticket_id,))
    return Ticket(**row) if row else None


async def get_tickets(wallet_ids: Union[str, List[str]]) -> List[Ticket]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]

    q = ",".join(["?"] * len(wallet_ids))
    rows = await db.fetchall(
        f"SELECT * FROM bookie.tickets WHERE wallet IN ({q})", (*wallet_ids,)
    )
    return [Ticket(**row) for row in rows]


async def delete_ticket(ticket_id: str) -> None:
    await db.execute("DELETE FROM bookie.tickets WHERE id = ?", (ticket_id,))


async def delete_competition_tickets(competition_id: str) -> None:
    await db.execute("DELETE FROM bookie.tickets WHERE competition = ?", (competition_id,))


# COMPETITIONS


async def create_competition(data: CreateCompetition) -> Competition:
    competition_id = urlsafe_short_hash()
    await db.execute(
        """
        INSERT INTO bookie.competitions (id, wallet, name, info, closing_datetime, amount_tickets, min_bet, max_bet, sold, choices, winning_choice, state)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            competition_id,
            data.wallet,
            data.name,
            data.info,
            data.closing_datetime,
            data.amount_tickets,
            data.min_bet,
            data.max_bet,
            0,
            json.dumps([{ "title": choice["title"], "total": 0 } for choice in json.loads(data.choices)]),
            -1,
            "INITIAL"
        ),
    )

    competition = await get_competition(competition_id)
    assert competition, "Newly created competition couldn't be retrieved"
    return competition


async def update_competition(competition_id: str, **kwargs) -> Competition:
    q = ", ".join([f"{field[0]} = ?" for field in kwargs.items()])
    await db.execute(
        f"UPDATE bookie.competitions SET {q} WHERE id = ?", (*kwargs.values(), competition_id)
    )
    competition = await get_competition(competition_id)
    assert competition, "Newly updated competition couldn't be retrieved"
    return competition


async def get_competition(competition_id: str) -> Optional[Competition]:
    row = await db.fetchone("SELECT * FROM bookie.competitions WHERE id = ?", (competition_id,))
    return Competition(**row) if row else None


async def get_competitions(wallet_ids: Union[str, List[str]]) -> List[Competition]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]

    q = ",".join(["?"] * len(wallet_ids))
    rows = await db.fetchall(
        f"SELECT * FROM bookie.competitions WHERE wallet IN ({q})", (*wallet_ids,)
    )

    return [Competition(**row) for row in rows]


async def delete_competition(competition_id: str) -> None:
    await db.execute("DELETE FROM bookie.competitions WHERE id = ?", (competition_id,))


# COMPETITIONTICKETS


async def get_wallet_competition_tickets(competition_id: str, wallet_id: str) -> List[Ticket]:
    rows = await db.fetchall(
        "SELECT * FROM bookie.tickets WHERE wallet = ? AND competition = ?",
        (wallet_id, competition_id),
    )
    return [Ticket(**row) for row in rows]

async def is_competition_payment_complete(competition_id: str) -> List[Ticket]:
    rows = await db.fetchall(
        "SELECT id FROM bookie.tickets WHERE competition = ? AND state != ? AND state != ? AND state != ? AND state != ? LIMIT 1",
        (competition_id, "CANCELLED_PAID", "CANCELLED_PAYMENT_FAILED", "WON_PAID", "WON_PAYMENT_FAILED"),
    )
    return not rows
