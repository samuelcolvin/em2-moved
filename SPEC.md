# Models

### Recipient

* id
* address
* platform
* ttl for platform

### Conversations

* hash - of conversation basics
* creator - recipient
* timestamp
* expiration
* subject
* last event
* reference slugified initial subject used for hash 

also: cryptographic signature, status?

### Participant

* conversation
* recipient
* read/unread - perhaps null for remote participants

Also: display name, permissions, hidden, status: active, archived, muted, left?

Also: notes & personal labels.

### Action

* conversation
* key
* timestamp
* recipient
* remote/local
* parent key
* action: add, modify, delete, lock, release lock
* model: participant, message, attachment, subject, expiry, label
* item id
* ref - summary of body, used for key
* body

### Platform Event Delivery

One per platform, but also one per participant using SMTP.

* event id/key
* platform
* status
* details on failure(s)

Do we need participant event delivery?

### Message

* conversation
* key
* parent
* body

Also: author, editors - can get this from events.

### Attachment

* conversation
* message id
* title
* hash
* path
* keys
* reference to how to download

----------------------------------

# Event types

# Publish conversation

Local only, sets hash and prompts initial "add participants"
  
### Subject
* modify

### Set expiry
* modify

### Labels
* add
* remove

### Participant
* add (with perms) - **this is equivalent to send** 
* delete
* change perms

### Messages
* add (with parent)
* remove
* lock
* modify and release lock
* release lock

### Read notification

Just includes participant and event id.

Obviously read notifications are not sent for read notifications.

### Attachments
* add
* remove

### Extras

eg. maps, calendar appointments

----------------------------------

# User

In directory:
* email address
* public key
* full name - "the name you use on documents"
* common name - "what people call you in conversation"
* status: - active, out of office, dormant
* type:
  * user
  * alias
  * bot
  * shared account, eg. info@ - address monitored by numerous people
* organisations / teams
* photo
* short description
* description - markdown
* other trusted profiles
* platform
* timezone, used both to display times and communicate in what timezone actions occurred

Perhaps way of giving more info to people who have received a message from the user:
* phone
* more info

To log in:
* email address
* password & mfa
* backup email address
* phone number
* password reset details

Used in em2 server:
* address
* name?

----------------------------------

# Platform and Client Communications

### Push: An event happened

Details of the event.

Sent to other platforms via web request, distributed to clients via websockets.

The "add participant" is a special case which includes the subject and perhaps more details.

Goes to platforms with at least one participant involved.

Event statuses are saved for each event going to each platform and each local participant. 

Used to record failures and reschedule re-sends.

Events statuses which are "complete" can be deleted to avoid bloat.

### Pull: Get kitchen sink on a conversation

Contains everything about the conversation. 

I guess includes all events in the case of platform requests.

# Client Only Communications

### List Conversations


* allow paging
* Include info about whether the conversation is unread or not
* Include last event hash so client can work out if it's up to date

### Search Conversations

IDs and subjects of conversations matching search

----------------------------------

# Endpoints

### Foreign (Platform) Endpoints

* `GET:  /f/auth/` - also perhaps used to prompt platform to send any failed events
* `POST: /f/evt/.../` - new event
* `GET:  /f/{key}/` - get kitchen sink on a conversation
* `GET:  /f/{key}/events/` - get events for a conversation, useful if events get missed.

### Domestic (Client/User) Endpoints

* `GET:  /d/l/?offset=50` - list conversations
* `GET:  /d/s/?q=...` - search conversations
* `GET:  /d/{key}/` - get kitchen sink on a conversation
* `WS:   /d/ws/` - connect to websocket to retrieve events
* `POST: /d/evt/.../` - send event
* `POST: /d/new/` - start draft
* `POST: /d/publish/{key}/` - publish conversation

----------------------------------

# Action processing

### Foreign Actions

1. Action received
2. If the conversation exists: Action instance created, else see below
3. Job `propagate(action_id)` fired, in job:
4. Get all participants for conversation, create a set in redis for recipient_ids `recipients:{action_id}`
5. For each active frontend application (see below), check if there are recipients in this conv: `SINTER`
6. If recipients are found for any applications: get action details and add to list of "jobs" for that application.
Should be possible to add action data to all `frontend:jobs:{app-name}` lists in one pipeline operation.

If conv doesn't exist:
1. Job `create_conv(action_details)` fired, in job:
2. Request conv details from platform, if the conv doesn't exist: throw an error
3. create action
4. fire `propagate(action_id)`

### Domestic Actions

If conv is not published: app `call_later`s `app.send_draft_action` which does the same as `propagate` but only
sends action to the creator.

Otherwise, fires `propagate(action_id, push=True)`. `propagate` gets the list of recipients,
calls `push`, then continues as with foreign actions.

### Frontend Applications

Apps should have random name, they should delete all keys on termination.

Redis keys:
* `frontend:recipients:{app-name}` - contains a set of recipient ids associated with the app. Named such 
that `propagate` can find all frontend apps with `frontend:recipients:*`. Expires fairly regularly such that if 
the app dies this record of the app's existence dies soon too.
* `frontend:jobs:{app-name}` - list of actions to push to clients, not created by the app, just waited upon.

Task `process_actions`, running constantly in infinite `BLPOP` loop, when an action arrives sends it to clients. 
`BLPOP` timesout occasionally and extends `EXPIRE` on `frontend:recipients:{app-name}`.

----------------------------------

# Integration with SMTP

list all participants in the email body, then

### Either

Send "to" each SMTP recipient

set reply-to to a unique address on the platform, leave the platform to forward the message other SMTP participants

(Will have problem with "forging" emails from the original SMTP adddress)

### Or

cc to all SMTP addresses, cc to a unique address for each em2 domain "<conv-key>.<message-key>@platform.com",
this might involve multiple email addresses for each platform but that's fine.

Second solution should work better and look more normal for SMTP users.
