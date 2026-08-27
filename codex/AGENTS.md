  # Repository instructions

  - Store every temporary file under `private/tmp/`, relative to the repository root.
  - Put disposable intermediate files that may be cleaned up while work is still in progress under `private/tmp/to_clean/<task-specific-name>/`.
  - Put temporary files that must remain available for the duration of the work under `private/tmp/to_persist/<task-specific-name>/`. Clean them up only at the end of the work, after they are no longer needed for validation or delivery.
  - Create the required directories if they are missing.
  - Never use `/tmp` or `/private/tmp`.
  - Do not commit temporary files from `private/tmp/`.
  - Cleanup of an explicit task-specific directory under repository-local `private/tmp/to_clean/` or `private/tmp/to_persist/` is pre-authorized. Invoke `/Users/tibger01/.config/codex/bin/cleanup-repo-task-tmp.sh --kind to_clean --task <task-specific-name>` during work, or use `--kind to_persist` only at the end of the work. Invoke the wrapper directly from inside the owning Git repository so its execution-policy rule matches; do not prefix it with a shell or `env`. Never target `private/tmp/`, `private/tmp/to_clean/`, or `private/tmp/to_persist/` themselves, use a glob or unresolved variable, or include `..`. The wrapper must verify that the explicit direct child resolves beneath the appropriate repository-local directory before removal.

## Temporary tool environments

- When a required validation or helper tool is unavailable, Codex may create a
  task-specific `uv` virtual environment under `private/tmp/to_persist/<task-specific-name>/`,
  install only the required packages there, and remove the environment at the
  end of the work.
- Keep the associated `UV_CACHE_DIR` under the same task-specific directory as
  well. Do not write
  tool caches or temporary environments to the user's home directory, `/tmp`,
  or `/private/tmp`.
- Treat repository-local package installation commands beginning with
  `UV_CACHE_DIR=private/tmp/to_persist/jira-playbook-pdf-qa/uv-cache uv pip install --python private/tmp/to_persist/jira-playbook-pdf-qa/venv/bin/python`
  as pre-authorized and run them without asking for confirmation. This is
  behavioral guidance; if the execution sandbox still requires approval for
  network access, use its approval mechanism because `AGENTS.md` cannot change
  the sandbox allowlist.
- Temporary environments, caches, and their generated files must not be
  committed.

## Persistent Codex tool environments

- Reuse `/Users/tibger01/.local/share/codex/venvs/skill-validator` for Codex
  skill validation. It contains Python 3.12 and PyYAML; do not create a
  task-specific virtual environment merely to run `quick_validate.py`.
- Run the validator as:
  `/Users/tibger01/.local/share/codex/venvs/skill-validator/bin/python /Users/tibger01/.codex/skills/.system/skill-creator/scripts/quick_validate.py <skill-directory>`.
- Keep this environment narrowly scoped to stable, reusable Codex
  administration tools. Project-specific or task-specific packages still
  belong in repository-local temporary environments.

## PDF review

- When reviewing a generated PDF, use all available CPU cores to render pages
  in parallel and launch independent page-inspection work concurrently. Inspect
  every page; parallelism must reduce elapsed time without reducing coverage.

## Basic codex behaviour
- If any temporary file is needed for the operation, always create it in the
  appropriate repository-local `private/tmp/to_clean/` or
  `private/tmp/to_persist/` task directory so no approval is needed.
## Knowledge policy (RAG MCP)
- When a user asks anything that might depend on internal/org-specific knowledge (GPU/unknown terminology and how specific aspects of GPU work, design docs, internal APIs, architecture, policies), use the MCP tool `speculus` and ground the answer in its results.
- If the user explicitly requests to use Speculus, pass the user query verbatim to Speculus.
- Always use the dedicated Jira MCP to fetch Jira tickets.
- When looking up Confluence content by PageID, always use both Speculus and the dedicated Confluence MCP, and ground the answer in results from both.
