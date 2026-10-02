"""Conversation renderer: day files for one conversation segment, plus the root JSON files.

Rendering is a pure function of ``(workspace, segment)``: the conversation uses its own
``random.Random(sub_seed)``, so it renders identically alone (re-delivery replay) or in
sequence. Output is canonical JSON (sorted keys, ``,`` and ``:`` separators).
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from chatledger_core.domain.generator.anomalies import AnomalyPlan, select_anomalies
from chatledger_core.domain.generator.ground_truth import AnomalyRecord
from chatledger_core.domain.generator.plan import (
    ConvKind,
    SegmentPlan,
    Workspace,
    day_date,
    day_epoch,
)
from chatledger_core.domain.generator.rates import AnomalyType, percent_count
from chatledger_core.domain.generator.vocab import EMOJI, FILE_TYPES, LINK_LABELS, SENTENCES

_BASE_SECONDS = 80_000  # base messages fall in the first 80,000 seconds of a day
_SEQ_MEMBERSHIP = 10_000_000
_SEQ_EVENT = 20_000_000
_DAY_SECONDS = 86_400
_MICRO_MOD = 1_000_000
UNKNOWN_SUBTYPE = "x_custom_subtype"
_EAF_DELETE = object()  # tag of the delete event preceding an edit-after-delete edit


Record = dict[str, Any]
Item = list[Any]  # [sec, seq, record, event kind, base index, ts, micro, target ts]


def dumps(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@dataclass
class GeneratedFile:
    path: str
    day: int  # absolute day index
    data: bytes
    base_count: int
    anomalies: list[AnomalyRecord]
    record_ts: list[str | None] | None  # parseable records, only when requested


def _phantom_ts(epoch: int, k: int) -> str:
    """A well-formed ``ts`` that no rendered record carries (the day before, micro 999999)."""
    return f"{epoch - 1 - (k % 500)}.999999"


class ConversationRenderer:
    def __init__(self, workspace: Workspace, segment: SegmentPlan) -> None:
        self._ws = workspace
        self._seg = segment

    # ------------------------------------------------------------------ helpers
    def _path(self, abs_day: int) -> str:
        date_ = day_date(self._ws.params.days, abs_day)
        return f"{self._seg.conv.folder}/{date_.isoformat()}.json"

    def _choose_days(self, rng: random.Random) -> list[int]:
        seg = self._seg
        count = seg.active_days
        if seg.force_ends:
            middle = rng.sample(range(1, seg.day_count - 1), count - 2) if count > 2 else []
            return sorted([0, seg.day_count - 1, *middle])
        return sorted(rng.sample(range(seg.day_count), count))

    # ------------------------------------------------------------------ rendering
    def files(self, *, collect_ts: bool = False) -> Iterator[GeneratedFile]:
        ws, seg = self._ws, self._seg
        conv, quotas, n = seg.conv, seg.quotas, seg.messages
        if n <= 0:
            return
        rng = random.Random(seg.sub_seed)
        team, days_total = ws.team_id, ws.params.days
        members, user_ids, bot_list = conv.members, ws.user_ids, ws.bots
        member_count, user_count = len(members), len(user_ids)

        active = self._choose_days(rng)
        day_total = len(active)
        counts = [1] * day_total
        for di in rng.choices(range(day_total), k=n - day_total):
            counts[di] += 1
        day_start: list[int] = []
        running = 0
        for c in counts:
            day_start.append(running)
            running += c

        first_of_day = set(day_start)
        non_first = [g for g in range(n) if g not in first_of_day]
        replies = set(rng.sample(non_first, min(quotas.replies, len(non_first))))
        rest = [g for g in non_first if g not in replies]
        bots = set(rng.sample(rest, min(quotas.bots, len(rest))))
        broadcasts = set(rng.sample(sorted(replies), min(quotas.broadcasts, len(replies))))
        reactions = set(rng.sample(range(n), min(quotas.reactions, n)))
        file_records = set(rng.sample(range(n), min(quotas.files, n)))
        mentions = set(rng.sample(range(n), min(quotas.mentions, n)))
        links = set(rng.sample(range(n), min(quotas.links, n)))

        parent_of: dict[int, int] = {}
        for di in range(day_total):
            start = day_start[di]
            candidates: list[int] = []
            for g in range(start, start + counts[di]):
                if g in replies:
                    parent_of[g] = candidates[rng.randrange(len(candidates))]
                elif g not in bots:
                    candidates.append(g)
        parents = set(parent_of.values())

        plan: AnomalyPlan = select_anomalies(
            rng,
            quotas,
            messages=n,
            day_start=day_start,
            active_days=active,
            day_count=seg.day_count,
            replies=sorted(replies),
            parents=parents,
            bots=bots,
            file_records=sorted(file_records),
        )
        orphans = {g for g, kind in plan.records.items() if kind is AnomalyType.ORPHAN_REPLY}
        children: dict[int, list[int]] = {}
        for child, parent in sorted(parent_of.items()):
            if child not in orphans:
                children.setdefault(parent, []).append(child)

        # Membership events (channels and groups only).
        membership: dict[int, list[tuple[int, str, str]]] = {}
        if seg.membership and member_count:
            leavers = set(rng.sample(range(member_count), percent_count(30, member_count)))
            rejoiners = set(rng.sample(sorted(leavers), percent_count(10, len(leavers))))
            kinds = ("channel_join", "channel_leave", "channel_join")
            for mi, uid in enumerate(members):
                total = 3 if mi in rejoiners else 2 if mi in leavers else 1
                points = sorted(
                    (rng.randrange(day_total), rng.randrange(_DAY_SECONDS)) for _ in range(total)
                )
                for (di, sec), kind in zip(points, kinds, strict=False):
                    membership.setdefault(di, []).append((sec, uid, kind))

        events_by_day: dict[int, list[tuple[AnomalyType, int | None]]] = {}
        for event in plan.events:
            events_by_day.setdefault(event.day, []).append((event.kind, event.target))

        empty_rel = list(plan.empty_days)
        serial = 0
        file_serial = 0
        unlisted = 0
        phantom_k = 0
        emitted_empty = 0

        for di in range(day_total):
            rel_day = active[di]
            while emitted_empty < len(empty_rel) and empty_rel[emitted_empty] < rel_day:
                yield self._empty_file(empty_rel[emitted_empty])
                emitted_empty += 1
            abs_day = seg.day_offset + rel_day
            epoch = day_epoch(days_total, abs_day)
            path = self._path(abs_day)
            start, count = day_start[di], counts[di]
            seconds = sorted(rng.randrange(_BASE_SECONDS) for _ in range(count))

            items: list[Item] = []  # [sec, seq, record, kind-or-None, g]
            by_g: dict[int, Item] = {}
            for j in range(count):
                g = start + j
                rec: Record = {"type": "message", "team": team}
                if g in bots:
                    bot = bot_list[rng.randrange(len(bot_list))]
                    rec["subtype"] = "bot_message"
                    rec["bot_id"] = bot.id
                    rec["username"] = bot.name
                    rec["bot_profile"] = {
                        "id": bot.id,
                        "name": bot.name,
                        "app_id": bot.app_id,
                        "deleted": False,
                    }
                else:
                    rec["user"] = members[rng.randrange(member_count)]
                text = SENTENCES[rng.randrange(len(SENTENCES))]
                if g in mentions:
                    text = f"<@{user_ids[rng.randrange(user_count)]}> {text}"
                if g in links:
                    label = LINK_LABELS[rng.randrange(len(LINK_LABELS))]
                    text = f"{text} <https://example.com/{label}/{rng.randrange(10**6):x}|{label}>"
                rec["text"] = text
                if g in reactions:
                    voters = [user_ids[rng.randrange(user_count)] for _ in range(rng.randint(1, 3))]
                    rec["reactions"] = [
                        {
                            "name": EMOJI[rng.randrange(len(EMOJI))],
                            "users": voters,
                            "count": len(voters),
                        }
                    ]
                if g in broadcasts:
                    rec["subtype"] = "thread_broadcast"
                if g in file_records:
                    name, mimetype, filetype = FILE_TYPES[rng.randrange(len(FILE_TYPES))]
                    file_serial += 1
                    rec["files"] = [
                        {
                            "id": f"F{file_serial:09X}",
                            "name": name,
                            "mimetype": mimetype,
                            "filetype": filetype,
                            "size": rng.randrange(1_000, 5_000_000),
                        }
                    ]
                    rec.setdefault("subtype", "file_share")
                item = [seconds[j], j, rec, None, g]
                items.append(item)
                by_g[g] = item

            for k, (sec, uid, kind) in enumerate(membership.get(di, ())):
                verb = "joined" if kind == "channel_join" else "left"
                rec = {
                    "type": "message",
                    "subtype": kind,
                    "user": uid,
                    "text": f"<@{uid}> has {verb} the channel",
                    "team": team,
                }
                items.append([sec, _SEQ_MEMBERSHIP + k, rec, None, -1])

            event_items: list[Item] = []
            for k, (kind, target) in enumerate(events_by_day.get(di, ())):
                low = seconds[target - start] if target is not None else 0
                sec = rng.randint(low, _DAY_SECONDS - 1)
                seq = _SEQ_EVENT + 2 * k
                if kind is AnomalyType.EDIT_AFTER_DELETE:
                    deleted = [sec, seq, {"type": "message", "team": team}, _EAF_DELETE, target]
                    edited_sec = rng.randint(sec, _DAY_SECONDS - 1)
                    edited = [
                        edited_sec,
                        seq + 1,
                        {"type": "message", "team": team},
                        AnomalyType.EDIT_AFTER_DELETE,
                        target,
                    ]
                    event_items.extend([deleted, edited])
                else:
                    event_items.append([sec, seq, {"type": "message", "team": team}, kind, target])
            items.extend(event_items)

            items.sort(key=lambda it: (it[0], it[1]))
            for it in items:
                it.append(f"{epoch + it[0]}.{serial % _MICRO_MOD:06d}")  # it[5] = ts
                it.append(serial % _MICRO_MOD)  # it[6] = micro
                it[2]["ts"] = it[5]
                serial += 1

            # Second pass: thread links and event bodies need final timestamps.
            for g in range(start, start + count):
                rec = by_g[g][2]
                if g in parent_of:
                    parent_rec = by_g[parent_of[g]][2]
                    rec["thread_ts"] = parent_rec["ts"]
                    rec["parent_user_id"] = parent_rec["user"]
                elif g in children:
                    kids = children[g]
                    rec["thread_ts"] = rec["ts"]
                    rec["reply_count"] = len(kids)
                    rec["reply_users_count"] = len({by_g[c][2]["user"] for c in kids})
                    rec["latest_reply"] = by_g[kids[-1]][2]["ts"]

            for it in event_items:
                kind, target = it[3], it[4]
                rec = it[2]
                if target is None:
                    phantom_k += 1
                    target_ts = _phantom_ts(epoch, phantom_k)
                    editor = members[0] if members else "U00000000"
                    old_text = SENTENCES[phantom_k % len(SENTENCES)]
                else:
                    original = by_g[target][2]
                    target_ts = original["ts"]
                    editor = original.get("user", original.get("bot_id", ""))
                    old_text = original["text"]
                previous = {"type": "message", "user": editor, "text": old_text, "ts": target_ts}
                rec["hidden"] = True
                rec["channel"] = conv.id
                if kind in (
                    AnomalyType.EDIT,
                    AnomalyType.EDIT_AFTER_DELETE,
                    AnomalyType.EDIT_TARGET_MISSING,
                ):
                    rec["subtype"] = "message_changed"
                    rec["message"] = {
                        "type": "message",
                        "user": editor,
                        "text": f"{old_text} (edited)",
                        "ts": target_ts,
                        "edited": {"user": editor, "ts": rec["ts"]},
                    }
                    rec["previous_message"] = previous
                else:
                    rec["subtype"] = "message_deleted"
                    rec["deleted_ts"] = target_ts
                    rec["previous_message"] = previous
                it.append(target_ts)  # it[7]

            # Record-level anomalies.
            anomalies: list[AnomalyRecord] = []
            for it in items:
                g = it[4]
                if it[3] is not None or g < 0:
                    continue
                mutation = plan.records.get(g)
                if mutation is None:
                    continue
                rec = it[2]
                if mutation is AnomalyType.ORPHAN_REPLY:
                    phantom_k += 1
                    rec["thread_ts"] = _phantom_ts(epoch, phantom_k)
                elif mutation is AnomalyType.UNKNOWN_SUBTYPE:
                    rec["subtype"] = UNKNOWN_SUBTYPE
                elif mutation is AnomalyType.MISSING_TS:
                    del rec["ts"]
                elif mutation is AnomalyType.INVALID_TS:
                    rec["ts"] = str(epoch + it[0])
                elif mutation is AnomalyType.SCHEMA_VIOLATION:
                    rec["text"] = 1000 + it[6]
                elif mutation is AnomalyType.UNRESOLVED_USER:
                    unlisted += 1
                    rec["user"] = f"UZ{unlisted:07d}"
                elif mutation is AnomalyType.UNRESOLVED_FILE:
                    rec["files"] = [{"id": rec["files"][0]["id"]}]
                elif mutation is AnomalyType.BOT_NO_IDENTITY:
                    for key in ("bot_id", "bot_profile", "username"):
                        rec.pop(key, None)
                elif mutation is AnomalyType.TS_OUT_OF_RANGE:
                    rec["ts"] = f"{epoch + it[0] + 2 * _DAY_SECONDS}.{it[6]:06d}"
            records = [it[2] for it in items]
            for index, it in enumerate(items):
                if it[3] is _EAF_DELETE:
                    continue  # the delete half of an edit-after-delete pair has no own entry
                if it[3] is not None:
                    anomalies.append((it[3].value, conv.id, it[7], path, index))
                elif it[4] >= 0 and it[4] in plan.records:
                    kind = plan.records[it[4]]
                    anomalies.append((kind.value, conv.id, it[2].get("ts"), path, index))

            parts = [dumps(r) for r in records]
            body = "[" + ",".join(parts) + "]"
            record_ts: list[str | None] | None = None
            if di in plan.malformed_days:
                cut_record = rng.randrange(1, len(parts)) if len(parts) > 1 else 0
                offset = 1 + sum(len(p) + 1 for p in parts[:cut_record])
                cut = offset + rng.randint(1, max(1, len(parts[cut_record]) - 1))
                body = body[:cut]
                anomalies.append((AnomalyType.MALFORMED_JSON.value, conv.id, None, path, None))
                if collect_ts:
                    record_ts = [r.get("ts") for r in records[:cut_record]]
            elif collect_ts:
                record_ts = [r.get("ts") for r in records]
            yield GeneratedFile(path, abs_day, body.encode("ascii"), count, anomalies, record_ts)

        while emitted_empty < len(empty_rel):
            yield self._empty_file(empty_rel[emitted_empty])
            emitted_empty += 1

    def _empty_file(self, rel_day: int) -> GeneratedFile:
        abs_day = self._seg.day_offset + rel_day
        path = self._path(abs_day)
        anomaly: AnomalyRecord = (AnomalyType.EMPTY_FILE.value, self._seg.conv.id, None, path, None)
        return GeneratedFile(path, abs_day, b"[]", 0, [anomaly], [])


def render_root_files(ws: Workspace) -> dict[str, bytes]:
    """``users.json`` and the four conversation listings."""
    team = ws.team_id
    users = [
        {
            "id": u.id,
            "team_id": team,
            "name": u.name,
            "real_name": u.real_name,
            "deleted": u.deleted,
            "is_bot": False,
            "profile": {"real_name": u.real_name, "display_name": u.name},
        }
        for u in ws.users
    ]
    listings: dict[str, list[Record]] = {
        "channels.json": [],
        "groups.json": [],
        "dms.json": [],
        "mpims.json": [],
    }
    for conv in ws.conversations:
        if conv.kind is ConvKind.PUBLIC:
            listings["channels.json"].append(
                {
                    "id": conv.id,
                    "name": conv.name,
                    "created": conv.created,
                    "creator": conv.members[0],
                    "is_archived": False,
                    "is_general": conv.rank == 1,
                    "members": list(conv.members),
                    "topic": {"value": "", "creator": "", "last_set": 0},
                    "purpose": {"value": "", "creator": "", "last_set": 0},
                }
            )
        elif conv.kind is ConvKind.PRIVATE:
            listings["groups.json"].append(
                {
                    "id": conv.id,
                    "name": conv.name,
                    "created": conv.created,
                    "creator": conv.members[0],
                    "is_archived": False,
                    "members": list(conv.members),
                    "topic": {"value": "", "creator": "", "last_set": 0},
                    "purpose": {"value": "", "creator": "", "last_set": 0},
                }
            )
        elif conv.kind is ConvKind.DM:
            listings["dms.json"].append(
                {"id": conv.id, "created": conv.created, "members": list(conv.members)}
            )
        else:
            listings["mpims.json"].append(
                {
                    "id": conv.id,
                    "name": conv.name,
                    "created": conv.created,
                    "creator": conv.members[0],
                    "members": list(conv.members),
                }
            )
    files = {"users.json": dumps(users).encode("ascii")}
    for name, value in listings.items():
        files[name] = dumps(value).encode("ascii")
    return files
