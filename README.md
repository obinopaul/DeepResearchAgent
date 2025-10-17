# Morgana

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> Originated from open source, give back to open source.

**Morgana** is a deep research studio that orchestrates multi-agent investigations, source-grounded synthesis, and polished deliverables. It pairs large language models with specialized tools for search, crawling, code execution, and content generation while keeping humans in the loop where it matters.

This project is inspired by the excellent [DeerFlow](https://github.com/bytedance/deer-flow) initiative. Morgana keeps the spirit of that work while re-imagining the architecture, agent orchestration, and user experience for a more opinionated deep research workflow.

## Highlights

- **LangGraph Deep Agent Core** – the researcher node is powered by LangGraph's Deep Agent architecture, combining long-form prompts, a planning tool, sub-agents, middleware, and a virtual file system so investigations can branch, persist intermediate artifacts, and rejoin when ready.
- **Task-Aware Planning** – Morgana persists structured TODO plans, status files, and research artifacts for every thread. The planner seamlessly rehydrates context, spawns focused sub-tasks, and keeps execution state off the main context window.
- **Modern Web Experience** – a refreshed UI centers the chat workspace, introduces responsive layouts for research sidebars, and ships with theme controls, replay support, and polished animation inspired by production agent tooling.
- **Model Flexibility** – any LiteLLM-compatible model can be plugged in. The hosted deployment defaults to OpenAI GPT-4.1 Nano for the deep agent to balance context hunger with cost, while heavier models remain available for local runs.
- **Observability by Design** – LangGraph Studio, structured checkpoints, and replayable chat sessions make it straightforward to audit, debug, and iterate on workflows.

## Demo

### Video

<https://github.com/user-attachments/assets/f3786598-1f2a-4d07-919e-8b99dfa1de3e>

The demo covers:

- Integration with Model Context Protocol (MCP) services
- End-to-end deep research culminating in an illustrated report
- Podcast generation built from the generated research narrative

### Replays

- [How tall is Eiffel Tower compared to tallest building?](https://deep-research-agent-taupe.vercel.app/chat?replay=eiffel-tower-vs-tallest-building)
- [What are the top trending repositories on GitHub?](https://deep-research-agent-taupe.vercel.app/chat?replay=github-top-trending-repo)
- [Write an article about Nanjing's traditional dishes](https://deep-research-agent-taupe.vercel.app/chat?replay=nanjing-traditional-dishes)
- [How to decorate a rental apartment?](https://deep-research-agent-taupe.vercel.app/chat?replay=rental-apartment-decoration)
- [Explore more replays on the website](https://deep-research-agent-taupe.vercel.app/#case-studies)

---

## Table of Contents

- [Quick Start](#quick-start)
- [Supported Search Engines](#supported-search-engines)
- [Features](#features)
- [Architecture](#architecture)
- [Text-to-Speech Integration](#text-to-speech-integration)
- [Development](#development)
- [Docker](#docker)
- [Examples](#examples)
- [FAQ](#faq)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## Quick Start

Morgana (a.k.a. DeepResearchAgent) ships with a Python backend and a Next.js web experience. The tooling below mirrors the workflow we use for local development.

### Recommended Tools

- **[`uv`](https://docs.astral.sh/uv/getting-started/installation/):** Creates and manages project virtual environments and dependencies automatically.
- **[`nvm`](https://github.com/nvm-sh/nvm):** Makes it simple to install and switch between Node.js versions.
- **[`pnpm`](https://pnpm.io/installation):** Efficient package manager for the web workspace.

### Environment Requirements

- **[Python](https://www.python.org/downloads/):** Version 3.12 or newer
- **[Node.js](https://nodejs.org/en/download/):** Version 22 or newer

### Installation

```bash
# Clone the repository
git clone https://github.com/obinopaul/DeepResearchAgent.git
cd DeepResearchAgent

# Install Python dependencies (uv will create the virtualenv for you)
uv sync

# Prepare environment configuration
cp .env.example .env
cp conf.yaml.example conf.yaml

# The .env file holds API keys (Tavily, Brave Search, RAG providers, Volcengine TTS, etc.)
# conf.yaml controls LLM routing; use Ollama or local models for offline development.

# (Optional) install Marp for PPT generation
brew install marp-cli
```

Install the web dependencies with `pnpm` if you plan to run the full-stack experience:

```bash
cd DeepResearchAgent/web
pnpm install
```

### Configurations

See the [Configuration Guide](docs/configuration_guide.md) for an exhaustive walkthrough of every environment flag and configuration value. Update the sample files before booting the stack.

### Console UI

The quickest way to experience Morgana is through the console application:

```bash
uv run main.py
```

### Web UI

For the full chat and research experience, start both backend and frontend services:

```bash
# macOS/Linux
./bootstrap.sh -d
# Windows
bootstrap.bat -d
```

By default the API binds to `127.0.0.1` for safety. Change the host to `0.0.0.0` inside the bootstrap script if you are deploying remotely, and secure the environment before exposing it.

Then visit <http://localhost:3000>.

## Supported Search Engines

### Web Search APIs

Configure the `SEARCH_API` variable in `.env` to choose a provider:

- **Tavily** (default) – purpose-built for AI assistants (`TAVILY_API_KEY` required)
- **DuckDuckGo** – privacy-focused and keyless
- **Brave Search** – privacy-first with advanced filters (`BRAVE_SEARCH_API_KEY`)
- **ArXiv** – scientific publications without an API key
- **Searx/SearxNG** – self-hosted metasearch (`SEARX_HOST` required)

```bash
# Choose one: tavily, duckduckgo, brave_search, arxiv, searx
SEARCH_API=tavily
```

### Private Knowledge Base

Morgana supports private retrieval sources such as RAGFlow and VikingDB so research can stay grounded in your corpus.

```text
# Example RAGFlow configuration (see .env.example)
RAG_PROVIDER=ragflow
RAGFLOW_API_URL="http://localhost:9388"
RAGFLOW_API_KEY="ragflow-xxx"
RAGFLOW_RETRIEVAL_SIZE=10
RAGFLOW_CROSS_LANGUAGES=English,Chinese,Spanish,French,German,Japanese,Korean
```

## Features

### Deep Agent Core

- Built on LangGraph's Deep Agent architecture with dedicated planner, TODO tool, and hierarchical sub-agents for every research thread.
- Researcher sub-agents persist plans, intermediate notes, and execution progress to a virtual file system, letting long-form tasks resume without blowing up the context window.
- Configurable middleware lets you inject validation, guardrails, or custom tracing into the agent loop.

### Model Strategy

- Compatible with any [LiteLLM](https://docs.litellm.ai/docs/providers) provider or OpenAI-compatible API.
- Defaults to OpenAI GPT-4.1 Nano for hosted research tasks to keep costs predictable while still supporting heavier models for desktop runs.
- Supports popular open-source models such as Qwen when configured via the provided guides.

### Modern Web Experience

- Responsive, centered chat layout with adaptive research sidebars.
- Built-in theme toggle, animated loading states, and replay support for showcasing multi-agent runs.
- Auth-friendly header components with quick links to project assets.

### Tools and MCP Integrations

- Web search, crawling, and structured extraction (Tavily, Brave, Jina, and more)
- Native RAGFlow integration for private document retrieval
- MCP clients extend Morgana into knowledge graphs, enterprise APIs, and internal tooling

### Human Collaboration

- Natural-language plan editing keeps humans steering long tasks (`[EDIT PLAN]`, `[ACCEPTED]`, etc.)
- Optional auto-accept flow when you want to run without interruptions
- Notion-style editing experience for generated reports, including AI-assisted rewrite actions

### Content Creation

- Podcast scripts and audio generation for every report
- Automated slide and presentation exports (Marp-based)
- Customizable templates for downstream publishing

## Architecture

Morgana implements a modular LangGraph workflow with clear boundaries between planning, research, execution, and reporting.

![Architecture Diagram](./assets/architecture.png)

> See it live at [deep-research-agent-taupe.vercel.app](https://deep-research-agent-taupe.vercel.app)

The pipeline consists of:

1. **Coordinator** – entry point that receives user requests, orchestrates the graph, and routes state transitions.
2. **Planner** – builds structured research plans, rehydrates existing TODOs, and decides when to iterate versus execute.
3. **Deep Research Team** – hierarchical agent stack:
   - **Deep Researcher** (LangGraph Deep Agent) performs web work, manages sub-agents, interacts with the file system, and tracks TODO status.
   - **Coder** executes Python tool invocations for data wrangling or code-level investigation.
   - Additional sub-agents can be added per workflow via configuration.
4. **Reporter** – synthesizes findings, enriches them with images, citations, and media, and hands results to the UI for editing or podcast generation.

Every agent interaction is checkpointed. Plans, notes, and data artifacts are stored via the LangGraph checkpoint saver so you can replay, inspect, and resume long-running sessions.

## Text-to-Speech Integration

Morgana ships with Volcengine-based text-to-speech so reports can be turned into audio summaries.

```bash
curl --location 'http://localhost:8000/api/tts' \
  --header 'Content-Type: application/json' \
  --data '{
    "text": "This is a test of the text-to-speech functionality.",
    "speed_ratio": 1.0,
    "volume_ratio": 1.0,
    "pitch_ratio": 1.0
  }' \
  --output speech.mp3
```

Configure your TTS credentials in `.env` before invoking the endpoint.

## Development

### Testing

```bash
make test               # run all tests
pytest tests/integration/test_workflow.py
make coverage
```

### Code Quality

```bash
make lint
make format
```

### Debugging with LangGraph Studio

LangGraph Studio can visualize Morgana's workflow in real time. The repository includes `langgraph.json` so you can boot the studio with a single command.

#### macOS

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uvx --refresh --from "langgraph-cli[inmem]" --with-editable . --python 3.12 langgraph dev --allow-blocking
```

#### Windows / Linux

```bash
pip install -e .
pip install -U "langgraph-cli[inmem]"
langgraph dev
```

The CLI prints the API endpoint, Studio UI, and docs URL. Open the Studio UI link to inspect state transitions, provide live feedback during planning, and replay runs.

### Enabling LangSmith Tracing

Set the following variables in `.env` to stream traces to LangSmith:

```bash
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT="https://api.smith.langchain.com"
LANGSMITH_API_KEY="xxx"
LANGSMITH_PROJECT="xxx"
```

Then launch `langgraph dev` to capture traces locally and within LangSmith.

### Checkpointing

1. LangGraph checkpoint saver supports Postgres and MongoDB. In-memory stores cache streaming messages before persistence.
2. Set `LANGGRAPH_CHECKPOINT_SAVER=true` and configure `LANGGRAPH_CHECKPOINT_DB_URL` in `.env`.

```bash
LANGGRAPH_CHECKPOINT_SAVER=true
LANGGRAPH_CHECKPOINT_DB_URL="mongodb://localhost:27017/"
# LANGGRAPH_CHECKPOINT_DB_URL="postgresql://localhost:5432/postgres"
```

3. Default database: `checkpoint_db`. Collections: `checkpoint_writes_aio`, `checkpoints_aio`, `chat_streams`.
4. For Postgres, prefer `langgraph-checkpoint-postgres==2.0.21` until [issue #5557](https://github.com/langchain-ai/langgraph/issues/5557) is resolved (`TypeError: Object of type HumanMessage is not JSON serializable`).
5. Psycopg typically requires `libpq`. Install the binary extra if you do not have system libraries available:

```bash
pip install psycopg[binary]
```

See the [Psycopg installation guide](https://www.psycopg.org/psycopg3/docs/basic/install.html) for platform support.

## Docker

Run Morgana in containers after preparing `.env` and `conf.yaml`.

```bash
docker build -t morgana-api .
docker run -d -t -p 127.0.0.1:8000:8000 --env-file .env --name morgana-api-app morgana-api
docker stop morgana-api-app
```

The repository also includes a compose file to launch backend and frontend together:

```bash
docker compose build
docker compose up
```

Add authentication and harden MCP/Python REPL access when deploying to production.

## Examples

### Research Reports

1. **OpenAI Sora Report** – features, access, prompt engineering, and ethics  
   [examples/openai_sora_report.md](examples/openai_sora_report.md)
2. **Google's Agent to Agent Protocol** – emergent agent communication patterns  
   [examples/what_is_agent_to_agent_protocol.md](examples/what_is_agent_to_agent_protocol.md)
3. **What is MCP?** – Model Context Protocol and other meanings across domains  
   [examples/what_is_mcp.md](examples/what_is_mcp.md)
4. **Bitcoin Price Fluctuations** – market trends, regulation, technical indicators  
   [examples/bitcoin_price_fluctuation.md](examples/bitcoin_price_fluctuation.md)
5. **What is LLM?** – architecture, training, applications, and ethics  
   [examples/what_is_llm.md](examples/what_is_llm.md)
6. **How to Use Claude for Deep Research?** – prompt engineering and workflows  
   [examples/how_to_use_claude_deep_research.md](examples/how_to_use_claude_deep_research.md)
7. **AI Adoption in Healthcare** – organizational readiness and digital infrastructure  
   [examples/AI_adoption_in_healthcare.md](examples/AI_adoption_in_healthcare.md)
8. **Quantum Computing vs. Cryptography** – vulnerabilities and post-quantum strategies  
   [examples/Quantum_Computing_Impact_on_Cryptography.md](examples/Quantum_Computing_Impact_on_Cryptography.md)
9. **Cristiano Ronaldo: Performance Highlights** – achievements and international record  
   [examples/Cristiano_Ronaldo's_Performance_Highlights.md](examples/Cristiano_Ronaldo's_Performance_Highlights.md)

Run Morgana with your own queries:

```bash
uv run main.py "What factors are influencing AI adoption in healthcare?"
uv run main.py --max_plan_iterations 3 "How does quantum computing impact cryptography?"
uv run main.py --interactive
uv run main.py
uv run main.py --help
```

### Interactive Mode

```bash
uv run main.py --interactive
```

Choose English or Chinese, pick a built-in topic or provide your own, and Morgana will generate a full research report.

### Human in the Loop

1. **Plan review** – Morgana presents the generated plan before execution.  
2. **Feedback loop** – respond with `[ACCEPTED]` or `[EDIT PLAN] ...` to refine it.  
3. **Auto-accept** – set `auto_accepted_plan: true` in API calls to bypass review.  
4. **API feedback** – supply the `feedback` parameter to guide revisions programmatically.

```json
{
  "messages": [{ "role": "user", "content": "What is quantum computing?" }],
  "thread_id": "my_thread_id",
  "auto_accepted_plan": false,
  "feedback": "[EDIT PLAN] Include more about quantum algorithms"
}
```

### Command Line Arguments

- `query` – research query to run
- `--interactive` – launch guided interactive mode
- `--max_plan_iterations` – cycle planning before execution (default 1)
- `--max_step_num` – constrain plan length (default 3)
- `--debug` – verbose logging

## FAQ

See [docs/FAQ.md](docs/FAQ.md) for common questions and troubleshooting tips.

## License

Released under the [MIT License](./LICENSE).

## Acknowledgments

Morgana stands on the shoulders of the open-source ecosystem. Thank you to:

- **[LangChain](https://github.com/langchain-ai/langchain)** for the foundational LLM framework.
- **[LangGraph](https://github.com/langchain-ai/langgraph)** for stateful agent orchestration.
- **[Novel](https://github.com/steven-tey/novel)** for the Notion-style editor powering report revisions.
- **[RAGFlow](https://github.com/infiniflow/ragflow)** for private knowledge base retrieval.
- **[DeerFlow](https://github.com/bytedance/deer-flow)** whose authors laid the groundwork that Morgana extends.

We continue to contribute back by documenting changes, improving usability, and keeping the project aligned with the needs of deep research practitioners.
