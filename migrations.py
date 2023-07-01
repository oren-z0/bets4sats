async def m001_initial(db):
    await db.execute(
        """
        CREATE TABLE bookie.competitions (
            id TEXT PRIMARY KEY,
            wallet TEXT NOT NULL,
            name TEXT NOT NULL,
            info TEXT NOT NULL,
            closing_datetime TEXT NOT NULL,
            amount_tickets INTEGER NOT NULL,
            min_bet INTEGER NOT NULL,
            max_bet INTEGER NOT NULL,
            sold INTEGER NOT NULL,
            choices TEXT NOT NULL,
            winning_choice INTEGER NOT NULL,
            state TEXT NOT NULL,
            time TIMESTAMP NOT NULL DEFAULT """
        + db.timestamp_now
        + """
        );
    """
    )


async def m002_changed(db):
    await db.execute(
        """
        CREATE TABLE bookie.tickets (
            id TEXT PRIMARY KEY,
            wallet TEXT NOT NULL,
            competition TEXT NOT NULL,
            amount INTEGER NOT NULL,
            reward_target TEXT NOT NULL,
            choice INTEGER NOT NULL,
            state TEXT NOT NULL,
            reward_msat INTEGER NOT NULL,
            reward_failure TEXT NOT NULL,
            reward_payment_hash TEXT NOT NULL,
            time TIMESTAMP NOT NULL DEFAULT """
        + db.timestamp_now
        + """
        );
    """
    )
