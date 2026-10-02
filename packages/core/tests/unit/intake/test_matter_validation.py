from __future__ import annotations

import pytest

from chatledger_core.domain.intake.errors import (
    MatterDescriptionInvalidError,
    MatterNameInvalidError,
)
from chatledger_core.domain.intake.matter import validate_matter_input


def test_trims_name_and_description() -> None:
    assert validate_matter_input("  Acme v. Beta  ", "  text  ") == ("Acme v. Beta", "text")


def test_empty_description_becomes_none() -> None:
    assert validate_matter_input("Acme", "   ") == ("Acme", None)
    assert validate_matter_input("Acme", None) == ("Acme", None)


@pytest.mark.parametrize("name", ["", "  ", "Ab", " Ab ", "x" * 81])
def test_invalid_name(name: str) -> None:
    with pytest.raises(MatterNameInvalidError) as info:
        validate_matter_input(name, None)
    assert info.value.message == "Name must be 3\u201380 characters"
    assert info.value.code == "MATTER_NAME_INVALID"
    assert info.value.http_status == 422


@pytest.mark.parametrize("name", ["abc", "x" * 80, "  abc  "])
def test_valid_name_bounds(name: str) -> None:
    assert validate_matter_input(name, None)[0] == name.strip()


def test_description_limit() -> None:
    assert validate_matter_input("Acme", "d" * 500)[1] == "d" * 500
    with pytest.raises(MatterDescriptionInvalidError) as info:
        validate_matter_input("Acme", "d" * 501)
    assert info.value.message == "Description must be at most 500 characters"


def test_description_length_measured_after_trim() -> None:
    assert validate_matter_input("Acme", " " + "d" * 500 + " ")[1] == "d" * 500
