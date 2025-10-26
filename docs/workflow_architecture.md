# Morgana Architecture Schemas

This document visualizes the end-to-end LangGraph workflow that powers Morgana and the inner workings of the deep-agent execution loop.

## Workflow Orchestration (Top-Level Graph)

```mermaid
flowchart LR
    Start([User Request])
    Coordinator[Coordinator Node<br/>Chat intake & routing]
    Background{Enable background<br/>investigation?}
    Investigator[Background Investigator<br/>Web search & crawl]
    Planner[Planner Node<br/>TrustCall plan builder]
    Iteration{Plan accepted?}
    Maxed{Max iterations reached?}
    ResearchTeam[Research Team Hub<br/>Step dispatcher]
    Researcher[Researcher Node<br/>Deep Agent executor]
    Coder[Coder Node<br/>Python & data tooling]
    Reporter[Reporter Node<br/>Report & media synthesis]
    End([Final Deliverables])

    Start --> Coordinator
    Coordinator --> Background
    Background -->|Yes| Investigator
    Background -->|No| Planner
    Investigator --> Planner
    Planner --> Iteration
    Iteration -->|Needs edits| Planner
    Iteration -->|Accepted| ResearchTeam
    Planner --> Maxed
    Maxed -->|Yes| Reporter
    Maxed -->|No| ResearchTeam
    ResearchTeam -->|Research step| Researcher
    ResearchTeam -->|Processing step| Coder
    Researcher --> ResearchTeam
    Coder --> ResearchTeam
    ResearchTeam -->|Plan complete| Reporter
    Reporter --> End
```

### Key Highlights

- **Configuration-driven:** `Configuration.from_runnable_config` injects max iterations, search caps, MCP servers, and research budgets into every node.
- **Human-in-the-loop hooks:** `interrupt()` pathways let reviewers approve (`[ACCEPTED]`) or revise (`[EDIT PLAN]`) plans before execution.
- **State persistence:** LangGraph checkpoints preserve plans, observations, and artifacts between node transitions and replays.
- **Multiple execution paths:** The planner can jump directly to the reporter when a plan has enough context, or loop until max iterations are hit.

## Deep Agent Execution Loop

```mermaid
flowchart TB
    Entry[Pending plan steps<br/>from Research Team]
    Chunk[Chunk steps in pairs<br/>two at a time]
    Brief[Compose execution brief<br/>user query, step summary, resources]
    Timer[[Research Timer Middleware<br/>LangChain middleware]]
    Orchestrator[LangGraph Deep Agent<br/>recursion limit 1000]
    subgraph SubAgents[Specialist Sub-Agents]
        Research[Research agent<br/>web & MCP tooling]
        Critique[Critique agent<br/>report redlining]
        Strategist[Query strategist<br/>prompt refinement]
        Synthesizer[Insight synthesizer<br/>evidence scoring]
        Architect[Exploration architect<br/>follow-up design]
        Auditor[Evidence auditor<br/>citation checks]
    end
    Tools[(Search, Crawl, RAG,<br/>Python REPL, MCP servers)]
    Result[Capture pair response<br/>and update step status]
    Aggregator[Accumulate execution results<br/>for every pair]
    Synthesis[Invoke reporter LLM<br/>for final synthesis]
    Update[Write observations, reports,<br/>and plan step metadata]
    Return[Return to Research Team node]

    Entry --> Chunk --> Brief
    Brief --> Timer --> Orchestrator
    Orchestrator --> SubAgents
    SubAgents --> Orchestrator
    Orchestrator --> Tools
    Tools --> Orchestrator
    Orchestrator --> Result --> Aggregator
    Aggregator -->|More pairs pending| Chunk
    Aggregator -->|All pairs complete| Synthesis --> Update --> Return
```

### Deep Agent Highlights

- **Pair-wise execution:** `_execute_deepagent_step` batches plan steps in twos, giving the model a fresh brief every cycle to limit context drift.
- **Resource-aware prompting:** When resource files are present, a local-search reminder is injected before each deep-agent call.
- **Timer middleware:** `ResearchTimerMiddleware` (LangChain middleware) alerts the agent as time elapses, nudging it to conclude or abort runaway loops.
- **Rich tool surface:** MCP-delivered tools and built-ins (search, crawl, RAG, Python) are dynamically attached per configuration.
- **Final synthesis:** After all pairs, Morgana replays the accumulated findings through the reporter LLM to produce the polished final deliverable.
