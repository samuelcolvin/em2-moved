DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
CREATE EXTENSION pgcrypto;

CREATE TYPE ACCOUNT_STATUS AS ENUM ('pending', 'active', 'suspended');

CREATE TABLE auth_users (
  id SERIAL PRIMARY KEY,
  address VARCHAR(255) NOT NULL UNIQUE,
  first_name VARCHAR(63),
  last_name VARCHAR(63),
  password_hash VARCHAR(63),
  otp_secret VARCHAR(20),
  recovery_address VARCHAR(63) UNIQUE,
  account_status ACCOUNT_STATUS NOT NULL DEFAULT 'pending'
);

CREATE TABLE auth_sessions (
  token UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_user INT NOT NULL REFERENCES auth_users ON DELETE CASCADE,
  started TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_active TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  active BOOLEAN DEFAULT TRUE,  -- TODO need a cron job to close expired sessions just so they look sensible
  events JSONB[]
);
