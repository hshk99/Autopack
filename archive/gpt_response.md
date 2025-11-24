
## 1. Git operations in Docker (critical)

### Current situation

* `governed_apply.py` shells out to `git` (integration branches, commits, status).
* In Docker, your API container has no `git` binary and no `.git` directory mounted, so all four git‑dependent endpoints fail:

  * `POST /runs/{run_id}/phases/{phase_id}/builder_result`
  * `POST /runs/{run_id}/phases/{phase_id}/auditor_request`
  * `POST /runs/{run_id}/phases/{phase_id}/auditor_result`
  * `GET /runs/{run_id}/integration_status`

You listed three options:

1. Add git to the Docker image.
2. External git service.
3. GitPython inside the container.

### Architectural recommendation

**Short answer:**
Use **Option 1 now** (git inside the API container, with repository mounted), but wrap it behind a **GitAdapter abstraction** so you can later plug in Option 2 (external service) without touching the rest of the system. Option 3 (GitPython) adds complexity and doesn’t solve the core problems (.git access and auth).

#### 1A. Baseline: Local GitAdapter in container

Introduce a very small abstraction in Autopack (names illustrative):

```python
class GitAdapter(Protocol):
    def ensure_integration_branch(self, repo: str, run_id: str) -> str: ...
    def apply_patch(self, repo: str, run_id: str, patch: str) -> str: ...
    def get_integration_status(self, repo: str, run_id: str) -> dict: ...
```

Concrete implementation:

```python
class LocalGitCliAdapter(GitAdapter):
    # Uses subprocess to call `git` in a working tree that has .git
```

Architecture:

* **Dockerfile**: install git (for Alpine-style base):

  ```dockerfile
  RUN apk add --no-cache git
  ```

* **Volumes**: mount the target repo(s) into the container, e.g.:

  ```yaml
  services:
    api:
      volumes:
        - /mnt/c/dev/Autopack:/app/autopack   # Autopack’s own repo if needed
        - /mnt/c/dev/my_target_repo:/workspace/my_target_repo
  ```

* **Config**: Autopack config maps `project_id` → repo path inside container:

  ```yaml
  projects:
    my_target_project:
      repo_path: /workspace/my_target_repo
  ```

Then `governed_apply.py` (or its replacement) becomes:

* “Look up repo path for this project_id.”
* Use `LocalGitCliAdapter` to:

  * `git status` / `git rev-parse` to verify working copy.
  * `git switch -c autonomous/{run_id}` or reuse branch.
  * `git apply` / `git commit` / `git tag` as needed.

Why this fits v7:

* Keeps the **governed apply path** exactly as specified (integration branch only, tags, etc.).
* No changes to Autopack’s public API or state machines.
* Predictable for local, single‑user or small‑team setups (your current scenario).

**Risks / trade‑offs:**

* Image size slightly larger (git installed).
* You must think about git auth (if you need `git push` to GitHub from inside the container):

  * Either mount SSH keys/PAT as secrets, or
  * Rely on a separate push step (CI) instead of pushing from container.
* You must be disciplined with volume mounts so `.git` is always there.

Given Autopack is still early and you control the environment, this is the sane starting point.

#### 1B. Future: ExternalGitServiceAdapter

For a more “cloud‑native” architecture (multi‑tenant, multiple repos, no .git in the API container), keep the same `GitAdapter` interface but add a second implementation later:

```python
class ExternalGitServiceAdapter(GitAdapter):
    # Calls a separate service (or GH Actions / GitHub API) to perform git operations
```

Pattern:

* Autopack **does not** touch the working tree directly.
* It sends “patch intents” to a git worker (or triggers a workflow) that:

  * checks out the repo,
  * applies and validates the patch,
  * pushes an integration branch,
  * reports status back by API or message queue.

This is architecturally clean and scalable, but:

* Requires another service or infra component.
* Adds latency and error modes you don’t need yet.

v7 is compatible with this: the playbook only cares that:

* changes go through a governed apply path,
* integration branches are used,
* CI verifies everything.

It doesn’t care whether `git` runs in the same container or somewhere else.

#### 1C. Why not GitPython as “solution 3”?

GitPython doesn’t remove the fundamental requirements:

* You still need a `.git` directory present.
* For many operations it shells out to git anyway.
* It adds another heavy dependency for little gain.

