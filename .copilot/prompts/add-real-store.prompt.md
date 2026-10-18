---
description: Add or debug a real store for Real Store Mode
---
Real-store data lives only in `config/real_stores.yaml`. To add a store:
1. Confirm it publishes `https://<domain>/.well-known/ucp` (try the apex then `www`) and declares an MCP endpoint for `dev.ucp.shopping`.
2. Family-friendly brands only. No alcohol, tobacco/vape, adult supplements or adult content.
3. Add the entry (`id`, `name`, `domain`, `covers`, `enabled: true`). Never hardcode its MCP host in code.
4. Run `make probe-real` to see what it returns, and check results are on-topic.
5. Add or extend a test in `agent/app/real_stores/test_real.py` using the fake transport. No live calls in tests.
6. Real stores only get carts. Never call or allow checkout tools.
