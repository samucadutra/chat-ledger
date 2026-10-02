from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime

from chatledger_core.domain.generator.params import validate_params
from chatledger_core.domain.generator.plan import ConvKind, build_workspace
from chatledger_core.domain.generator.render import ConversationRenderer, render_root_files
from generator_support import Rendered, render_params

TS = re.compile(r"^\d{10}\.\d{6}$")


def test_reply_broadcast_reaction_file_bot_counts(small_clean: Rendered) -> None:
    regular = small_clean.regular()
    assert len(regular) == 10_000
    assert sum(1 for r in regular if "thread_ts" in r and r["thread_ts"] != r["ts"]) == 2_000
    assert sum(1 for r in regular if r.get("subtype") == "thread_broadcast") == 60
    assert sum(1 for r in regular if "reactions" in r) == 800
    assert sum(1 for r in regular if "files" in r) == 400
    assert sum(1 for r in regular if "bot_id" in r) == 200
    assert all("bot_profile" in r and r["bot_profile"]["name"] for r in regular if "bot_id" in r)


def test_mentions_and_links_resolve(small_clean: Rendered) -> None:
    users = {u.id for u in small_clean.workspace.users}
    texts = [r["text"] for r in small_clean.regular()]
    mentions = [m for t in texts for m in re.findall(r"<@(U[0-9A-F]+)>", t)]
    assert len(mentions) >= 1_000 and set(mentions) <= users
    assert sum(1 for t in texts if re.search(r"<https?://[^|>]+\|[^>]+>", t)) == 1_000


def test_clean_export_has_nothing_to_quarantine(small_clean: Rendered) -> None:
    assert small_clean.anomalies == []
    users = {u.id for u in small_clean.workspace.users}
    for _conv_id, path, rec in small_clean.records():
        assert TS.match(rec["ts"])
        stamp = datetime.fromtimestamp(int(rec["ts"].split(".")[0]), UTC).date().isoformat()
        assert stamp == path.split("/")[1][:10]
        assert rec.get("subtype") not in {"message_changed", "message_deleted", "x_custom_subtype"}
        if "user" in rec:
            assert rec["user"] in users
        assert isinstance(rec["text"], str)
    for _, _, rec in small_clean.records():
        for f in rec.get("files", []):
            assert {"id", "name", "mimetype"} <= set(f)


def test_thread_parents_resolve(small_clean: Rendered) -> None:
    ts_by_conv: dict[str, set[str]] = defaultdict(set)
    for conv_id, _, rec in small_clean.records():
        ts_by_conv[conv_id].add(rec["ts"])
    for conv_id, _, rec in small_clean.records():
        if "thread_ts" in rec:
            assert rec["thread_ts"] in ts_by_conv[conv_id]


def test_membership_events_alternate(small_clean: Rendered) -> None:
    per: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for conv_id, _, rec in small_clean.records():
        if rec.get("subtype") in {"channel_join", "channel_leave"}:
            per[(conv_id, rec["user"])].append((rec["ts"], rec["subtype"]))
    assert per
    kinds = Counter()
    for events in per.values():
        events.sort()
        expected = "channel_join"
        for _, subtype in events:
            assert subtype == expected
            expected = "channel_leave" if expected == "channel_join" else "channel_join"
        kinds.update(s for _, s in events)
    assert kinds["channel_leave"] > 0
    dms = {
        c.id for c in small_clean.workspace.conversations if c.kind in (ConvKind.DM, ConvKind.MPIM)
    }
    assert not any(conv in dms for conv, _ in per)


def test_deleted_users_stay_listed() -> None:
    ws = build_workspace(validate_params(seed=42, preset="small", profile="clean"))
    users = json.loads(render_root_files(ws)["users.json"])
    assert len(users) == 40 and any(u["deleted"] for u in users)


def test_conversation_render_independent_of_order() -> None:
    params = validate_params(seed=42, preset="small", profile="default")
    ws = build_workspace(params)
    seg = ws.segments[7]
    alone = [f.data for f in ConversationRenderer(ws, seg).files()]
    for other in ws.segments[:7]:
        list(ConversationRenderer(ws, other).files())
    again = [f.data for f in ConversationRenderer(ws, seg).files()]
    assert alone == again and alone


def test_canonical_json(small_default: Rendered) -> None:
    parsed = 0
    for data in small_default.files.values():
        try:
            value = json.loads(data)
        except json.JSONDecodeError:
            continue
        assert json.dumps(value, sort_keys=True, separators=(",", ":")).encode() == data
        parsed += 1
    assert parsed > 900


def test_span_and_conversation_count(small_clean: Rendered) -> None:
    dates = {p.split("/")[1][:10] for p in small_clean.files}
    assert len(dates) == 90
    assert len({p.split("/")[0] for p in small_clean.files}) == 50


def test_custom_preset_renders_exact_counts() -> None:
    params = validate_params(
        seed=7, preset="custom", profile="clean", messages=2_000, conversations=20
    )
    result = render_params(params)
    assert len(result.regular()) == 2_000
    assert len({p.split("/")[0] for p in result.files}) == 20
