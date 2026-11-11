# Development task state

This branch stores only sanitized technical progress for the approved draft work in PR #17. It is not an application release and must not be merged into main or the product feature branch.

The current queue is `.emma/automation-state.json`. Updates require a fresh content SHA and lease ownership check. Do not store credentials, private conversations, customer data or private repository source here. Release and important business decisions remain in the authenticated ChatGPT conversation.

Vercel automatic deployment is disabled for this branch by its branch-specific `vercel.json`. The existing deployment workflow is main-only and must never be invoked by this queue.
