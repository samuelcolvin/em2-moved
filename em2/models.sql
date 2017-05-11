DROP SCHEMA public CASCADE;
CREATE SCHEMA public;

CREATE TABLE platforms (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255) NOT NULL UNIQUE
  -- TODO check ttl
);
CREATE INDEX platform_name ON platforms USING btree (name);
INSERT INTO platforms (name) VALUES ('f');

CREATE TABLE recipients (
  id SERIAL PRIMARY KEY,
  address VARCHAR(255) NOT NULL UNIQUE,
  platform INT REFERENCES platforms ON DELETE RESTRICT
  -- TODO check ttl, perhaps display name
);
CREATE INDEX recipient_address ON recipients USING btree (address);

CREATE TABLE conversations (
  id SERIAL PRIMARY KEY,
  hash VARCHAR(64) UNIQUE,
  creator INT NOT NULL REFERENCES recipients ON DELETE RESTRICT,
  timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  subject VARCHAR(255) NOT NULL,
  -- TODO expiry
  ref VARCHAR (255)
);

CREATE TABLE participants (
  id SERIAL PRIMARY KEY,
  conversation INT NOT NULL REFERENCES conversations ON DELETE CASCADE,
  recipient INT NOT NULL REFERENCES recipients ON DELETE RESTRICT,
  readall BOOLEAN DEFAULT FALSE,
  -- TODO permissions, hidden, status
  UNIQUE (conversation, recipient)
);

CREATE TABLE messages (
  id SERIAL PRIMARY KEY,
  hash VARCHAR(40) NOT NULL,
  conversation INT NOT NULL REFERENCES conversations ON DELETE CASCADE,
  parent INT REFERENCES messages,
  body TEXT,
  UNIQUE (conversation, hash)
  -- TODO deleted
);

CREATE TYPE action_type AS ENUM ('add', 'modify', 'delete', 'lock', 'release lock');
CREATE TYPE target_type AS ENUM ('participant', 'message');  -- TODO attachments, subject, expiry, labels

CREATE TABLE events (
  id SERIAL PRIMARY KEY,
  hash VARCHAR(40) NOT NULL,
  conversation INT NOT NULL REFERENCES conversations ON DELETE CASCADE,
  actor INT NOT NULL REFERENCES participants ON DELETE RESTRICT,
  timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  parent INT REFERENCES events,
  action action_type NOT NULL,
  target target_type NOT NULL,

  participant INT REFERENCES participants,
  message INT REFERENCES messages,
  body TEXT,
  UNIQUE (conversation, hash)
);

CREATE TYPE event_status_type AS ENUM ('pending', 'temporary_failure', 'failed', 'successful');

CREATE TABLE events_status (
  event INT NOT NULL REFERENCES events ON DELETE CASCADE,

  status event_status_type NOT NULL DEFAULT 'pending',
  platform INT REFERENCES platforms,
  participant INT REFERENCES participants,
  errors JSONB[]
);

-- TODO attachments