If you already have a stable `git` CLI path and your abstraction is `GitAdapter`, there is no strong architectural benefit to swapping subprocess calls for GitPython. It’s an implementation detail you can revisit later if needed.

**Conclusion for (1):**

* Implement `GitAdapter` with `LocalGitCliAdapter` now.
* Install git in the API container and mount the target repo(s) with `.git`.
* Keep the option open to introduce `ExternalGitServiceAdapter` later when you need remote or multi‑tenant operation.

---

## 2. Feature repository lookup system (enhancement)

You want:

* To describe features and behaviour conversationally.
* Cursor + Autopack should:

  * pick an appropriate stack (frameworks, libs, tools),
  * reuse existing features/code from known repositories,
  * generate a plan and then run autonomously,
  * with minimal prompting each time (configuration “baked in”).

### Fit with v7

Conceptually this is an extension of:

* §3 `PLAN_BOOTSTRAP` (planning),
* §4 phases/tiers,
* §6 high‑risk categories (external code intake),
* §7 StrategyEngine,
* plus the external‑code‑intake pattern from Tier‑4 (S1) in your earlier Cursor work.

You’re not changing the run state machine. You’re adding a **pre‑plan and phase‑type** for “feature reuse / external feature intake”.

### 2.1 Core components

I’d split this into three architectural pieces inside Autopack:

#### A. Feature Catalog + Stack Profiles

New config files in the Autopack repo, e.g.:

* `stack_profiles.yaml`
* `feature_catalog.yaml`

Examples:

```yaml
# stack_profiles.yaml
profiles:
  web_fastapi_pg:
    project_types: [ "api_service", "autonomous_orchestrator" ]
    backend: fastapi
    db: postgres
    frontend: none
    preferred_repos:
      - id: autopack_core
      - id: chatbot_project_orchestrator

  fullstack_rag:
    project_types: [ "rag_app", "chatbot" ]
    backend: fastapi
    db: postgres
    vector_db: qdrant
    frontend: nextjs
    preferred_repos:
      - id: my_rag_template
      - id: open_source_rag_boilerplate
```

```yaml
# feature_catalog.yaml
features:
  auth_basic:
    description: Basic username/password auth with JWT
    repos:
      - id: autopack_auth_module
        repo_url: https://github.com/...
        path: auth/
        license: MIT
        quality_score: 0.9

  autonomous_build_orchestrator:
    description: Orchestrator for autonomous builds
    repos:
      - id: chatbot_project_orchestrator
        repo_url: https://github.com/...
        path: backend/orchestrator/
        license: private
        quality_score: 0.95
```

This does two things:

* Encodes your **curated** sources (avoids arbitrary GitHub scraping).
* Associates them with project types and compatible stacks.

Aligns well with v7: StrategyEngine can treat `task_category = external_feature_reuse` with its own budgets and risk profile.

#### B. Feature Lookup + Planning Step

Extend `PLAN_BOOTSTRAP` in Autopack:

1. Take as input:

   * `comprehensive_plan.md` for the new project,
   * a short “project type” label (e.g. `rag_app`, `api_service`, `autonomous_orchestrator`),
   * your conversational feature list (which Cursor can turn into a structured list).

2. Autopack’s planning logic (with help from Cursor) then:

   * Chooses a `stack_profile` from `stack_profiles.yaml`.
   * Maps requested features (auth, orchestrator, dashboards, etc.) to entries in `feature_catalog.yaml`.
   * Produces:

     * A **stack selection** (fastapi+postgres+qdrant, etc.).
     * A set of candidate **reuse phases**, each with:

       * `task_category = external_feature_reuse`,
       * `source_repo_id`, `source_path`,
       * compatibility hints.

3. Generate phases for:

   * “Import and adapt auth module from repo X”.
   * “Import orchestrator backbone from repo Y”.
   * “Build new code where no candidate exists.”

These reuse phases feed directly into the v7 lifecycle; they’re just another phase type in Tier‑1 or Tier‑2.

#### C. External Code Intake Flow per Reuse Phase

Each `external_feature_reuse` phase uses a standardised flow (similar in spirit to Tier‑4 S1 external intake): 

