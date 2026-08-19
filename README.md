# AION AXON

AION AXON is an autonomous AI execution architecture built around:

- Google ADK
- Gemini
- Firestore
- Taskmaster workflow planning
- Guardian governance
- Human approval
- Kill switch
- Unified execution gate
- Tool registry
- Persistent workflow state

## Architecture

User Request
    ↓
Taskmaster / Planner
    ↓
WorkflowState
    ↓
Guardian
    ├── ALLOW
    ├── APPROVAL_REQUIRED
    └── REFUSE
    ↓
Unified Execution Gate
    ↓
Tools / External Actions
    ↓
Firestore

## Current Status

Core foundation successfully initialized.

- Google Cloud project configured
- Firestore Native database configured
- Google ADC configured
- Google ADK installed
- AXON planner operational
- Guardian operational
- Human approval system operational
- Kill switch operational
- Unified execution gate operational
- Tool registry operational
- Calculator operational
- Web research tool created
- WorkflowState operational
- Taskmaster connected to WorkflowState

## Development

Activate the virtual environment:

    .\.venv\Scripts\Activate.ps1

Run the ADK application:

    adk run app

## Security

Secrets, credentials, virtual environments, runtime databases, logs and local configuration must never be committed to source control.

## Storage Strategy

Laptop:
Primary development workspace.

GitHub:
Version control and source recovery.

Google Drive:
Independent project backup/archive.

Firestore:
Runtime state and application memory.
