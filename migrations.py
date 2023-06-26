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
            price_per_ticket INTEGER NOT NULL,
            sold INTEGER NOT NULL,
            time TIMESTAMP NOT NULL DEFAULT """
        + db.timestamp_now
        + """
        );
    """
    )


async def m002_changed(db):

    await db.execute(
        """
        CREATE TABLE bookie.ticket (
            id TEXT PRIMARY KEY,
            wallet TEXT NOT NULL,
            competition TEXT NOT NULL,
            name TEXT NOT NULL,
            reward_target TEXT NOT NULL,
            registered BOOLEAN NOT NULL,
            paid BOOLEAN NOT NULL,
            time TIMESTAMP NOT NULL DEFAULT """
        + db.timestamp_now
        + """
        );
    """
    )
