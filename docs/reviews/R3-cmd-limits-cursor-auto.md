Read-only review of `/cmd` + limits/ledger. Pulling those files now.

Delegating parallel read-only slices on `/cmd` security and limits/ledger maths; I'll spot-check claims myself.

agy blocked — reading critical sections myself.

Verifying highest-severity claims against the code.

## WP22 /cmd + limits — findings (max 10)

### 1. Critical — `/cmd` is always `source=gui` → agentguard never applies
**Where:** [`roadmap/http/server.py:67`](roadmap/http/server.py), [`roadmap/http/routes.py:212-213`](roadmap/http/routes.py), [`roadmap/services/cmdops.py:29-41`](roadmap/services/cmdops.py), [`roadmap/services/agentguard.py:15-18`](roadmap/services/agentguard.py)

**Scenario:** `roadmap serve` up on localhost. Agent (or any local process) `GET /` → CSRF from `<meta name="csrf">`, then:

`POST /api/v1/cmd` with `Sec-Fetch-Site: same-origin`, CSRF, `{"op":"limit.rm","args":{"id":"AUTO"}}` (or `limit.set` / `budget.set` value ↑ / undo of a person’s limit tighten).

Main app hardcodes `cmd_source = "gui"`. `_caller_env` clears `CLAUDECODE`; `refuse_if_agent(..., source="gui")` is false. Agent removes or raises own limits despite CLI guard.

**Fix:** Do not treat every main-listener POST as trusted human. Prefer thread-local `gui_ok` (set only when browser-proof headers present: valid `Origin` ∈ `origins(port)` **and** `Sec-Fetch-Site: same-origin`) and pass that into `agentguard` without mutating `os.environ`. Refuse loosening ops unless `gui_ok` or real non-agent CLI.

---

### 2. High — project file error fails open → all rows (incl. global) skipped
**Where:** [`roadmap/services/limits.py:173-177`](roadmap/services/limits.py), [`:287-312`](roadmap/services/limits.py), [`:315-319`](roadmap/services/limits.py)

**Scenario:** Before any block sentinel exists, agent `Write`s `docs/autonomy.json` with `"schemaVersion": 99`. `_autonomy_row` raises `newer_schema` inside `_project_state` **before** `global_rows()` are judged. `evaluate_rows` catches → `[]` → `evaluate` → `ok` → `recompute` clears block. Global day/week pct and project rows never apply for that project. Same if `budget.get` throws.

**Fix:** Build/evaluate `global_rows()` outside project-local try. Wrap autonomy/budget reads per-file; on schema/corruption emit `unknown` or fail closed for that project’s gate, not empty list.

---

### 3. High — any weekly% dip counted as full reset; no 0–100 clamp
**Where:** [`roadmap/services/ledger.py:53-54`](roadmap/services/ledger.py), [`:172-188`](roadmap/services/ledger.py)

**Scenario:** `lastW=62`, next reading `61` (jitter / two writers). `w < base` → `added = w` → **+61** day points (not 0). `global day pct 10` block fires falsely. Also `-5` or `1e9` pass `_number` (`inf` too: `inf==inf`); negative `w` subtracts points / huge `w` spikes.

**Fix:** Reject `weeklyPct` outside `[0, 100]` (finite). Treat reset only on large drop (e.g. `base - w >= 10` or `w < base * 0.5`); else `added = max(0, w - base)` and keep `lastW = max(base, w)`.

---

### 4. Medium — phone `undo` bypasses allowlist via inverse ops
**Where:** [`roadmap/http/security.py:154`](roadmap/http/security.py), [`roadmap/services/commands.py:420-431`](roadmap/services/commands.py), [`roadmap/services/cmdops.py:49-51`](roadmap/services/cmdops.py)

**Scenario:** `phoneWrites=true`. GUI/agent queued `task.start` → activity `A812`. Phone `{"op":"undo","args":{"activity":"A812"}}`. `op_allowed("undo")` ok; `_execute` runs `queue.remove` (not in `PHONE_OPS`, not in `LOOSENING`). Same for undoing another party’s `question.answer` → `question.reopen`, etc. (Resume-via-undo correctly refused — tests cover that only.)

**Fix:** In `_h_undo`, if `current_source()=="phone"`, require original activity `source=="phone"` and `entry["op"] in PHONE_OPS` (or inverse ∈ allowlist).

