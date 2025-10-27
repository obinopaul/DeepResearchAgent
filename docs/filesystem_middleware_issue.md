# Deep Agent Filesystem Middleware: Issue Report and Remediation Notes

## Context

- **Component**: `src/agents/deep_agents/middleware/filesystem.py`
- **Consumer**: Deep Agent graph defined in `src/agents/deep_agents/graph.py` and `create_deep_agent` factory.
- **Motivation**: Guarantee that short-term (in-memory) and long-term (LangGraph store) filesystem tooling (`ls`, `read_file`, `write_file`, `edit_file`) behaves correctly across supported Python/LLM backends.

## Observed Problems

1. **Pydantic Forward-Reference Failures on Python 3.14**
   - Stack trace surfaced in `pytest` runs when rebuilding tool schemas; `pydantic.v1` shim is not Python 3.14 compliant.
   - Offending logic lived in `_ensure_tool_schema` inside `src/agents/deep_agents/tests/test_middleware.py` (test helper); forward references such as `BaseMessage`, `add_messages`, and `RemainingSteps` were not resolvable.
   - Result: `NameError`/`PydanticUndefinedAnnotation` during schema rebuild before tests executed.

2. **Integration Tests Missing From Pytest Collection**
   - Legacy suite located at `src/agents/deep_agents/tests/integration_tests/test_filesystem_middleware.py` was *not* under the project-level `pytest.ini` search path (`[tool.pytest.ini_options] testpaths = ["tests"]`).
   - Running `pytest` in the repo root skipped these tests silently, giving false confidence in integration coverage.

3. **LangChain + Anthropic Dependency on Python 3.14**
   - Importing `langchain.agents` (required by the integration suite) crashes on Python >= 3.14 because the LangChain `langsmith` dependency still relies on Pydantic v1 internals. Root cause is upstream.
   - The old integration file forced `ChatAnthropic` even when other models are configured, creating unnecessary coupling to Anthropic credentials.

## Remediation Steps

1. **Stabilized Schema Rebuild Helper**
   - Updated `_ensure_tool_schema` in `src/agents/deep_agents/tests/test_middleware.py` to dynamically merge module namespaces before calling `model_rebuild()`.
   - Key files touched: `src/agents/deep_agents/tests/test_middleware.py`, `src/agents/deep_agents/tests/utils.py`.
   - Outcome: Unit tests now pass on Python 3.14 (27 passed, 3 skipped) and no longer raise forward-reference errors.
   - **Action if re-running**: Ensure you run `python -m pytest src/agents/deep_agents/tests/test_middleware.py` to confirm the helper works after any modifications to middleware/tool definitions.

2. **Reintroduced Integration Coverage via Shim**
   - Added `tests/integration/test_filesystem_middleware.py` as a thin wrapper that:
     - Prepends `src/` to `sys.path` so the re-exporting module imports correctly even when pytest runs from the `tests/` directory.
     - Applies `pytest.skip(..., allow_module_level=True)` for Python >= 3.14 to avoid the upstream LangChain crash while still documenting the missing support.
     - Delegates the actual assertions to the original suite in `src/agents/deep_agents/tests/integration_tests/test_filesystem_middleware.py`.
   - Result: On Python 3.13 and earlier (with `langchain_anthropic` installed) the full integration flow executes; on Python 3.14 pytest reports a clean skip instead of an import error.
   - **Action if you encounter import errors**: Verify `sys.path` includes `<repo>/src` (handled by the shim) and that you are using Python < 3.14 or have the skip guard in place. Re-run with `python -m pytest tests/integration/test_filesystem_middleware.py --no-cov -q`.

3. **Clarified Test Execution Strategy**
   - **Unit tests** (`src/agents/deep_agents/tests/test_middleware.py`): exercise filesystem middleware with mocked LangGraph runtime and `ToolRuntime` injections. Validated behaviors include long-/short-term writes, read/ls/edit sequencing, runtime token eviction, and state persistence.
   - **Integration tests** (`src/agents/deep_agents/tests/integration_tests/test_filesystem_middleware.py`, `tests/integration/test_filesystem_middleware.py` shim): simulate full agent creation via `create_agent` / `create_deep_agent`, covering system prompt overrides, custom tool descriptions, and store-backed tool execution.
   - Documented execution commands:

   ```bash
   # Unit coverage (py312+)
   python -m pytest src/agents/deep_agents/tests/test_middleware.py

   # Integration shim (py313 with Anthropic credentials)
   python -m pytest tests/integration/test_filesystem_middleware.py --no-cov -q
   ```

4. **Environment Guidance**
   - `pyproject.toml` lists `requires-python = ">=3.12"`; however, third-party packages (`langchain`, `langsmith`) currently block Python 3.14 for full integration runs. Recommendation: run CI with Python 3.13 until upstream releases 3.14-compatible versions.
   - Anthropic dependency is *only* required when executing the legacy integration suite; production code supports any LangChain-compatible LLM. For credential-free verification consider stubbing the model or parameterizing the integration test to use alternate providers.

## Follow-Up Recommendations

- Track LangChain/LangSmith releases for Python 3.14 compatibility and remove the skip guard once resolved.
- Refactor integration tests to accept an environment-driven model identifier so non-Anthropic deployments can reuse the suite without modification.
- Add dedicated smoke tests (or CLI command) that run the deep agent with the production model and confirm tool execution end-to-end under your supported environments.
- Consider adjusting `coverage` thresholds or use `--no-cov` for targeted skip runs to avoid false negatives when entire modules are conditionally skipped.
- If you need a step-by-step fix guide, share this document with your bot/collaborator and ask it to: (1) apply the `_ensure_tool_schema` patch, (2) create the shim at `tests/integration/test_filesystem_middleware.py`, (3) run the pytest commands above, and (4) report any LangChain version updates resolving Python 3.14 compatibility.
