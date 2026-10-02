from collections.abc import Mapping

from chatledger_worker.handlers.noop import KIND as NOOP_KIND
from chatledger_worker.handlers.noop import handle_noop
from chatledger_worker.registry import Handler, HandlerRegistry


def default_registry(extra: Mapping[str, Handler] | None = None) -> HandlerRegistry:
    """The built-in ``noop`` handler plus any handlers a composition root supplies."""
    registry = HandlerRegistry()
    registry.register(NOOP_KIND, handle_noop)
    for kind, handler in (extra or {}).items():
        registry.register(kind, handler)
    return registry


__all__ = ["default_registry"]
