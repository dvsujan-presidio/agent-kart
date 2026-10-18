---
description: Start AgentKart locally and verify it end to end
---
1. Read `.copilot/instructions.md`.
2. Run `make start`, then `curl localhost:8000/health` and `curl localhost:8000/real/config` (expect `"available": true` for real stores).
3. Run `make test` and `make eval`; both must be fully green.
4. Run `make demo` (demo stores, real model) and, with a US network exit, `make ui-real-test` (real stores).
5. Report what passed and what failed with the exact output. Do not mark anything verified that you did not run.
