# AgentMail — Email for AI Agents

Manage email inboxes, send and receive emails autonomously.

## When to Use

- User asks to send an email
- User wants to set up an email inbox for the agent
- Check for new emails / incoming messages
- Auto-reply to emails
- Cron jobs for email monitoring

## API Key & Inbox ID

The user must provide their own AgentMail API key (from https://agentmail.to).

**First time:** Ask the user for their key AND inbox email, then save both to memory:
```
manage_memory action="save" namespace="config" key="agentmail_api_key" value="<THE_KEY>"
manage_memory action="save" namespace="config" key="agentmail_inbox_id" value="<EMAIL>@agentmail.to"
```

**Later:** Load both from memory before calling agentmail:
```
manage_memory action="load" namespace="config" key="agentmail_api_key"
manage_memory action="load" namespace="config" key="agentmail_inbox_id"
```

## IMPORTANT: Do NOT rely on list_inboxes

The `list_inboxes` API has a known bug — it often returns empty even when inboxes exist.
**Always use the inbox_id from memory directly.** Never conclude "no inboxes" based on list results.

If you need to verify an inbox exists, use `get_inbox` (not list).

## Sending an Email (most common task)

Just load key + inbox_id from memory and send directly:

```
agentmail action="send_message" api_key="<KEY>" inbox_id="<INBOX_ID>" to=["recipient@example.com"] subject="Hello" text="This is a test email."
```

Do NOT create a new inbox every time. Reuse the one saved in memory.

## Other Actions

### Get inbox info (verify it exists)
```
agentmail action="get_inbox" api_key="<KEY>" inbox_id="<INBOX_ID>"
```

### Create an inbox (only if user has none)
```
agentmail action="create_inbox" api_key="<KEY>" display_name="My Agent"
```
After creating, save the inbox_id to memory immediately.

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
agentmail action="reply" api_key="<KEY>" inbox_id="<INBOX_ID>" message_id="<MSG_ID>" text="Thanks!"
```

### List/get threads
```
agentmail action="list_threads" api_key="<KEY>" inbox_id="<INBOX_ID>"
agentmail action="get_thread" api_key="<KEY>" inbox_id="<INBOX_ID>" thread_id="<THREAD_ID>"
```

## Tips

- Always load API key AND inbox_id from memory before any agentmail call
- Do NOT use list_inboxes to check if inbox exists — use get_inbox instead
- Do NOT create new inboxes unless user explicitly asks — reuse the saved one
- Free tier has a 2 inbox limit, so don't waste them
- Save inbox_id to memory right after creating so it persists across sessions
