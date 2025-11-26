# Build Plan: Task Tracker Application

**Project ID**: task-tracker-v1
**Build Date**: 2025-11-26
**Strategy**: Manual supervised build (first application)
**Goal**: Validate Phase 1b implementation with a complete 20-50 phase build

---

## Executive Summary

This is our **first production build** using Autopack Phase 1b. We're building a simple task tracker to validate:

1. **Model routing** (8 fine-grained categories)
2. **Budget warnings** (alert-based system)
3. **Context ranking** (JIT loading for 30-50% token savings)
4. **Risk scoring** (LOC delta, critical paths, test coverage)
5. **Learned rules** (accumulation across phases)
6. **Dual auditing** (security-critical categories only)

---

## Tech Stack

- **Backend**: FastAPI + PostgreSQL + SQLAlchemy + Alembic
- **Frontend**: React + Vite + TailwindCSS
- **Testing**: pytest + React Testing Library
- **Deployment**: Docker Compose (already configured)

---

## Build Tiers and Phases

### **Tier 1: Database and Backend Foundation** (8 phases)

#### Phase 1.1: Database Schema - Task Model
- **Category**: `schema_contract_change_additive`
- **Complexity**: medium
- **Description**: Create Task model with id, title, description, completed, created_at, updated_at
- **Acceptance Criteria**:
  - SQLAlchemy model defined in `src/autopack/models/task.py`
  - Alembic migration generated
  - Schema includes proper indexes (id primary key, created_at for sorting)
  - Type hints on all fields
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~40 (schema change + 50 LOC)

#### Phase 1.2: Run Alembic Migration
- **Category**: `schema_contract_change_additive`
- **Complexity**: low
- **Description**: Apply migration to create tasks table
- **Acceptance Criteria**:
  - Migration applied successfully
  - `tasks` table exists in database
  - Schema matches model definition
