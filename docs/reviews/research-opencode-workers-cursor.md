Researching OpenCode worker integrations and free coding models. No files or plan docs.

Web search was blocked. Retrying with direct read-only fetches.

Live fetch was blocked this session. Confirm limits on the linked pages; free catalogs move.

## 1. Claude Code driving OpenCode workers

**CLI** — https://opencode.ai/docs/cli — https://github.com/anomalyco/opencode  
Setup: install from https://opencode.ai. Add a provider key. From Claude Code Bash or a skill, run `opencode run` with the model set and permissions pre-allowed (https://opencode.ai/docs/config). Put the worker in its own git worktree.  
Pros: official agent, any OpenCode model, edits and shell, no extra protocol.  
Cons: same worktree means edit clashes; Claude sees stdout, not the session; a permission prompt stalls a headless run.

**Server + SDK** — https://opencode.ai/docs/sdk — https://opencode.ai/docs/server  
Setup: `opencode serve`, then the JS SDK (create session, send prompt) from a script Claude calls.  
Pros: real sessions, resume, structured events, one long-lived worker.  
Cons: a server must stay up; Claude still needs that caller script.

**ACP** — https://opencode.ai/docs/acp — spec https://agentclientprotocol.com — https://github.com/agentclientprotocol/agent-client-protocol  
Setup: `opencode acp` on stdio. Reference client is Zed (https://zed.dev).  
Pros: standard sessions and permissions.  
Cons: Claude Code has no ACP client. https://github.com/zed-industries/claude-code-acp lets Zed drive Claude Code (other direction).

**MCP** — https://docs.anthropic.com/en/docs/claude-code/mcp  
Setup: a local MCP server whose tool runs `opencode run` or the SDK; register it in `.mcp.json`. https://opencode.ai/docs/mcp is for tools OpenCode calls.  
Pros: Claude calls the worker as a tool and can run several.  
Cons: you write the wrapper; it needs its own worktree and a timeout.

**Worker pack inside OpenCode** — https://github.com/code-yeongyu/oh-my-opencode  
Setup: install the plugin, then Claude only launches `opencode run`.  
Pros: ready-made roles and cheap-model routing.  
Cons: OpenCode orchestrates, not Claude; plugins break across OpenCode releases.

**Same models, Claude Code binary** — https://github.com/musistudio/claude-code-router  
Setup: config routes Claude Code at OpenRouter, DeepSeek, Gemini, or Ollama, then start through the router.  
Pros: one agent UI, model is just config.  
Cons: tool-call mismatches; breaks when Claude Code updates.

## 2. Free coding models, minimal setup

**OpenRouter `:free`** — https://openrouter.ai/models?q=free — key https://openrouter.ai/keys — limits https://openrouter.ai/docs/api-reference/limits  
Setup: one key, `OPENROUTER_API_KEY`, pick a `:free` coder in OpenCode. Prefer Qwen3-Coder, DeepSeek chat, or current Gemini Flash when those aliases exist.  
Limits: published free-model policy has been about 20 RPM, about 50 requests/day before credits, about 1000/day after $10 credits.  
Pros: one key, many models. Cons: daily cap kills agent loops; `:free` names disappear.

**Gemini Flash** — https://aistudio.google.com/apikey — https://ai.google.dev/gemini-api/docs/rate-limits — OpenCode provider https://opencode.ai/docs/providers  
Setup: Google account, create a key, select Google in OpenCode. Use the current Flash row.  
Limits: free Flash stays near 10 RPM and a few hundred requests/day. Gemini 2.5 Flash was 10 RPM, 250 RPD, 250k TPM.  
Pros: best hosted free quality and context, no card. Cons: quota is too low for tight loops.

**Groq** — https://console.groq.com/keys — https://console.groq.com/docs/rate-limits  
Setup: one key, OpenCode Groq provider. Use the free Qwen, Llama, Kimi, or gpt-oss row that is listed.  
Limits: per model; a typical free row is tens of RPM, a few thousand TPM, and a daily cap in the thousands.  
Pros: fastest free tokens. Cons: weaker than Qwen3-Coder or DeepSeek on hard edits; the lineup changes.

**Ollama** — https://ollama.com/download — https://ollama.com/library/qwen3-coder — also https://ollama.com/library/devstral  
Setup: install, `ollama pull qwen3-coder`, point OpenCode at `http://localhost:11434`.  
Limits: none; RAM/GPU only. A 32B quant wants a large machine.  
Pros: private, no quota. Cons: laptop-size quants lose to hosted Qwen3-Coder and DeepSeek.

**More friction:** Cerebras free Qwen https://cloud.cerebras.ai (limits https://inference-docs.cerebras.ai/support/rate-limits). Qwen trial https://www.alibabacloud.com/help/en/model-studio/getting-started/first-api-call-to-qwen. DeepSeek’s own API is paid and cheap: https://platform.deepseek.com/api_keys. GLM: https://docs.z.ai. Kimi K2 weights: https://github.com/MoonshotAI/Kimi-K2 (free only while Groq or OpenRouter hosts it).

**Pick:** OpenRouter or AI Studio key, then `opencode run` in a separate worktree. Use Ollama when the daily caps are too low.

