"""Domain services - the single place business logic lives.

The FastAPI routers are thin: they authenticate, then call in here. Keeping the
logic out of the route handlers is what lets the tests exercise it directly.
"""
