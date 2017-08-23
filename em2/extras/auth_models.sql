DROP SCHEMA public CASCADE;
CREATE SCHEMA public;


CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  address VARCHAR(255) NOT NULL UNIQUE,
  first_name VARCHAR(63),
  last_name VARCHAR(63),
  password_hash VARCHAR(63),
  otp_secret VARCHAR(20),
  recovery_address VARCHAR(63) UNIQUE
);
CREATE INDEX user_address ON users USING btree (address);
