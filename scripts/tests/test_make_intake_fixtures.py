from __future__ import annotations

import zipfile
from pathlib import Path

from fixtures import make_intake_fixtures as gen


def test_small_fixtures_are_deterministic() -> None:
    assert gen.small_fixtures() == gen.small_fixtures()


def test_committed_fixtures_match_generator() -> None:
    for name, data in gen.small_fixtures().items():
        assert (gen.SMALL_DIR / name).read_bytes() == data, f"{name} is stale: rerun --small"


def test_shapes() -> None:
    small = gen.small_fixtures()
    import io

    with zipfile.ZipFile(io.BytesIO(small["path-traversal.zip"])) as zf:
        assert "../evil.json" in zf.namelist()
    with zipfile.ZipFile(io.BytesIO(small["zip-bomb.zip"])) as zf:
        info = zf.getinfo("padding.bin")
        assert info.file_size == 52_428_800
        assert info.file_size / info.compress_size > 100
    assert len(small["not-a-zip.zip"]) == 1024
    assert not small["not-a-zip.zip"].startswith(b"PK")
    with zipfile.ZipFile(io.BytesIO(small["nested-export.zip"])) as zf:
        assert all(n.startswith("Acme Slack export Jan 2024/") for n in zf.namelist())


def test_large_writers_with_small_sizes(tmp_path: Path) -> None:
    big = tmp_path / "big.zip"
    gen.write_large_export(big, padding_bytes=300_000)
    first = big.read_bytes()
    gen.write_large_export(big, padding_bytes=300_000)
    assert big.read_bytes() == first
    with zipfile.ZipFile(big) as zf:
        pad = zf.getinfo("padding.bin")
        assert pad.compress_type == zipfile.ZIP_STORED
        assert pad.file_size == 300_000
        assert "users.json" in zf.namelist()

    over = tmp_path / "over.zip"
    gen.write_oversize(over, size=12_345)
    assert over.stat().st_size == 12_345

    many = tmp_path / "many.zip"
    gen.write_many_entries(many, total=50)
    with zipfile.ZipFile(many) as zf:
        assert len(zf.namelist()) == 50


def test_constants_match_contract() -> None:
    assert gen.OVERSIZE_BYTES == 2_147_483_649
    assert gen.MANY_ENTRIES == 200_001
    assert gen.LARGE_PADDING_BYTES >= 1_610_612_736


def test_main_requires_a_mode() -> None:
    import pytest

    with pytest.raises(SystemExit):
        gen.main([])