---

### 5. Medium — undo check / execute / mark not atomic (replay)
**Where:** [`roadmap/services/commands.py:424-434`](roadmap/services/commands.py)

**Scenario:** Two concurrent `undo A5` (rate limit allows 10/s). Both pass “already undone”, both `_execute` inverse, both append `undid`. e.g. undo `rules.rm` → `rules.add` twice → duplicate rules. Also undoing old `A5` after later `A9` on same object overwrites without conflict check.

**Fix:** Under `lock.locked`, claim `undid` first (or CAS); run inverse; on failure remove claim. Optionally refuse undo if current state ≠ recorded prior.

---

### 6. Medium — `_fit` evicts days inside the 7-day window
**Where:** [`roadmap/services/ledger.py:30`](roadmap/services/ledger.py), [`:151-157`](roadmap/services/ledger.py)

**Scenario:** Many projects write daily `tok` entries → ledger > 4KB. After trimming `recent`, `del days[min(days)]` drops oldest keys still inside `_keys(week)`. `tokens_k` / `rate` undercount → tok week limits stop blocking; calibration drifts.

**Fix:** Never delete keys in `_keys(now, "week")`. Cap/merge per-day `tok` (e.g. `_other`) or raise `MAX_BYTES` with a week floor.

---

### 7. Medium — future `updated` treated as fresh
**Where:** [`roadmap/services/limits.py:192-205`](roadmap/services/limits.py)

**Scenario:** Clock steps back, or `usage` `updated` is in the future. `age` negative → `age <= USAGE_STALE_S` true. Stale/wrong weekly% drives `acct` / global week blocks (or keeps a bad reading “fresh” for hours).

**Fix:** Fresh only if `age is not None and 0 <= age <= USAGE_STALE_S` (small negative skew√ optional, e.g. ≥ -60).

---

### 8. Medium — `CLAUDECODE` clear is process-global (thread answer)
**Where:** [`roadmap/services/cmdops.py:24`](roadmap/services/cmdops.py), [`:35-41`](roadmap/services/cmdops.py)

**Scenario:** Lock only serializes **gui** callers. While gui holds env cleared (incl. long `flock` wait), another serve thread calling `agentguard.is_agent(source≠"agent")` sees empty `CLAUDECODE`. Phone can’t loosen today (`PHONE_OPS` + `_refuse_phone`), but any in-process path that relies on env alone is open; child processes spawned in the window inherit cleared env. Combined with finding 1 this is how gui HTTP defeats the shell guard when serve was started under an agent.

**Fix:** Same as #1 — thread-local override; never `os.environ.pop("CLAUDECODE")`.

---

### 9. Medium — `tokensK` unbounded; overflow after status write
**Where:** [`roadmap/services/commands.py:80-82`](roadmap/services/commands.py), [`:99-102`](roadmap/services/commands.py)

**Scenario:** `task.status` with huge int `tokensK` (fits 4KB body). Check allows any `int >= 0`. `tasks.apply` commits status; then `float(tokensK)` → `OverflowError` → 500, no activity/undo. Large finite value permanently inflates budget (undo does not reverse spend) and can trip auto-stop.

**Fix:** Cap in check (e.g. `0 <= tokensK <= 10_000_000`); compute `float` before apply.

---

### 10. Medium — `json.loads` accepts `NaN`/`Infinity`; numeric arg helpers don’t
**Where:** [`roadmap/http/routes.py:193`](roadmap/http/routes.py), [`roadmap/services/cmdops.py:65-71`](roadmap/services/cmdops.py), [`:266-268`](roadmap/services/cmdops.py)

**Scenario:** `budget.set` / `task.cap` with `value: NaN` (Python `json.loads` allows it). `_number_or_none` accepts float NaN. `spent > limit` vs NaN is always false → cap never trips; NaN lands in JSON and can break strict readers. Same class of hole for `rules.add` `value`.

**Fix:** `json.loads(..., parse_constant=raise)`; require `math.isfinite(value)` and sensible ranges in `_number_or_none` / rules value check.

---

**Skipped (known):** `limits.py:541-545` malformed-rm → not_found; `:532` warn budget as block on removal.

**Not counted as bugs here:** div-by-zero in share/`rate` (guarded); estimate inflation from untracked account pts (design); rate limiter (counts post-allowlist only, as documented).

