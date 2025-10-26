# LinkedIn Post: Morgana DeepResearchAgent

🚀 **Thrilled to unveil Morgana — my end-to-end deep research studio for teams that demand evidence, velocity, and polish.** I engineered the alpha in just a few intense days, compressing years of multi-agent experimentation into a cohesive LangGraph workflow.

Morgana automates the drudge work behind expert research while keeping humans firmly in control. The system spins up a coordinated squad of planners, deep researchers, coders, and storytellers that can investigate, synthesize, and package a topic in one seamless flow.

## Why it matters

- **Mission-ready planning:** A TrustCall-enhanced planner inspects every brief, rehydrates past context, and won't ship a plan until the steps are structured, scoped, and grounded.
- **Deep agent execution:** A Deep Agent branches sub-agents for exploratory search, evidence audits, and follow-up design, persisting every artifact in a virtual file system so context never evaporates.
- **Research timer middleware:** Custom middleware nudges the model when a step is overstaying its budget, keeping execution focused and cost-aware.
- **Signal-rich tooling:** Logged Tavily/Brave/DuckDuckGo search, Jina crawling, Python REPL, and private RAG connectors cave in context gaps without hallucinations.
- **Human-in-the-loop by default:** Coordinators route queries, planners pause for review (`[EDIT PLAN]` or `[ACCEPTED]`), and background investigations warm up context before execution.
- **Deliverables on autopilot:** Reporters compress multi-thousand token transcripts into polished long-form deliverables, complete with Markdown tables, citation management, slide decks, and even Volcengine-powered podcasts.
- **Observability built in:** Every run is checkpointed, streamable via LangGraph Studio, and traceable with Langfuse so ops teams can audit or replay anything.
- **Beautiful, transparent UX:** A Next.js workspace streams source pulls, animates plan progress, and surfaces contextual breadcrumbs so stakeholders always know what’s happening.

## Meet the specialist sub-agents

- **Research agent** – drives web-scale investigations, juggling TODO lists and MCP tools without losing context.
- **Critique agent** – red-lines drafts for evidence gaps, tone issues, and structural misses before anything ships.
- **Query strategist** – rewrites vague prompts into laser-focused directives that unlock high-signal search.
- **Insight synthesizer** – distills crawled material into weighted insights with provenance baked in.
- **Exploration architect** – proposes counterfactuals, longitudinal checks, and follow-on work so momentum never stalls.
- **Evidence auditor** – cross-examines citations, numbers, and assertions against raw sources to keep reports defensible.

## See it in action

🎥 **Live demo:** [End-to-end Morgana walkthrough](https://deep-research-agent-taupe.vercel.app/)

The walkthrough covers MCP integrations, multi-agent execution, translucent progress streaming, and how the system ships the final report, podcast script, and slides in a single pass.

## Under the hood

- Python 3.12 backend orchestrated by LangGraph, with background research pivots, trust-call plan validation, and per-step recursion limits.
- Next.js 14 front-end with replayable sessions, responsive research sidebars, and a shareable "case study" gallery.
- Flexible model routing via LiteLLM — ship on GPT-4.1 Nano for cost-sensitive runs or swap in open weights like Qwen locally.
- Optional Postgres/Mongo checkpointing, LangSmith tracing, and Marp-based presentation exports for enterprise-ready deployments.
- Real-time activity rails, streaming citations, and replayable timelines that turn research ops into a spectator sport.

## Looking for collaborators

I’m eager to partner with teams who need agentic automation: think strategy firms, product orgs, and ops teams that live on structured answers. If that’s you:

1. Drop me a DM for early access.
2. Explore the open-source repo and star it to follow along: `github.com/obinopaul/DeepResearchAgent`
3. Let’s jam on integrations—Morgana’s MCP interface and tool hooks make it straightforward to connect your proprietary knowledge base.

Building Morgana has been the culmination of years working across multi-agent systems, retrieval tooling, and production AI workflows. If you’re scaling research velocity without sacrificing rigor, I’d love to talk.

Hashtags: #AI #IntelligentAutomation #LangGraph #MultiAgentSystems #ResearchOps #OpenSource #AIEngineer

