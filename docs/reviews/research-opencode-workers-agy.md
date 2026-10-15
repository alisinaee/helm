# OpenCode Workers for Claude-Driven Projects

## 1. Top 3 Tools and CLI Wrappers for Running OpenCode Models as Workers

- **OpenCode CLI**
  - URL: https://github.com/opencode-ai/opencode
  - What it does: Open-source terminal agent harness providing headless non-interactive execution (`opencode run`) and background server mode (`opencode serve`) supporting 75+ model providers (URL: https://opencode.ai).
  - Setup steps: Install via `npm i -g opencode-ai` or `brew install opencode-ai/tap/opencode` (URL: https://opencode.ai), configure provider keys or local endpoints, and run worker tasks with `opencode run --auto -m <provider/model> "<prompt>"`.

- **Aider**
  - URL: https://github.com/Aider-AI/aider
  - What it does: Terminal AI coding CLI supporting automated headless scripting (`aider --message "<prompt>" --yes-always`) and git-aware diff application across local and hosted models (URL: https://aider.chat).
  - Setup steps: Install via `python3 -m pip install aider-chat` (URL: https://aider.chat/docs/install.html), set API credentials, and run `aider --model <model-name> --message "<prompt>" --yes-always`.

- **Ollama**
  - URL: https://github.com/ollama/ollama
  - What it does: Local LLM runner and CLI providing OpenAI-compatible REST API endpoints (`http://localhost:11434/v1`) to run open coding models as local worker backends (URL: https://ollama.com).
  - Setup steps: Install via package manager or download from https://ollama.com/download, run `ollama serve`, and pull models using `ollama run qwen2.5-coder` (URL: https://ollama.com/library/qwen2.5-coder).

## 2. Top 5 Free Models for Coding

1. **Qwen 2.5 Coder 32B Instruct**
   - URL: https://openrouter.ai/qwen/qwen-2.5-coder-32b-instruct:free
   - Details: State-of-the-art open coding model for code completion and refactoring, free on OpenRouter and free locally via Ollama (URL: https://ollama.com/library/qwen2.5-coder).

2. **DeepSeek V3 / DeepSeek Chat**
   - URL: https://openrouter.ai/deepseek/deepseek-chat:free
   - Details: High-performing open architecture model for code generation and multi-step reasoning (URL: https://github.com/deepseek-ai/DeepSeek-V3).

3. **Google Gemini 2.0 Flash**
   - URL: https://openrouter.ai/google/gemini-2.0-flash-exp:free
   - Details: High-speed 1M-context model with free usage tiers via Google AI Studio (URL: https://ai.google.dev) and OpenRouter.

4. **Meta Llama 3.3 70B Instruct**
   - URL: https://openrouter.ai/meta-llama/llama-3.3-70b-instruct:free
   - Details: Instruction-tuned open model for complex logic and coding, available free on OpenRouter and locally via Ollama (URL: https://ollama.com/library/llama3.3).

5. **Codestral 22B**
   - URL: https://ollama.com/library/codestral
   - Details: Mistral's open-weights model specialized in code generation across 80+ programming languages, downloadable free for local execution (URL: https://huggingface.co/mistralai/Codestral-22B-v0.1).

## 3. Simplest Setup

The simplest zero-cost, low-configuration setup pairs OpenCode CLI with OpenRouter's free tier:
1. Install OpenCode CLI: `npm i -g opencode-ai` (URL: https://github.com/opencode-ai/opencode).
2. Obtain a free API key from OpenRouter (URL: https://openrouter.ai/keys) and set `export OPENROUTER_API_KEY="your-key"`.
3. Run the headless worker agent with auto-approvals: `opencode run --auto -m openrouter/qwen/qwen-2.5-coder-32b-instruct:free "your task description"` (URL: https://opencode.ai).
