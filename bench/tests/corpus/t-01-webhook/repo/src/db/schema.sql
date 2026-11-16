-- payments: ~40 million rows in production
CREATE TABLE payments (
    id          BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    amount_cents BIGINT NOT NULL,
    status      TEXT NOT NULL,          -- pending | succeeded | refunded | disputed
    updated_at  TIMESTAMP NOT NULL
);
