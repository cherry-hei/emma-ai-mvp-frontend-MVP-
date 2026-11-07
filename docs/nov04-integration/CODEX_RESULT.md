Implemented the scoped **review-only candidate**: persistent owner-managed policy, version/CAS, retry identity, audit, and deterministic single-request evaluation.

- **97 tests passed, 1 skipped**: 72 new tests plus 25 regression tests.
- Optional SQL run: **1 setup error** because the sandbox blocked PostgreSQL socket creation; migration/RLS remain unverified.
- Automatic approval remains unavailable pending transactional balance, lock, window and rule checks.
- Router registration remains with the parent.

Details and blockers: [AUTO_APPROVAL_API.md](/home/ubuntu/emma-oct31-chat-window/autoapproval/docs/nov04-integration/AUTO_APPROVAL_API.md).

No push, deployment, live migration or paid API usage. Changes remain uncommitted on source `caff1c86`; Git metadata is read-only.