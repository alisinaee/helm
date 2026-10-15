# Request: the "Head" section (the person's words, 2026-10-15). TOP PRIORITY: design first with Opus (high effort)

> tell opus: very important feature: we need another section as **head**.
> What is this? It shows the **model that takes the role of head**.
> **What the user asks and tells** (auto-summarised, and also able to see the full details): all of it needs to be in that section.
> For example: now I will talk and tell you many things in the middle of the task and chat. To **avoid forgetting and missing**, these things need to be **logged in there**.
> Also we need to see **if the head goes for them, takes action for them or not**.
> Did they **bind to a task**? Did they **fulfil** them and are they **done**? Or **in progress**, or ... the **status** of each of them.
> **What the user's ask converts to**: an **issue**? a **task**? a **review**? ...
> This should be **very smart**. This is a very, very good feature for us and Opus needs to think well about this.
> (also: "I don't want, when I start a new chat, to tell the AI agent all things again": the section is the persistent memory of the person's requests and decisions.)

## What the first job must produce (Opus, effort HIGH, read-only, one file docs/HEAD-SPEC.md)
1. The **request ledger**: every person message that contains an ask, decision, rule, bug report or preference is logged (who said it, when, verbatim text, a short auto-summary, a kind: ask | decision | rule | bug | preference | question) with full detail on demand.
2. How the head (the AI session) **captures** them reliably and cheaply: a CLI (`roadmap head log "<verbatim>" --kind ... --task ...`), hooks (UserPromptSubmit hook can append every person message to the ledger automatically: investigate what the Claude Code hook payload gives), the docs/HANDOVER + memory sync, and the `/head` skill reading the ledger on resume so a new chat needs NO re-explaining.
3. **Conversion and traceability**: each ledger entry links to what it became (issue / task / review / backlog item / rule / feature / decision), with a lifecycle status: new -> understood -> bound -> in progress -> done | declined | needs-you; "did the head act on it?" = a visible flag and age ('unhandled for 2 h'); coverage view (uncovered asks), done/accepted by the person only.
4. The **GUI section** "Head": who is head now (model, session start, usage), a timeline/list of asks with summary + status chips + the bound tasks, expand for the verbatim text, filters (unhandled, in progress, done), a one-line Overview chip ('3 asks unhandled'), copy-ref support, phone read-only; aligned grid (UI rule 0), CSS budget (cap 72 KB).
5. Smartness: auto-summarise, auto-suggest the conversion (ask -> task vs issue vs review) and duplicates/merge, detect unfulfilled asks from old sessions, keep per-account-switch continuity.
6. Safety/privacy (no secrets), data model compatible with the existing files, Haiku-sized build breakdown with strict file lists, Cursor grok review gate, agy audits.
