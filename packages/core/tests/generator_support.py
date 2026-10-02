"""Helpers shared by the generator tests: render a whole export into memory."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache

from chatledger_core.domain.generator.ground_truth import AnomalyRecord
from chatledger_core.domain.generator.params import GenerationParams, validate_params
from chatledger_core.domain.generator.plan import Workspace, build_workspace
from chatledger_core.domain.generator.render import ConversationRenderer

EVENT_SUBTYPES = {"channel_join", "channel_leave", "message_changed", "message_deleted"}


@dataclass
class Rendered:
    workspace: Workspace
    files: dict[str, bytes] = field(default_factory=dict)  # path -> bytes
    owner: dict[str, str] = field(default_factory=dict)  # path -> conversation id
    anomalies: list[AnomalyRecord] = field(default_factory=list)

    def records(self) -> list[tuple[str, str, dict]]:  # type: ignore[type-arg]
        out = []
        for path, data in self.files.items():
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                continue
            out.extend((self.owner[path], path, r) for r in parsed)
        return out

    def regular(self) -> list[dict]:  # type: ignore[type-arg]
        return [r for _, _, r in self.records() if r.get("subtype") not in EVENT_SUBTYPES]


def render_params(params: GenerationParams) -> Rendered:
    workspace = build_workspace(params)
    result = Rendered(workspace)
    for segment in workspace.segments:
        for f in ConversationRenderer(workspace, segment).files():
            result.files[f.path] = f.data
            result.owner[f.path] = segment.conv.id
            result.anomalies.extend(f.anomalies)
    return result


@lru_cache(maxsize=16)
def render_cached(seed: int, preset: str, profile: str) -> Rendered:
    return render_params(validate_params(seed=seed, preset=preset, profile=profile))
