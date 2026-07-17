-- 019: webhook idempotency key on sicredi_events.
-- Mirrors alembic revision 016_sicredi_event_webhook_id.
-- Indexed but NOT unique: redeliveries must remain insertable as audit rows.

ALTER TABLE sicredi_events
    ADD COLUMN IF NOT EXISTS webhook_event_id VARCHAR(100);

CREATE INDEX IF NOT EXISTS ix_sicredi_events_webhook_event_id
    ON sicredi_events (webhook_event_id);
