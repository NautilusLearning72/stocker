-- Migrate symbols from legacy trading_universe into the Global instrument_universe.
-- Run once against the Postgres DB (psql -f backend/scripts/migrate_trading_universe_to_global.sql).

DO
$$
DECLARE
    global_id INTEGER;
BEGIN
    SELECT id
    INTO global_id
    FROM instrument_universe
    WHERE is_global = TRUE
      AND is_deleted = FALSE
    ORDER BY id
    LIMIT 1;

    IF global_id IS NULL THEN
        RAISE EXCEPTION 'Global universe not found (is_global=true, is_deleted=false)';
    END IF;

    INSERT INTO instrument_universe_member (universe_id, symbol, is_deleted, created_at)
    SELECT global_id, t.symbol, FALSE, now()
    FROM (SELECT DISTINCT symbol FROM trading_universe) t
    ON CONFLICT (universe_id, symbol) DO UPDATE
    SET is_deleted = FALSE,
        updated_at = now();
END;
$$;
