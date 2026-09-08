"""Shared, event-loop-aware ``httpx`` client for every Sicredi call.

Each request used to build its own ``httpx.AsyncClient``, so every boleto paid
for a fresh DNS lookup, TCP connect and TLS handshake — visible in the logs as a
``load_ssl_context`` / ``connect_tcp`` / ``start_tls`` trio per consulta.
Reconciling a few hundred boletos spent most of its time in handshakes and blew
the manual sync's per-call timeout.

The client is cached per running event loop: Celery opens a brand new loop for
every task (``app.tasks._async_helpers.run_in_task_loop``) and an httpx client,
like the asyncpg pool, cannot be reused across loops.
"""

import asyncio

import httpx

from app.services.sicredi.config import HTTP_TIMEOUT

# Sicredi throttles aggressively; a small pool keeps connections warm without
# opening a burst of sockets when the sync fans out.
_LIMITS = httpx.Limits(
    max_connections=10,
    max_keepalive_connections=10,
    keepalive_expiry=60.0,
)

# id(loop) -> (loop, client). The loop is kept in the value so a recycled id
# never hands back a client bound to a dead loop.
_clients: dict[int, tuple[asyncio.AbstractEventLoop, httpx.AsyncClient]] = {}


def get_http_client() -> httpx.AsyncClient:
    """Return the pooled client for the running loop, creating it if needed."""
    loop = asyncio.get_running_loop()
    entry = _clients.get(id(loop))
    if entry is not None and entry[0] is loop and not entry[1].is_closed:
        return entry[1]

    client = httpx.AsyncClient(timeout=HTTP_TIMEOUT, limits=_LIMITS)
    _clients[id(loop)] = (loop, client)

    # Forget clients whose loop is already closed; their sockets died with it.
    for key, (cached_loop, _) in list(_clients.items()):
        if cached_loop is not loop and cached_loop.is_closed():
            _clients.pop(key, None)

    return client
