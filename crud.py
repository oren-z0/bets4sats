from typing import List, Optional, Union
import json
import datetime

import shortuuid
from lnbits.helpers import urlsafe_short_hash

from . import db
from .models import ChoiceAmountSum, CreateCompetition, Competition, Ticket, UpdateCompetition

# TICKETS

INVOICE_EXPIRY = 15 * 60 # 15 minutes
TICKET_PURGE_TIME = INVOICE_EXPIRY + 10 # safety 10 seconds more than ticket expiry

async def create_ticket(
    ticket_id: str, wallet: str, competition: str, amount: int, reward_target: str,
    choice: int,
) -> Ticket:
    await db.execute(
        """
        INSERT INTO bets4sats.tickets (id, wallet, competition, amount, reward_target, choice, state, reward_msat, reward_failure, reward_payment_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ticket_id, wallet, competition, amount, reward_target, choice, "INITIAL", 0, "", ""),
    )

    # UPDATE COMPETITION DATA ON NEW TICKET
    while True:
      competitiondata = await get_competition(competition)
      assert competitiondata, "Couldn't get competition from ticket being created"
      if competitiondata.state != "INITIAL":
          break
      amount_tickets = competitiondata.amount_tickets - 1
      update_result = await db.execute(
          """
          UPDATE bets4sats.competitions
          SET amount_tickets = ?
          WHERE id = ? AND amount_tickets = ? AND state = ?
          """,
          (amount_tickets, competition, competitiondata.amount_tickets, "INITIAL"),
      )
      if update_result.rowcount > 0:
          break

    ticket = await get_ticket(ticket_id)
    assert ticket, "Newly created ticket couldn't be retrieved"
    return ticket

async def purge_expired_tickets(competition_id: str) -> None:
    purge_time = datetime.datetime.now() - datetime.timedelta(seconds=TICKET_PURGE_TIME)
    delete_result = await db.execute(
        """
        DELETE FROM bets4sats.tickets
        WHERE competition = ? AND state = ? AND time < """ + db.timestamp_placeholder,
        (competition_id, "INITIAL", db.datetime_to_timestamp(purge_time))
    )
    if delete_result.rowcount <= 0:
        return
    while True:
      competitiondata = await get_competition(competition_id)
      assert competitiondata, "Couldn't get competition data for tickets being purged"
      amount_tickets = competitiondata.amount_tickets + delete_result.rowcount
      update_result = await db.execute(
          """
          UPDATE bets4sats.competitions
          SET amount_tickets = ?
          WHERE id = ? AND amount_tickets = ?
          """,
          (amount_tickets, competition_id, competitiondata.amount_tickets),
      )
      if update_result.rowcount > 0:
          break

async def set_ticket_funded(ticket_id: str) -> None:
    cas_success = await cas_ticket_state(ticket_id, "INITIAL", "FUNDED")
    if not cas_success:
        return
    ticket = await get_ticket(ticket_id)

    # UPDATE COMPETITION DATA ON SOLD TICKET
    while True:
      competitiondata = await get_competition(ticket.competition)
      assert competitiondata, "Couldn't get competition from ticket being paid"
      if competitiondata.state != "INITIAL":
          break
      sold = competitiondata.sold + 1
      choices = json.loads(competitiondata.choices)
      choices[choice]["total"] += ticket.amount
      update_result = await db.execute(
          """
          UPDATE bets4sats.competitions
          SET sold = ?, choices = ?
          WHERE id = ? AND sold = ? AND state = ?
          """,
          (sold, json.dumps(choices), ticket.competition, competitiondata.sold, "INITIAL"),
      )
      if update_result.rowcount > 0:
          break

async def cas_ticket_state(ticket_id: str, old_state: str, new_state: str) -> bool:
    update_result = await db.execute(
        """
        UPDATE bets4sats.tickets
        SET state = ?
        WHERE id = ? AND state = ?
        """,
        (new_state, ticket_id, old_state)
    )
    return update_result.rowcount > 0

async def update_ticket(ticket_id: str, **kwargs) -> Ticket:
    q = ", ".join([f"{field[0]} = ?" for field in kwargs.items()])
    await db.execute(
        f"UPDATE bets4sats.tickets SET {q} WHERE id = ?", (*kwargs.values(), ticket_id)
    )
    ticket = await get_ticket(ticket_id)
    assert ticket, "Newly updated ticket couldn't be retrieved"
    return ticket


async def get_ticket(ticket_id: str) -> Optional[Ticket]:
    row = await db.fetchone("SELECT * FROM bets4sats.tickets WHERE id = ?", (ticket_id,))
    return Ticket(**row) if row else None


async def get_tickets(wallet_ids: Union[str, List[str]]) -> List[Ticket]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]

    q = ",".join(["?"] * len(wallet_ids))
    rows = await db.fetchall(
        f"SELECT * FROM bets4sats.tickets WHERE wallet IN ({q})", (*wallet_ids,)
    )
    return [Ticket(**row) for row in rows]


async def delete_ticket(ticket_id: str) -> None:
    await db.execute("DELETE FROM bets4sats.tickets WHERE id = ?", (ticket_id,))


async def delete_competition_tickets(competition_id: str) -> None:
    await db.execute("DELETE FROM bets4sats.tickets WHERE competition = ?", (competition_id,))


# COMPETITIONS


async def create_competition(data: CreateCompetition) -> Competition:
    competition_id = urlsafe_short_hash()
    register_id = shortuuid.random()
    await db.execute(
        """
        INSERT INTO bets4sats.competitions (id, wallet, register_id, name, info, banner, closing_datetime, amount_tickets, min_bet, max_bet, sold, choices, winning_choice, state)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            competition_id,
            data.wallet,
            register_id,
            data.name,
            data.info,
            data.banner,
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


async def update_competition(competition_id: str, data: UpdateCompetition) -> Optional[Competition]:
    query, values = zip(
        *([["amount_tickets = ?", data.amount_tickets]] if data.amount_tickets is not None else []),
        *([["closing_datetime = ?", data.closing_datetime]] if data.closing_datetime is not None else []),
    )
    if not query:
        return await get_competition(competition_id)
    
    update_result = await db.execute(
        f"UPDATE bets4sats.competitions SET {', '.join(query)} WHERE id = ? AND state = ?",
        (*values, competition_id, "INITIAL"),
    )
    if update_result.rowcount == 0:
        return None
    
    return await get_competition(competition_id)

async def cas_competition_state(competition_id: str, old_state: str, new_state: str) -> bool:
    update_result = await db.execute(
        """
        UPDATE bets4sats.competitions
        SET state = ?
        WHERE id = ? AND state = ?
        """,
        (new_state, competition_id, old_state)
    )
    return update_result.rowcount > 0

async def set_winning_choice(competition_id: str, winning_choice: int) -> None:
    await db.execute(
        """
        UPDATE bets4sats.competitions
        SET winning_choice = ?
        WHERE id = ?
        """,
        (winning_choice, competition_id)
    )

async def sum_choices_amounts(competition_id: str) -> List[ChoiceAmountSum]:
    choices = await db.fetchall(
        """
        SELECT choice, SUM(amount) amount_sum
        FROM bets4sats.tickets
        WHERE competition = ?
        GROUP BY choice
        """,
        (competition_id,),        
    )
    return [ChoiceAmountSum(**choice) for choice in choices]

async def update_competition_winners(competition_id: str, choices: str, winning_choice: int):
    await db.execute(
        """
        UPDATE bets4sats.competitions
        SET choices = ?, winning_choice = ?
        WHERE id = ?
        """,
        (choices, winning_choice, competition_id)
    )
    if winning_choice < 0:
        await db.execute(
            """
            UPDATE bets4sats.tickets
            SET state = ?
            WHERE competition = ? AND state = ?
            """,
            ("CANCELLED_UNPAID", competition_id, "FUNDED")
        )
    else:
        await db.execute(
            """
            UPDATE bets4sats.tickets
            SET state = ?
            WHERE competition = ? AND state = ? AND choice = ?
            """,
            ("WON_UNPAID", competition_id, "FUNDED", winning_choice)
        )
        await db.execute(
            """
            UPDATE bets4sats.tickets
            SET state = ?
            WHERE competition = ? AND state = ? AND choice != ?
            """,
            ("LOST", competition_id, "FUNDED", winning_choice)
        )


async def get_competition(competition_id: str) -> Optional[Competition]:
    row = await db.fetchone("SELECT * FROM bets4sats.competitions WHERE id = ?", (competition_id,))
    return Competition(**row) if row else None


async def get_competitions(wallet_ids: Union[str, List[str]]) -> List[Competition]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]

    q = ",".join(["?"] * len(wallet_ids))
    rows = await db.fetchall(
        f"SELECT * FROM bets4sats.competitions WHERE wallet IN ({q})", (*wallet_ids,)
    )

    return [Competition(**row) for row in rows]


