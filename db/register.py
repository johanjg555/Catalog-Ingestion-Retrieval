import asyncpg



REGISTER_USER_SQL="""
Create table if not exists users(
    id serial primary key,
    username varchar(50) not null unique,
    email varchar(50) not null unique,
    disabled boolean not null,
    hashed_password varchar(255) not null
)
"""


async def check_and_create_table(pool: asyncpg.Pool) -> None:
    """Check if the target table exists, and create it if not."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(REGISTER_USER_SQL)