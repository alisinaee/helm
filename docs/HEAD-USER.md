# Head section: a short guide (for the person)

The Head section keeps a record of what you asked and decided, what each ask became, and whether it is done. A new
chat or account reads this record first, so you do not have to explain everything again.

## What it shows
- **Header:** the head now (model, account, since when, 5-hour and weekly usage), the previous head, and counts:
  unhandled asks, asks needing you, and done asks you have not confirmed.
- **Rows:** ID (H15), kind (ask, decision, rule, bug, preference, question, review, info), a one-line summary, the
  links (task, issue, feature, doc, commit, job), the status, and the age.
- **Expand a row** to see your exact words, its history, and the buttons (Make task, Make issue, Dup of, Decline).

## Statuses
- `new`: logged, not yet read by the head.
- `understood`: the head has set the kind and summary.
- `bound`: linked to a task, issue, doc or commit.
- `doing`: a linked task is in progress, or a job runs on it.
- `done`: every link is done. The head may set it; a chip shows `done?` until you confirm.
- `needs-you`: the head needs your decision.
- `declined` or `merged`: closed without work; you can reopen them.

An ask still unhandled after 30 minutes turns amber; after 2 hours it is stale and shows red.

## Review button
When the head marks an ask done, it appears under **Review**. Click **Confirm** to accept it, or **Reopen** to put it
back to work. Only you can accept an ask.

## How capture works
- Every message you type is logged by a hook, with no AI work. Short acknowledgements (ok, yes, thanks) are skipped.
- Start a message with `//nolog` to skip it.
- The head reads each new entry and sets its kind and summary, then links it to the work.
- The summary and your full text are saved in the project's files and committed to git. Redaction removes common
  secrets (keys, tokens, passwords, emails, card numbers), but it is not perfect.

**Never type secrets** (passwords, API keys, tokens, card or bank numbers) in a message. Use `//nolog` for a message
that must not be kept at all, or ask for the value to be entered outside the chat.

## Commands (for reference)
- `roadmap head list` shows open entries; `roadmap head show H15` shows one entry.
- `roadmap head review` lists done entries awaiting your confirmation.
- `roadmap head forget H15` blanks the text of an entry and keeps its summary.
