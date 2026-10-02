from __future__ import annotations

import pytest

from generator_support import Rendered, render_cached


@pytest.fixture(scope="session")
def small_clean() -> Rendered:
    return render_cached(42, "small", "clean")


@pytest.fixture(scope="session")
def small_default() -> Rendered:
    return render_cached(42, "small", "default")


@pytest.fixture(scope="session")
def small_stress() -> Rendered:
    return render_cached(42, "small", "stress")


@pytest.fixture(scope="session")
def medium_default() -> Rendered:
    return render_cached(42, "medium", "default")


@pytest.fixture(scope="session")
def medium_stress() -> Rendered:
    return render_cached(42, "medium", "stress")
