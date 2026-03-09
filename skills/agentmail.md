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

## Fallback: Sending Email via Python Script

If the `agentmail` tool fails (e.g., due to missing API key configuration in the environment), you can send an email by creating and executing a Python script directly.

### When to Use This Method
- When `agentmail(action="list_inboxes")` returns an empty list even though you know inboxes exist.
- When you need to send an email and the primary `agentmail` tool is not functional.

### Step 1: Create the Python Script

Create a file named `send_email.py` with the following content. You must replace `'YOUR_AGENTMAIL_API_KEY'` with the actual API key.

```python
import os
from agentmail import AgentMail

# --- Configuration ---
# It's recommended to load this from an environment variable for security
API_KEY = "am_us_cdd0c16e7c614a1314ce1a07210669bc15ee2b773dadf23460898ebb90c370cd"
SENDER_EMAIL = "agreeablebench628@agentmail.to"

# The recipient's details
RECIPIENT_EMAIL = "nghiahsgs@gmail.com"
SUBJECT = "Hello from LawClaw"
BODY = "This is a test email sent from a Python script."

# --- Main Logic ---
def main():
    if not API_KEY or API_KEY == "YOUR_AGENTMAIL_API_KEY":
        print("Error: API_KEY is not set.")
        return

    try:
        client = AgentMail(api_key=API_KEY)
        inboxes = client.inboxes.list()
        sender_inbox = next((inbox for inbox in inboxes if inbox.address == SENDER_EMAIL), None)

        if not sender_inbox:
            print(f"Error: Inbox {SENDER_EMAIL} not found.")
            return

        print(f"Found inbox: {sender_inbox.id}")

        print(f"Sending email to {RECIPIENT_EMAIL}...")
        message = client.inboxes.messages.send(
            inbox_id=sender_inbox.id,
            to=[RECIPIENT_EMAIL],
            subject=SUBJECT,
            text=BODY,
        )
        print(f"Email sent! ID: {message.id}")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
```

### Step 2: Execute the Script

Use the `exec_cmd` tool to run the script.

```
exec_cmd command="python send_email.py"
```

### Security and API Key Management

The method above involves hardcoding the API key, which is simple but not secure. The recommended approach, as designed in the `LawClaw` repository, is to use **environment variables**. The system is designed to read the key from an environment variable named `AGENTMAIL_API_KEY`.

Using `manage_memory` to store the key is flexible but requires writing the key to the script file before execution, which poses a security risk. Therefore, using environment variables remains the preferred and most secure method.

