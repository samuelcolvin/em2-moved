-- TODO: indexes.

CREATE TABLE platforms
(
  id SERIAL PRIMARY KEY,
  name CHARACTER VARYING(255) NOT NULL UNIQUE
  -- TODO check ttl
);
CREATE INDEX platform_name ON platforms USING btree (name);
INSERT INTO platforms (name) VALUES ('F');

CREATE TABLE recipients
(
  id SERIAL PRIMARY KEY,
  address CHARACTER VARYING(255) NOT NULL UNIQUE,
  platform INTEGER REFERENCES platforms ON DELETE RESTRICT
  -- TODO check ttl
);

CREATE TABLE conversations
(
  id serial primary key,
  hash CHARACTER VARYING(64) UNIQUE,
  draft_hash CHARACTER VARYING(64) UNIQUE,
  creator INTEGER NOT NULL REFERENCES recipients ON DELETE RESTRICT,
  timestamp TIMESTAMP,
  subject CHARACTER VARYING(255) NOT NULL,
  -- TODO expiry
  last_event INTEGER REFERENCES events,
  ref CHARACTER VARYING (255)
);

CREATE TABLE participants
(
  conversation INTEGER NOT NULL REFERENCES conversations ON DELETE CASCADE,
  recipient INTEGER NOT NULL REFERENCES recipients ON DELETE RESTRICT,
  readall BOOLEAN DEFAULT FALSE,
  -- TODO permissions, hidden, status
  primary key (conversation, recipient)
);

CREATE TABLE messages
(
  id serial primary key,
  hash CHARACTER VARYING(20),
  conversation INTEGER NOT NULL REFERENCES conversations ON DELETE CASCADE,
  parent INTEGER REFERENCES messages,
  body TEXT
  -- TODO deleted
);

CREATE TYPE action_type AS ENUM ('add', 'modify', 'delete', 'lock', 'release lock');
CREATE TYPE target_type AS ENUM ('participant', 'message');  -- TODO attachments, subject, expiry, labels

CREATE TABLE events
(
  id serial primary key,
  conversation INTEGER NOT NULL REFERENCES conversations ON DELETE CASCADE,
  actor INTEGER NOT NULL REFERENCES participants ON DELETE RESTRICT,
  timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  parent INTEGER REFERENCES events,
  action action_type NOT NULL,
  target target_type NOT NULL,
  participant INTEGER REFERENCES participants,
  message INTEGER REFERENCES messages,
  body TEXT
);

CREATE TYPE event_status_type AS ENUM ('pending', 'temporary_failure', 'failed', 'successful');

CREATE TABLE events_status
(
  event INTEGER NOT NULL REFERENCES events ON DELETE CASCADE,

  status event_status_type NOT NULL DEFAULT 'pending',
  platform INTEGER REFERENCES platforms,
  participant INTEGER REFERENCES participants,
  errors JSONB[]
);

-- TODO attachments
