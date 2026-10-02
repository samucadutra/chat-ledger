"""Ground-truth model: anomaly records, ordering and the canonical JSON document."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

from chatledger_core.domain.generator.rates import REASON_CODES, AnomalyType

SCHEMA_VERSION = 1

# (anomaly_type, conversation_id, message_ts | None, source_file, record_index | None)
AnomalyRecord = tuple[str, str, str | None, str, int | None]


def sort_key(record: AnomalyRecord) -> tuple[str, str, str, str, int]:
    """Conversation, then ``ts`` (null first), then type; location breaks remaining ties."""
    anomaly_type, conversation_id, message_ts, source_file, record_index = record
    return (
        conversation_id,
        message_ts or "",
        anomaly_type,
        source_file,
        -1 if record_index is None else record_index,
    )


@dataclass(frozen=True)
class Overlap:
    base_seed: int
    days_pct: int


@dataclass(frozen=True)
class GroundTruthMeta:
    generator_version: str
    seed: int
    preset: str
    profile: str
    messages: int
    conversations: int
    message_records: int
    overlap: Overlap | None = None


def reason_code(anomaly_type: str) -> str:
    return REASON_CODES[AnomalyType(anomaly_type)]


def anomaly_to_dict(record: AnomalyRecord) -> dict[str, object]:
    anomaly_type, conversation_id, message_ts, source_file, record_index = record
    return {
        "anomaly_type": anomaly_type,
        "conversation_id": conversation_id,
        "message_ts": message_ts,
        "source_file": source_file,
        "record_index": record_index,
        "expected_reason_code": reason_code(anomaly_type),
    }


def _dumps(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def canonical_chunks(meta: GroundTruthMeta, anomalies: Sequence[AnomalyRecord]) -> Iterator[bytes]:
    """Stream the canonical document (sorted keys, ``,`` and ``:`` separators, final newline).

    ``anomalies`` must already be sorted with :func:`sort_key`. The array is the first key in
    sorted order, so the rest of the document is emitted as one object after it.
    """
    by_type = Counter(a[0] for a in anomalies)
    rest: dict[str, object] = {
        "conversations": meta.conversations,
        "generator_version": meta.generator_version,
        "messages": meta.messages,
        "overlap": (
            None
            if meta.overlap is None
            else {"base_seed": meta.overlap.base_seed, "days_pct": meta.overlap.days_pct}
        ),
        "preset": meta.preset,
        "profile": meta.profile,
        "schema_version": SCHEMA_VERSION,
        "seed": meta.seed,
        "totals": {
            "anomalies": len(anomalies),
            "anomalies_by_type": dict(sorted(by_type.items())),
            "conversations": meta.conversations,
            "message_records": meta.message_records,
        },
    }
    yield b'{"anomalies":['
    batch: list[str] = []
    first = True
    for record in anomalies:
        batch.append(_dumps(anomaly_to_dict(record)))
        if len(batch) >= 2_000:
            yield (("" if first else ",") + ",".join(batch)).encode()
            first = False
            batch = []
    if batch:
        yield (("" if first else ",") + ",".join(batch)).encode()
    yield ("]," + _dumps(rest)[1:] + "\n").encode()


def build_document(meta: GroundTruthMeta, anomalies: Iterable[AnomalyRecord]) -> bytes:
    ordered = sorted(anomalies, key=sort_key)
    return b"".join(canonical_chunks(meta, ordered))
