from psycopg2.extras import RealDictCursor


def get_oauth_account(conn, provider: str, provider_user_id: str) -> dict | None:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT provider, provider_user_id, user_id, email, email_verified, profile_name, profile_picture
            FROM oauth_account
            WHERE provider = %s AND provider_user_id = %s
            """,
            (provider, provider_user_id),
        )
        return cur.fetchone()


def upsert_oauth_account(
    conn,
    provider: str,
    provider_user_id: str,
    user_id: str,
    email: str | None,
    email_verified: bool,
    profile_name: str | None,
    profile_picture: str | None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO oauth_account
              (provider, provider_user_id, user_id, email, email_verified, profile_name, profile_picture)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (provider, provider_user_id)
            DO UPDATE SET
              user_id = EXCLUDED.user_id,
              email = EXCLUDED.email,
              email_verified = EXCLUDED.email_verified,
              profile_name = EXCLUDED.profile_name,
              profile_picture = EXCLUDED.profile_picture,
              updated_at = now(),
              last_login = now()
            """,
            (
                provider,
                provider_user_id,
                user_id,
                email,
                email_verified,
                profile_name,
                profile_picture,
            ),
        )
