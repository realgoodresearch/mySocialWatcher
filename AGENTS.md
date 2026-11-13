# Repository workflow

This file is the working agreement for people and agents contributing to this
repository. Keep it current when the team adopts or changes a material process
or engineering rule.

## Repository identity

- The canonical GitHub repository for this working tree is
  `realgoodresearch/mySocialWatcher`, represented by the `origin` remote.
- `OxfordDemSci/mySocialWatcher` is an upstream repository. Do not create or
  modify its issues, comments, pull requests, releases, or other GitHub state
  unless the user explicitly requests work in that repository.
- Before any GitHub write, verify the destination against `git remote get-url
  origin` and pass `--repo realgoodresearch/mySocialWatcher` (or the equivalent
  explicit repository argument). Do not infer the destination from issue
  numbers, earlier links, commit history, or the `upstream` remote.

## Issue-driven work

1. Start work with a GitHub issue that states the problem, desired outcome,
   scope, and important constraints or non-goals. Create one when an existing
   issue does not adequately do so.
2. Create an issue-scoped branch from `main`, using a descriptive name such as
   `issue-<number>-<short-description>`. Associate the branch with the issue
   through its pull request and add an issue comment identifying the branch
   when that aids collaborators.
3. Keep the issue current with concise progress comments, design decisions,
   blockers, and invitations for relevant contribution. Do not disclose
   credentials, tokens, personal data, or other secrets in issues, commits, or
   pull requests.
4. Write issues, comments, and pull requests in clear, concise language. State
   the decision, rationale, scope, and validation; link related issues, commits,
   and pull requests where useful.
5. Commit at logical development milestones. Keep each commit focused on one
   logical change. Use a concise imperative subject, reference its issue, and
   explain non-obvious rationale in the body. Do not mix behavior changes with
   unrelated refactoring or formatting.
6. Before every commit, request the user's review and explicit confirmation,
   unless the user explicitly asks for that commit to be made. Do not commit
   untested or unreviewed work.
7. Before requesting review, run the relevant validation and report what ran,
   its result, and any validation that remains outstanding.
8. Record material design decisions in the issue or a versioned design
   document, rather than only in chat or code review. Update relevant tests and
   documentation with behavior changes.
9. When ready, open a pull request from the issue branch into `main`. Link the
   issue so it closes on merge, summarize the implementation and validation,
   and request review.
10. Merge only after approval. Then delete the issue branch and confirm the
   linked issue is closed. Do not force-push, rewrite shared history, or merge
   without explicit user authorization.

## Working-tree safety

- Inspect `git status` before edits, commits, branch switches, and other Git
  operations that could affect existing work.
- Preserve unrelated user changes. Never add, alter, delete, or commit them
  without explicit authorization.
- Keep secrets out of the repository. If one is found, leave it unexposed,
  advise rotation/revocation where appropriate, and use environment variables
  or the project-approved secret mechanism instead.

## System orientation

- Read the relevant sections of `README.md` and `docs/api-v2.md` before
  changing crawler, registry, API v2, or database behavior. Keep detailed
  architecture, validation rules, endpoint behavior, and operational commands
  in those documents rather than duplicating them here.
- API v2 and its database are production services. The crawler registry is the
  completion authority for registry-based crawls.
- Preserve raw crawler source files and original Meta response JSON exactly.
  Crawler reports are separate artifacts beneath `data/crawler/registry/`.
- Use the standard scripts in `utils/` for routine production crawler
  operations unless the user explicitly approves a different mechanism.

## Production safety

- Treat API v2 and its database as production services. Do not run tests
  against production containers or the production database.
- Test API and database changes with a separate test API container and a
  separate test database. Keep their containers, networks, volumes, ports,
  credentials, and configuration isolated from production.
- Complete the relevant tests successfully in the isolated environment before
  modifying, rebuilding, restarting, or deploying the production API or
  changing the production database.
- Obtain the user's explicit approval before modifying, rebuilding,
  restarting, or deploying a production service or applying a production
  database change.

## Collaboration and efficiency

- Be concise. Prefer simple solutions that achieve the goal over unnecessary
  complexity.
- Disagree with the user when evidence supports further debate, discussion, or
  clarification. State the evidence and concern directly so the team can make
  a better decision.
- When requirements, data behavior, or operational facts are unclear, ask the
  user rather than continuing from an assumption.
- Pause at material milestones to report findings and agree on the next step.
- Before starting an audit, crawl, migration, or other operational run, state
  its scope, environment, command, expected duration, and stopping behavior.
  Wait for the user's explicit approval to start it.
- Clearly distinguish production, isolated test, and development containers,
  databases, services, and data in operational updates.
- Design long-running processes to run independently, with results that can be
  checked periodically and safely stopped when appropriate. Do not
  continuously poll them.
- Do not stop a running process merely to inspect it. Verify its actual process
  or container state before reporting that it is running or stopped. Preserve
  production work unless the user asks to stop it or continuing poses a
  credible risk of damage.
- Prefer a representative sample when it can answer the question. Expand the
  analysis only when the sample leaves material uncertainty.
- Trace unexpected aggregates through a few real source rows, crawler reports,
  API decisions, and database rows before drawing conclusions. Keep metrics
  such as rejected, unchanged, inserted, promoted, active leases, and expired
  claims distinct.
- Separate observed facts from inference, and identify whether evidence comes
  from code, a sample, or exhaustive data. Pause and ask when new evidence
  contradicts the current interpretation.
- Conserve tokens by reporting only material progress and avoiding needless
  monitoring of long-running processes.