1. **Discovery step**:

   * Builder (Cursor) is told:

     * which `source_repo` and `path` to inspect,
     * what behaviour/feature is needed,
     * what target repo and stack profile are.
   * It proposes:

     * specific files/regions to reuse,
     * the integration plan as a patch.

2. **Intake gate** (Supervisor):

   * Treat this patch with stricter high‑risk mapping:

     * Category: `external_code_intake` or `external_feature_reuse`.
     * Default `complexity = high`.
     * `ci_profile = strict`.
   * Optionally require an Auditor (Codex) pass for this category by default.

3. **CI + tests**:

   * Strict CI profile for these phases:

     * extra emphasis on license headers, import correctness, tests around new code.
   * Issues from these phases are tagged with `category = external_feature_*` for backlog.

This gives you the behaviour you want: “take what we need from earlier work and integrate it”, but fully inside the existing v7 governance and CI pipeline.

### 2.2 Budget and Safety treatment

For `external_feature_reuse` phases, StrategyEngine should:

* Set **budgets** expecting:

  * Slightly higher spike in **diff size** and **test churn**, but
  * Lower “fresh generation” cost.
* Use **strict CI** by default (because reuse can smuggle in obsolete patterns, incompatible assumptions).
* Apply **higher default severity** for issues in categories like:

  * `external_code_incompatible`,
  * `external_dependency_version_conflict`,
  * `external_license_mismatch`.

License governance:

* Restrict the catalog to:

  * your own repos, or
  * explicit licences you accept (MIT/BSD/Apache).
* For zero‑intervention runs, only use features from repos that are pre‑whitelisted in `feature_catalog.yaml`.
* If you later add dynamic “search GitHub” behaviour, keep that behind a **non‑zero‑intervention** path (e.g. separate curation run that populates the catalog).

### 2.3 Conversational planning with Cursor

Your desired workflow:

> I describe features and app behaviour once, Cursor figures out stack + reuse plan, and that plan is re‑usable for future builds.

Architecturally:

* Behind the scenes, that conversation becomes:

  * A `comprehensive_plan.md`,
  * A project type label and feature list,
  * Calls to Autopack’s **planning** endpoint that:

    * resolves stack_profile,
    * resolves feature_catalog entries,
    * emits a v7‑style plan with phases/tiers (including external‑reuse phases).

To make this repeatable:

* Store the **resulting plan** and **profile selection** in Autopack:

  * e.g. `plans/{project_type}/{plan_id}/plan.md`
  * or as a first‑class `PlanTemplate` model with metadata.

Next time you want a similar app, you can:

* reuse a plan template,
* tweak only the deltas in a short prompt,
* then let Autopack generate phases/tiers and run autonomously.

---

## 3. What you actually need to change in Autopack

You asked what belongs in code vs what you can leave to Cursor prompts.

Architecturally, in Autopack:

1. **Add data models/files**:

   * `stack_profiles.yaml`
   * `feature_catalog.yaml`
   * New `task_category` values:

     * `external_feature_reuse`
     * optionally `external_code_intake` for finer granularity.

2. **Extend StrategyEngine**:

   * Recognise the new categories.
   * Set budgets, CI profiles, and Auditor profiles accordingly.

3. **Extend planning**:

   * Add a pre‑planning function that:

     * maps project_type + features → stack_profile + reuse phases using the catalog.
   * Expose it as an API endpoint so Cursor can call it.

4. **Leave conversational glue to Cursor**:

   * You don’t hard‑code “conversation scripts” into Autopack; Cursor’s integration layer can:

     * collect your natural‑language feature description,
     * call Autopack’s planning API,
     * show you the resulting plan if you want,
     * then kick off `/runs/start` with that plan.

No changes needed to the v7 state machine, issue model, or metrics; you’re just adding a new phase type and more structured inputs.

---

### Summary

* **Git in Docker:**
  For your current single‑user, local Docker deployment, install `git` in the API container and mount repos with `.git`. Introduce a small `GitAdapter` abstraction so you can later switch to an external git service if needed. GitPython doesn’t solve the real problems here.

* **Feature repository lookup:**
  Add a **Feature Catalog** + **Stack Profiles** layer to Autopack (config files + StrategyEngine extensions), and treat external feature reuse as a first‑class `task_category` that maps into v7’s phases/tiers, budgets, and CI profiles. Keep it curated and pre‑whitelisted to preserve zero‑intervention runs.
