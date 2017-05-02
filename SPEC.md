# Models

### Recipient

* id
* address
* platform
* ttl for platform

### Conversations

* hash - of conversation basics
* draft hash - used until published
* creator - recipient
* timestamp
* expiration
* subject
* last event
* reference slugified nitial subject used for hash 

also: cryptographic signature, status?

### Participant

* conversation
* recipient
* read/unread - perhaps null for remote participants

Also: display name, permissions, hidden, status: active, archived, muted, left?

Also: notes & personal labels.

### Event

* conversation
* hash
* timestamp
* recipient
* remove/local
* parent hash
* action: add, modify, delete, lock, release lock
* model: participant, message, attachment, subject, expiry, label
* item id
* ref - summary of body, used for hash
* body

### Platform Event Delivery

One per platform, but also one per participant using SMTP.

* event id/hash
* platform
* status
* details on failure(s)

Do we need participant event delivery?

### Message

* conversation
* hash
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
* remove
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

----------------------------------


# Platform and Client Communications

### Push: An event happened

Details of the event.

Sent to other platforms via web request, distributed to clients via websockets.

The "add participant" is a special case which includes the subject and perhaps more details.

Goes to platforms with at least one participant involved.

Event statuses are saved for each event going to each platform and each local participant. 

Used to record failures and reschedule re-sends.

Events which are "complete" can be deleted to avoid bloat.

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
* `GET:  /f/{hash}/` - get kitchen sink on a conversation
* `GET:  /f/{hash}/events/` - get events for a conversation, useful if events get missed.

### Domestic (Client/User) Endpoints

* `GET:  /d/l/?offset=50` - list conversations
* `GET:  /d/s/?q=...` - search conversations
* `GET:  /d/{hash}/` - get kitchen sink on a conversation
* `WS:   /d/ws/` - connect to websocket to retrieve events
* `POST: /d/evt/.../` - send event
* `POST: /d/new/` - start draft
* `GET:  /d/draft/{draft-hash}/` - get kitchen sink on a draft conversation
* `POST: /d/publish/{draft-hash}/` - publish conversation

----------------------------------

# Distributing Events

1. Event received
2. Event instance created
3. Job `process_event(event_id)` fired
4. In the job, get the job, then:
  * publish (via redis pub-sub) updates for all local participants connected to websockets
  * (if event was local) create "Platform Event Delivery" objects and push to platforms/SMTP users.
