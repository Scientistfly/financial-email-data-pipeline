from sqlalchemy import text
from sqlalchemy.orm import Session

RLS_TABLES = [
    "oauth_credentials",
    "debug_emails",
    "households",
    "users",
    "merchant_aliases",
    "transactions",
]

def apply_rls_and_policies(db: Session) -> None:
    """
    Enables RLS and creates safe default policies.
    Run once after tables exist (or on startup with IF NOT EXISTS guards).
    """

    # 1) Enable RLS on all tables
    for t in RLS_TABLES:
        db.execute(text(f'ALTER TABLE public."{t}" ENABLE ROW LEVEL SECURITY;'))

    # 2) Policies
    # NOTE: These policies assume you're using Supabase Auth (auth.uid()).
    # If you are NOT using Supabase Auth, skip policies and keep data private by schema + service_role.

    # oauth_credentials: user can only access their own rows
    db.execute(text("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public'
          AND tablename='oauth_credentials'
          AND policyname='user_owns_oauth_credentials'
      ) THEN
        CREATE POLICY user_owns_oauth_credentials
        ON public.oauth_credentials
        FOR ALL
        USING (auth.uid() = user_id)
        WITH CHECK (auth.uid() = user_id);
      END IF;
    END $$;
    """))

    # debug_emails: user can only access their own rows
    db.execute(text("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public'
          AND tablename='debug_emails'
          AND policyname='user_owns_debug_emails'
      ) THEN
        CREATE POLICY user_owns_debug_emails
        ON public.debug_emails
        FOR ALL
        USING (auth.uid() = user_id)
        WITH CHECK (auth.uid() = user_id);
      END IF;
    END $$;
    """))

    # transactions: user can only access their own rows
    db.execute(text("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public'
          AND tablename='transactions'
          AND policyname='user_owns_transactions'
      ) THEN
        CREATE POLICY user_owns_transactions
        ON public.transactions
        FOR ALL
        USING (auth.uid() = user_id)
        WITH CHECK (auth.uid() = user_id);
      END IF;
    END $$;
    """))

    # merchant_aliases: allow access by household membership
    # This one is a bit more complex: user can read/write aliases for their household.
    db.execute(text("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public'
          AND tablename='merchant_aliases'
          AND policyname='household_owns_aliases'
      ) THEN
        CREATE POLICY household_owns_aliases
        ON public.merchant_aliases
        FOR ALL
        USING (
          EXISTS (
            SELECT 1 FROM public.users u
            WHERE u.id = auth.uid()
              AND u.household_id = merchant_aliases.household_id
          )
        )
        WITH CHECK (
          EXISTS (
            SELECT 1 FROM public.users u
            WHERE u.id = auth.uid()
              AND u.household_id = merchant_aliases.household_id
          )
        );
      END IF;
    END $$;
    """))

    db.commit()