DROP SCHEMA public CASCADE;
CREATE SCHEMA public;

-- TODO add domains, organisations and teams, perhaps new db/app.

CREATE TABLE recipients (
  id SERIAL PRIMARY KEY,
  address VARCHAR(255) NOT NULL UNIQUE
  -- TODO perhaps display name
);

CREATE TABLE conversations (
  id SERIAL PRIMARY KEY,
  key VARCHAR(64) UNIQUE,
  published BOOL DEFAULT False,
  creator INT NOT NULL REFERENCES recipients ON DELETE RESTRICT,
  created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  subject VARCHAR(255) NOT NULL,
  -- TODO expiry
  ref VARCHAR (255)
);

CREATE TABLE participants (
  id SERIAL PRIMARY KEY,
  conv INT NOT NULL REFERENCES conversations ON DELETE CASCADE,
  recipient INT NOT NULL REFERENCES recipients ON DELETE RESTRICT,
  -- TODO permissions, hidden, status, has_seen/unread
  UNIQUE (conv, recipient)
);

-- see core.Relationships enum which matches this
CREATE TYPE RELATIONSHIP AS ENUM ('sibling', 'child');
CREATE TYPE MSG_FORMAT AS ENUM ('markdown', 'plain', 'html');

CREATE TABLE messages (
  id SERIAL PRIMARY KEY,
  key CHAR(20) NOT NULL,
  conv INT NOT NULL REFERENCES conversations ON DELETE CASCADE,
  after INT REFERENCES messages,
  relationship RELATIONSHIP,
  position INT[] NOT NULL DEFAULT ARRAY[1],
  deleted BOOLEAN DEFAULT FALSE,
  body TEXT,
  format MSG_FORMAT NOT NULL DEFAULT 'markdown',
  UNIQUE (conv, key)
);
CREATE INDEX message_key ON messages USING btree (key);

-- see core.Verbs enum which matches this
CREATE TYPE VERB AS ENUM ('publish', 'add', 'modify', 'delete', 'recover', 'lock', 'unlock');
-- see core.Components enum which matches this
CREATE TYPE COMPONENT AS ENUM ('subject', 'expiry', 'label', 'message', 'participant', 'attachment');

CREATE TABLE actions (
  id SERIAL PRIMARY KEY,
  key CHAR(20) NOT NULL,
  conv INT NOT NULL REFERENCES conversations ON DELETE CASCADE,
  verb VERB NOT NULL,
  component COMPONENT,
  actor INT NOT NULL REFERENCES recipients ON DELETE RESTRICT,
  timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  parent INT REFERENCES actions,

  recipient INT REFERENCES recipients,
  message INT REFERENCES messages,

  body TEXT,
  UNIQUE (conv, key)
);
CREATE INDEX action_key ON actions USING btree (key);

CREATE FUNCTION do_action_update() RETURNS trigger AS $do_action_update$
  BEGIN
    -- update the conversation timestamp on new actions
    UPDATE conversations SET updated_ts=NEW.timestamp WHERE id=NEW.conv;
    RETURN NULL;
  END;
$do_action_update$ LANGUAGE plpgsql;

CREATE TRIGGER action_update AFTER INSERT ON actions FOR EACH ROW EXECUTE PROCEDURE do_action_update();

-- see core.ActionStatuses enum which matches this
CREATE TYPE ACTION_STATUS AS ENUM ('temporary_failure', 'failed', 'successful');

CREATE TABLE action_states (
  action INT NOT NULL REFERENCES actions ON DELETE CASCADE,
  ref VARCHAR(100),
  status ACTION_STATUS NOT NULL,
  node VARCHAR(255),  -- null for fallback TODO rename to node
  errors JSONB[],
  UNIQUE (action, node)
);
CREATE INDEX action_state_ref ON action_states USING btree (ref);
-- might need index on platform

-- TODO attachments