async def get_all_competitions() -> List[Competition]:
    rows = await db.fetchall(
        f"SELECT * FROM bets4sats.competitions",
    )
    return [Competition(**row) for row in rows]

async def delete_competition(competition_id: str) -> None:
    await db.execute("DELETE FROM bets4sats.competitions WHERE id = ?", (competition_id,))


# COMPETITIONTICKETS


async def get_wallet_competition_tickets(competition_id: str) -> List[Ticket]:
    rows = await db.fetchall(
        "SELECT * FROM bets4sats.tickets WHERE competition = ?",
        (competition_id,),
    )
    return [Ticket(**row) for row in rows]

async def get_state_competition_tickets(competition_id: str, states: List[str]) -> List[Ticket]:
    assert len(states) > 0, "get_state_competition_tickets called with no states"
    query = " OR ".join(["state = ?" for _state in states])
    rows = await db.fetchall(
        f"SELECT * FROM bets4sats.tickets WHERE competition = ? AND ({query})",
        (competition_id, *states),
    )
    return [Ticket(**row) for row in rows]

async def is_competition_payment_complete(competition_id: str) -> List[Ticket]:
    row = await db.fetchone(
        "SELECT id FROM bets4sats.tickets WHERE competition = ? AND state != ? AND state != ? AND state != ? AND state != ? AND state != ? LIMIT 1",
        (competition_id, "CANCELLED_PAID", "CANCELLED_PAYMENT_FAILED", "WON_PAID", "WON_PAYMENT_FAILED", "LOST"),
    )
    return not row
