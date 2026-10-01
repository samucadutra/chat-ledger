"""Contract fixture (CLI-GATES-03): a module with >= 20 statements that no test imports.

Copy it into ``packages/core/chatledger_core/parsing/`` to prove the coverage gate fails.
"""

THRESHOLD = 10
NAMES = ["alpha", "beta", "gamma"]


def classify(value: int) -> str:
    if value < 0:
        return "negative"
    if value == 0:
        return "zero"
    if value < THRESHOLD:
        return "small"
    return "large"


def total(values: list[int]) -> int:
    result = 0
    for value in values:
        result += value
    return result


def describe(values: list[int]) -> list[str]:
    labels = []
    for value in values:
        label = classify(value)
        labels.append(label)
    return labels


def pick_name(index: int) -> str:
    if index < 0:
        index = 0
    if index >= len(NAMES):
        index = len(NAMES) - 1
    return NAMES[index]


def summarise(values: list[int]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for label in describe(values):
        summary[label] = summary.get(label, 0) + 1
    summary["total"] = total(values)
    return summary
