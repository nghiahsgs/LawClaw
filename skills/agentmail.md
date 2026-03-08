# AgentMail — Email for AI Agents

Manage email inboxes, send and receive emails autonomously.

## When to Use

- User asks to send an email
- User wants to set up an email inbox for the agent
- Check for new emails / incoming messages
- Auto-reply to emails
- Cron jobs for email monitoring

## Quick Start

### Create an inbox

```
agentmail action="create_inbox" display_name="LawClaw Agent"
```

### List inboxes

```
agentmail action="list_inboxes"
```

### Send an email

```
agentmail action="send_message" inbox_id="<INBOX_ID>" to=["recipient@example.com"] subject="Hello" text="This is a test email from LawClaw."
```

### Check messages

```
agentmail action="list_messages" inbox_id="<INBOX_ID>"
```

### Read a specific message

```
agentmail action="get_message" inbox_id="<INBOX_ID>" message_id="<MSG_ID>"
```

### Reply to a message

```
agentmail action="reply" inbox_id="<INBOX_ID>" message_id="<MSG_ID>" text="Thanks for your email!"
```

### List threads

```
agentmail action="list_threads" inbox_id="<INBOX_ID>"
```

### Get full thread

```
agentmail action="get_thread" inbox_id="<INBOX_ID>" thread_id="<THREAD_ID>"
```

## Tips

- First create an inbox, then use its ID for all other actions
- The inbox gets a random email address like `username@agentmail.to`
- You can set `username` when creating to pick a custom prefix
- For monitoring, set up a cron job: `agentmail action="list_messages" inbox_id="<ID>"` and compare with last check
- Use `display_name` to set a friendly name shown in email headers
