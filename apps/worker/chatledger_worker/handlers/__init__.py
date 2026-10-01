from chatledger_worker.handlers.noop import KIND as NOOP_KIND
from chatledger_worker.handlers.noop import handle_noop
from chatledger_worker.registry import HandlerRegistry


def default_registry() -> HandlerRegistry:
    registry = HandlerRegistry()
    registry.register(NOOP_KIND, handle_noop)
    return registry


__all__ = ["default_registry"]
