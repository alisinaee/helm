"""The static text of `roadmap agent-guide`: rules, the most used commands, the plan grammar, research and estimates.

Pure data, no I/O. Every line starting with "roadmap " is a command that tests parse with roadmap.cli.build_parser().
The guide stays at 40 lines or fewer (GUIDE_MAX_LINES); docs/AGENT-INTERFACE.md section 4 describes it.
"""

GUIDE_MAX_LINES = 40

_LINES = (
    "Agent guide for roadmap-board: how an agent records work on a project board",
    "",
    "Rules",
    "- Never open or edit docs/tasks.json or docs/jobs.json. Use the commands below.",
    "- Every command takes --json. On an error, run the command printed on the next: line.",
    "- Dry-run first: add --dry-run to plan import and task set, read the diff, then run it again without it.",
    "- --project ID is optional; without it the project is the one registered for this folder.",
    "",
    "Most used commands (--tokens and tokensK are thousands of tokens)",
    "roadmap status",
    "roadmap task list --status todo,partial --limit 10",
    "roadmap task show P1.2",
    "roadmap task done P1.2 --tokens 20 --note \"short note\"",
    "roadmap task set --dry-run",
    "roadmap job start \"Write the parser\" sonnet P1.2",
    "roadmap job done j3 \"parser done\" --tokens 18",
    "roadmap plan import docs/research/04-plan.md --dry-run",
    "",
    "Plan text: one record per line; a task id is <phase>.<n>",
    "P <id> <status> | <name>",
    "T <id> <status> <tokensK> <model>/<thinking> [!] [c:<check>/<checkK>] | <title> [# <note>]",
    "status: todo, partial, done, hold, backlog or -. "
    "model: haiku, sonnet, opus or -. thinking: low, medium, high or -.",
    "Example: P P1 todo | Foundations",
    "Example: T P1.1 todo 20 haiku/low | Scaffold repo and lint",
    "Example: T P1.2 todo 5 haiku/low ! | Create the hosting account # needs your login",
    "Bulk set (task set, stdin): one \"ID key=value ...\" line per task.",
    "Keys: status, tokensK, model, thinking, needsUser, check, checkK, note, title.",
    "",
    "Research (first, for a new project): docs/research/NN-slug.md, at most 6 notes",
    "Each note has ## Question, ## Findings, ## Decisions and ## Sources; at most 120 lines and 6 KB.",
    "roadmap research new landscape \"Similar products\"",
    "roadmap research list",
    "roadmap research check",
    "",
    "Token estimate (K tokens, round to 5; never below 5 or above 150 per task)",
    "Small one-file change: 10 to 30. A few files: 30 to 80. Large or new feature: 80 to 150.",
    "A check review is 10 to 25% of the work estimate. When unsure, round up.",
)


def lines():
    """The guide as a list of lines, without a trailing newline."""
    return list(_LINES)
