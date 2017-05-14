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
  key VARCHAR(64) UNIQUE,
  published BOOL DEFAULT False,
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
  active BOOLEAN DEFAULT TRUE,
  -- TODO permissions, hidden, status
  UNIQUE (conversation, recipient)
);

CREATE TABLE messages (
  id SERIAL PRIMARY KEY,
  key CHAR(20) NOT NULL,
  conversation INT NOT NULL REFERENCES conversations ON DELETE CASCADE,
  after INT REFERENCES messages,
  child BOOLEAN DEFAULT FALSE, -- TODO perhaps record depth to limit child replies
  active BOOLEAN DEFAULT TRUE,
  body TEXT,
  UNIQUE (conversation, key)
  -- TODO deleted
);
CREATE INDEX message_key ON messages USING btree (key);

-- see Verbs enum which matches this
CREATE TYPE VERB AS ENUM ('add', 'modify', 'delete', 'recover', 'lock', 'unlock', 'publish');
-- see Components enum which matches this
CREATE TYPE COMPONENT AS ENUM ('subject', 'expiry', 'label', 'message', 'participant', 'attachment');

CREATE TABLE actions (
  id SERIAL PRIMARY KEY,
  key CHAR(20) NOT NULL,
  conversation INT NOT NULL REFERENCES conversations ON DELETE CASCADE,
  verb VERB NOT NULL,
  component COMPONENT NOT NULL,
  actor INT NOT NULL REFERENCES participants ON DELETE RESTRICT,
  timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  parent INT REFERENCES actions,
  participant INT REFERENCES participants,
  message INT REFERENCES messages,
  body TEXT,
  UNIQUE (conversation, key)
);
CREATE INDEX action_key ON actions USING btree (key);

CREATE TYPE ACTION_STATUS AS ENUM ('pending', 'temporary_failure', 'failed', 'successful');

CREATE TABLE actions_status (
  action INT NOT NULL REFERENCES actions ON DELETE CASCADE,
  status ACTION_STATUS NOT NULL DEFAULT 'pending',
  platform INT REFERENCES platforms,
  participant INT REFERENCES participants,
  errors JSONB[]
);

-- TODO attachments
