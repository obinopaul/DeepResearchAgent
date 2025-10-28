# DeepResearchAgent Browser Freeze Investigation

## Observed Behaviour
- The chat UI becomes increasingly sluggish and eventually appears to freeze while a deep research run is in progress.
- The slowdown correlates with long-running research sessions that emit hundreds of Server-Sent Events (SSE) chunks.
- Browser developer tools show a flood of `console.debug` statements emitted for every streaming chunk and for each rerender of complex components such as `PlanCard`.

## Root Cause
- High-frequency debug logging on the critical render path overwhelms the browser:
  - `web/src/core/store/store.ts` logs each SSE event inside the `sendMessage` async iterator (`console.debug("[store.sendMessage] received", …)`), as well as a second log each time a message object is updated.
  - `web/src/core/api/chat.ts` echoes every raw SSE event with `console.debug("[chatStream] event", event.event)`.
  - `web/src/app/chat/components/message-list-view.tsx` logs render state for every `PlanCard` render, capturing large message snapshots.
- During deep research the backend pushes dozens of message chunks per second; each chunk triggers multiple `console.debug` calls. Logging large payloads (chat messages, tool call metadata) is especially expensive because the console serialises these objects.
- The accumulated logging work blocks the main thread, which manifests as UI freezes even though React state updates are throttled to 50 ms.

## Recommended Fixes
1. Remove or gate the streaming `console.debug` statements behind an explicit development flag (e.g. `if (process.env.NEXT_PUBLIC_DEBUG_STREAM === "true")`).
2. Replace per-chunk logging with coarse-grained sampling (e.g. log once per message or when the stream finishes) to avoid O(N) logs for chunk counts.
3. Avoid logging full message objects from React render functions; if logging is still needed, log lightweight identifiers (message id, agent, status) and only in development mode.
4. After trimming the logs, validate in the browser profiler (React Profiler or Chrome Performance) to ensure the render thread remains responsive during long research runs.
5. Optionally add a feature flag so verbose diagnostics can be re-enabled when troubleshooting without shipping them to production builds.

Implementing the logging guard is typically sufficient to eliminate the freeze, because it removes thousands of synchronous console operations emitted during a single research session.