- **Expected Model**: gpt-4o-mini (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~30 (destructive operation)

#### Phase 1.3: CRUD API Endpoints - Create Task
- **Category**: `core_backend_high`
- **Complexity**: medium
- **Description**: POST /api/tasks endpoint to create new tasks
- **Acceptance Criteria**:
  - Endpoint defined in `src/autopack/routers/tasks.py`
  - Pydantic request/response models
  - Input validation (title required, 1-200 chars)
  - Returns 201 with created task
  - Type hints on all functions
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~50 (critical path + 80 LOC)

#### Phase 1.4: CRUD API Endpoints - List Tasks
- **Category**: `core_backend_high`
- **Complexity**: medium
- **Description**: GET /api/tasks endpoint to list all tasks
- **Acceptance Criteria**:
  - Supports pagination (offset, limit query params)
  - Supports filtering by completed status
  - Sorted by created_at descending
  - Returns 200 with task array
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~45 (critical path + 60 LOC)

#### Phase 1.5: CRUD API Endpoints - Update Task
- **Category**: `core_backend_high`
- **Complexity**: medium
- **Description**: PUT /api/tasks/{task_id} endpoint to update tasks
- **Acceptance Criteria**:
  - Supports partial updates (title, description, completed)
  - Returns 404 if task not found
  - Returns 200 with updated task
  - Updates updated_at timestamp
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~50 (critical path + 70 LOC)

#### Phase 1.6: CRUD API Endpoints - Delete Task
- **Category**: `core_backend_high`
- **Complexity**: low
- **Description**: DELETE /api/tasks/{task_id} endpoint
- **Acceptance Criteria**:
  - Soft delete (sets deleted_at timestamp)
  - Returns 404 if task not found
  - Returns 204 on success
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~40 (critical path + 30 LOC)

#### Phase 1.7: Backend Unit Tests - CRUD Operations
- **Category**: `tests`
- **Complexity**: medium
- **Description**: pytest tests for all CRUD endpoints
- **Acceptance Criteria**:
  - Test file: `tests/test_tasks_api.py`
  - Tests for create, list, update, delete
  - Tests for validation errors
  - Tests for 404 cases
  - Coverage >80% for tasks router
- **Expected Model**: gpt-4o-mini (builder - cheap_first), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~25 (tests + 150 LOC)

#### Phase 1.8: API Documentation - OpenAPI Spec
- **Category**: `docs`
- **Complexity**: low
- **Description**: Ensure FastAPI auto-generated docs are complete
- **Acceptance Criteria**:
  - All endpoints have docstrings
  - Request/response models documented
  - Example values provided
  - /docs endpoint renders correctly
- **Expected Model**: gpt-4o-mini (builder - cheap_first), gpt-4o-mini (auditor - cheap_first)
- **Risk Score**: ~15 (docs + 40 LOC)

---

### **Tier 2: Frontend Foundation** (7 phases)

#### Phase 2.1: Vite + React Setup
- **Category**: `core_frontend_medium`
- **Complexity**: low
- **Description**: Initialize Vite React app in `frontend/` directory
- **Acceptance Criteria**:
  - Vite config with HMR
  - TailwindCSS configured
  - ESLint + Prettier setup
  - Dev server runs on port 5173
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~35 (new frontend + 100 LOC)

#### Phase 2.2: API Client - Fetch Wrapper
- **Category**: `external_feature_reuse_remote`
- **Complexity**: low
- **Description**: Create typed API client for backend
- **Acceptance Criteria**:
  - File: `frontend/src/api/client.ts`
  - TypeScript types for Task
  - Fetch wrapper with error handling
  - Base URL from environment variable
- **Expected Model**: gpt-5 (builder - best_first for external integration), claude-opus-4-5 (auditor - best_first)
- **Risk Score**: ~55 (external dependency + 80 LOC)

#### Phase 2.3: Task List Component
- **Category**: `core_frontend_medium`
- **Complexity**: medium
- **Description**: React component to display task list
- **Acceptance Criteria**:
  - File: `frontend/src/components/TaskList.tsx`
  - Fetches tasks on mount
  - Displays loading state
  - Displays error state
  - Renders task cards with title, description, status
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~45 (UI component + 120 LOC)

#### Phase 2.4: Task Create Form
- **Category**: `core_frontend_medium`
- **Complexity**: medium
- **Description**: Form component to create new tasks
- **Acceptance Criteria**:
  - File: `frontend/src/components/TaskForm.tsx`
  - Controlled inputs for title, description
  - Client-side validation
  - Calls POST /api/tasks
  - Clears form on success
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~45 (form validation + 100 LOC)

#### Phase 2.5: Task Update - Toggle Complete
- **Category**: `core_frontend_medium`
- **Complexity**: low
- **Description**: Checkbox to toggle task completion
- **Acceptance Criteria**:
  - Checkbox in TaskList component
  - Calls PUT /api/tasks/{id} on change
  - Optimistic UI update
  - Reverts on error
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~40 (state management + 60 LOC)

#### Phase 2.6: Task Delete Button
- **Category**: `core_frontend_medium`
- **Complexity**: low
- **Description**: Delete button for each task
- **Acceptance Criteria**:
  - Confirmation dialog
  - Calls DELETE /api/tasks/{id}
  - Removes from UI on success
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~35 (UI action + 50 LOC)

#### Phase 2.7: Frontend Tests - Components
- **Category**: `tests`
- **Complexity**: medium
- **Description**: React Testing Library tests for components
- **Acceptance Criteria**:
  - Tests for TaskList, TaskForm
  - Mocked API calls
  - Tests for loading/error states
  - Coverage >70% for components
- **Expected Model**: gpt-4o-mini (builder - cheap_first), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~25 (tests + 130 LOC)

---

### **Tier 3: Integration and Polish** (6 phases)

#### Phase 3.1: CORS Configuration
- **Category**: `security_auth_change`
- **Complexity**: low
- **Description**: Configure CORS for frontend-backend communication
- **Acceptance Criteria**:
  - FastAPI CORS middleware
  - Allow origins: http://localhost:5173
  - Allow credentials: true
  - Allow methods: GET, POST, PUT, DELETE
- **Expected Model**: gpt-5 (builder - best_first for security), claude-opus-4-5 (auditor - dual auditing)
- **Risk Score**: ~65 (security config + 30 LOC)

#### Phase 3.2: Environment Variables
- **Category**: `core_backend_high`
- **Complexity**: low
- **Description**: Externalize configuration to .env
- **Acceptance Criteria**:
  - Backend: DATABASE_URL, CORS_ORIGINS
  - Frontend: VITE_API_URL
  - Example .env.example files
  - pydantic-settings for backend config
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~30 (config + 40 LOC)

#### Phase 3.3: Error Handling - 500 Responses
- **Category**: `core_backend_high`
- **Complexity**: low
- **Description**: Global error handler for uncaught exceptions
- **Acceptance Criteria**:
  - FastAPI exception handler
  - Logs errors to console
  - Returns 500 with safe error message
  - Doesn't leak stack traces
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~40 (error handling + 50 LOC)

#### Phase 3.4: Integration Tests - E2E Scenarios
- **Category**: `tests`
- **Complexity**: high
- **Description**: End-to-end tests for full workflows
- **Acceptance Criteria**:
  - Test file: `tests/test_integration.py`
  - Create → List → Update → Delete flow
  - Tests with real database (test container)
  - Cleanup between tests
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~55 (complex tests + 180 LOC)

#### Phase 3.5: Docker Compose - Frontend Service
- **Category**: `external_feature_reuse_remote`
- **Complexity**: low
- **Description**: Add frontend service to docker-compose.yml
- **Acceptance Criteria**:
  - Service name: task-tracker-frontend
  - Builds from frontend/Dockerfile
  - Exposed on port 5173
  - Depends on backend API
- **Expected Model**: gpt-5 (builder - best_first for docker integration), claude-opus-4-5 (auditor)
- **Risk Score**: ~50 (docker config + 40 LOC)

#### Phase 3.6: README and Deployment Docs
- **Category**: `docs`
- **Complexity**: low
- **Description**: Complete README for task tracker
- **Acceptance Criteria**:
  - Installation steps
  - Running with docker-compose
  - API endpoints documentation
  - Frontend usage guide
- **Expected Model**: gpt-4o-mini (builder - cheap_first), gpt-4o-mini (auditor - cheap_first)
- **Risk Score**: ~15 (docs + 80 LOC)

---

## Summary Stats (Estimated)

- **Total Phases**: 21
- **Total LOC**: ~1,700 (estimated)
- **Category Distribution**:
  - schema_contract_change_additive: 2 (9.5%)
  - core_backend_high: 6 (28.6%)
  - core_frontend_medium: 5 (23.8%)
  - external_feature_reuse_remote: 2 (9.5%)
  - security_auth_change: 1 (4.8%)
  - tests: 4 (19.0%)
  - docs: 2 (9.5%)
  - general: 0 (0%)

- **Strategy Distribution**:
  - best_first: 4 phases (security + external integration)
  - progressive: 14 phases (core backend/frontend)
  - cheap_first: 3 phases (docs + tests)

- **Token Budget Estimate** (rough):
  - Best-first phases: 4 × 15k = 60k tokens
  - Progressive phases: 14 × 10k = 140k tokens
  - Cheap-first phases: 3 × 5k = 15k tokens
  - **Total**: ~215k tokens (well under 50M quota)

- **Risk Score Distribution**:
  - High (>60): 2 phases (CORS, Docker)
  - Medium (40-60): 11 phases
  - Low (<40): 8 phases

---

## Manual Tracking Plan

We'll track these metrics manually during the build:

### 1. Category Accuracy
- Does `schema_contract_change_additive` correctly trigger for migrations?
- Does `security_auth_change` correctly trigger dual auditing for CORS?
- Does `external_feature_reuse_remote` correctly escalate to best_first for Docker/API client?

### 2. Escalation Frequency
- How often does progressive strategy escalate from gpt-4o to gpt-5?
- After how many failed attempts?
- Were escalations necessary?

### 3. Token Savings (Context Ranking)
- Estimate tokens without context ranking (all files loaded)
- Actual tokens used (with JIT loading)
- Calculate % savings

### 4. Risk Scorer Calibration
- Which phases had high risk scores?
- Did high-risk phases actually have more issues?
- Correlation between risk score and audit failures?

### 5. Budget Warnings
- Did we hit any 80% soft limit warnings?
- Were warnings helpful?
- Did alert-based system work better than hard blocks?

### 6. Learned Rules Effectiveness
- How many rules were recorded?
- Were rules applied in later phases?
- Did rules reduce audit failures over time?

---

## Execution Approach

Since this is our first build, we'll use a **manual supervised approach**:

1. **Execute phases sequentially** (one at a time)
2. **Review each Builder output** before auditing
3. **Manually call Auditor** after each Builder output
4. **Record observations** in manual tracking file
5. **Update todo list** as we complete phases
6. **Commit changes** after each successful phase

This approach lets us observe the system in action and validate Phase 1b implementation.

---

## Success Criteria

This build is successful if:

1. ✅ All 21 phases complete with working code
2. ✅ No quota exhaustion (under 50M OpenAI tokens)
3. ✅ At least 5 learned rules recorded
4. ✅ Security phases use dual auditing (CORS phase)
5. ✅ Context ranking works (no file-not-found errors)
6. ✅ Risk scorer provides useful signals
7. ✅ Manual tracking reveals actionable insights for tuning

---

## Next Steps

1. Create `.autonomous_runs/task-tracker-v1/` directory
2. Create `MANUAL_TRACKING.md` file
3. Execute Phase 1.1 (Database Schema)
4. Record observations after each phase
5. Review data after 10 phases (mid-point check)
6. Complete all 21 phases
7. Analyze final results and decide on Phase 2 implementation

---

**Ready to Start?** Let's build! 🚀
