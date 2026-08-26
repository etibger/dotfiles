  # Repository instructions

  - Store every temporary file under `private/tmp/`, relative to the repository root.
  - Create the directory if it is missing.
  - Never use `/tmp` or `/private/tmp`.
  - Do not commit temporary files from `private/tmp/`.

## Basic codex behaviour
- if any temporal file is needed for the operation, always create it in your sandbox, so no approval is needed.
## Knowledge policy (RAG MCP)
- When a user asks anything that might depend on internal/org-specific knowledge (GPU/unknown terminology and how specific aspects of GPU work, design docs, internal APIs, architecture, policies), use the MCP tool `speculus` and ground the answer in its results.
- If the user explicitly requests to use Speculus, pass the user query verbatim to Speculus.
- Always use the dedicated Jira MCP to fetch Jira tickets.
- When looking up Confluence content by PageID, always use both Speculus and the dedicated Confluence MCP, and ground the answer in results from both.
