# AgentMail — Email for AI Agents

Manage email inboxes, send and receive emails autonomously.

## When to Use

- User asks to send an email
- User wants to set up an email inbox for the agent
- Check for new emails / incoming messages
- Auto-reply to emails
- Cron jobs for email monitoring

## API Key

The user must provide their own AgentMail API key (from https://agentmail.to).

**First time:** Ask the user for their key, then save it to memory:
```
manage_memory action="save" namespace="config" key="agentmail_api_key" value="<THE_KEY>"
```

**Later:** Load the key from memory before calling agentmail:
```
manage_memory action="load" namespace="config" key="agentmail_api_key"
```

Then pass the key in every `agentmail` call via the `api_key` parameter.

## Quick Start

### Create an inbox

```
agentmail action="create_inbox" api_key="<KEY>" display_name="My Agent"
```

### List inboxes

```
agentmail action="list_inboxes" api_key="<KEY>"
```

### Send an email

```
agentmail action="send_message" api_key="<KEY>" inbox_id="<INBOX_ID>" to=["recipient@example.com"] subject="Hello" text="This is a test email."
```

### Check messages

```
agentmail action="list_messages" api_key="<KEY>" inbox_id="<INBOX_ID>"
```

### Read a specific message

```
agentmail action="get_message" api_key="<KEY>" inbox_id="<INBOX_ID>" message_id="<MSG_ID>"
```

### Reply to a message

```
agentmail action="reply" api_key="<KEY>" inbox_id="<INBOX_ID>" message_id="<MSG_ID>" text="Thanks for your email!"
```

### List threads

```
agentmail action="list_threads" api_key="<KEY>" inbox_id="<INBOX_ID>"
```

### Get full thread

```
agentmail action="get_thread" api_key="<KEY>" inbox_id="<INBOX_ID>" thread_id="<THREAD_ID>"
```

## Tips

- Always load the API key from memory before calling agentmail
- First create an inbox, then use its ID for all other actions
- The inbox gets a random email address like `username@agentmail.to`
- You can set `username` when creating to pick a custom prefix
- Save the inbox_id to memory so you don't need to list_inboxes every time
- For monitoring, set up a cron job to check new messages periodically
