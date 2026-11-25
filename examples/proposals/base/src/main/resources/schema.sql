-- Version 1
CREATE TABLE IF NOT EXISTS links (
    code VARCHAR(12) PRIMARY KEY,
    destination VARCHAR(4096) NOT NULL,
    redirects BIGINT NOT NULL DEFAULT 0 CHECK (redirects >= 0)
);
