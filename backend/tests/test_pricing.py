"""The configurable price list: what it accepts, what it refuses, when it reloads.

The card's rule is that prices are not in the code, which puts the burden on
this file instead: a malformed price list has to fail in a way an operator can
act on, because the alternative is a wrong number in front of the foundation.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services import pricing
from app.services.pricing import (
    PricingConfigError,
    UnknownModelPrice,
    get_price_list,
    parse_price_list,
    reset_price_list_cache,
)

VALID = {
    "version": "2026-08-31",
    "currency": "USD",
    "fx_rate_pln_per_usd": "4.050000",
    "models": {
        "small": {"input_per_million": "0.150000", "output_per_million": "0.600000"},
        "large": {"input_per_million": "3", "output_per_million": "15"},
    },
}


@pytest.fixture(autouse=True)
def clean_cache() -> None:
    """The cache is module level, so one test must not answer for the next."""
    reset_price_list_cache()


def write_price_list(directory: Path, data: object, name: str = "pricing.json") -> Path:
    path = directory / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_parses_amounts_as_exact_decimals() -> None:
    price_list = parse_price_list(VALID)

    assert price_list.version == "2026-08-31"
    assert price_list.fx_rate_pln_per_usd == Decimal("4.05")
    assert price_list.price_for("small").input_per_million == Decimal("0.15")
    # An integer is a legitimate way to write a whole-dollar price.
    assert price_list.price_for("large").output_per_million == Decimal("15")


def test_unknown_model_is_an_error_not_a_free_call() -> None:
    """Costing an unpriced model at zero would understate the actual bill."""
    with pytest.raises(UnknownModelPrice):
        parse_price_list(VALID).price_for("a-model-nobody-priced")


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param({"version": ""}, id="blank version"),
        pytest.param({"version": "v" * 51}, id="version longer than the column"),
        pytest.param({"currency": "PLN"}, id="currency the rate does not describe"),
        pytest.param({"fx_rate_pln_per_usd": 4.05}, id="rate as a JSON float"),
        pytest.param({"fx_rate_pln_per_usd": "-4.05"}, id="negative rate"),
        pytest.param({"fx_rate_pln_per_usd": "0"}, id="zero rate"),
        pytest.param({"fx_rate_pln_per_usd": "0.000000"}, id="zero rate, written out"),
        pytest.param({"fx_rate_pln_per_usd": "NaN"}, id="rate that is not a number"),
        pytest.param({"fx_rate_pln_per_usd": "four"}, id="rate that is not numeric at all"),
        pytest.param({"fx_rate_pln_per_usd": True}, id="rate as a boolean"),
        pytest.param({"models": {}}, id="no models at all"),
        pytest.param({"models": []}, id="models as a list"),
        pytest.param({"models": {"small": "0.15"}}, id="model entry that is not an object"),
        pytest.param({"models": {"s": {"input_per_million": "1"}}}, id="missing output price"),
        pytest.param({"models": {"m" * 101: {}}}, id="model name longer than the column"),
    ],
)
def test_refuses_a_malformed_price_list(mutation: dict[str, object]) -> None:
    with pytest.raises(PricingConfigError):
        parse_price_list({**VALID, **mutation})


def test_a_price_of_zero_is_allowed_but_a_rate_of_zero_is_not() -> None:
    """A free tier is a real price. A rate of zero is not a rate: it would
    report every question as costing 0 PLN, which is the one wrong answer that
    reads as good news, and the ledger's own constraint rejects it anyway."""
    free = {**VALID, "models": {"free": {"input_per_million": "0", "output_per_million": "0"}}}

    assert parse_price_list(free).price_for("free").input_per_million == Decimal("0")

    with pytest.raises(PricingConfigError, match="greater than zero"):
        parse_price_list({**VALID, "fx_rate_pln_per_usd": "0"})


def test_refuses_a_price_list_that_is_not_an_object() -> None:
    with pytest.raises(PricingConfigError):
        parse_price_list([VALID])


def test_a_float_price_is_refused_because_it_would_round() -> None:
    """0.1 has no exact binary form, and this figure is reported to a funder."""
    data = {**VALID, "models": {"small": {"input_per_million": 0.1, "output_per_million": "1"}}}
    with pytest.raises(PricingConfigError, match="loses precision"):
        parse_price_list(data)


def test_missing_file_names_the_fix(tmp_path: Path) -> None:
    with pytest.raises(PricingConfigError, match="pricing.example.json"):
        get_price_list(tmp_path / "absent.json")


def test_unreadable_path_is_a_config_error(tmp_path: Path) -> None:
    """A directory, a permission problem, a path that is not a file: all the
    same answer, because none of them can be priced from."""
    with pytest.raises(PricingConfigError, match="not readable"):
        get_price_list(tmp_path)


def test_invalid_json_is_a_config_error(tmp_path: Path) -> None:
    path = tmp_path / "pricing.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(PricingConfigError, match="not valid JSON"):
        get_price_list(path)


def test_reads_the_configured_path_when_none_is_given(tmp_path: Path, monkeypatch) -> None:
    path = write_price_list(tmp_path, VALID)
    monkeypatch.setattr(pricing.settings, "pricing_file", str(path))

    assert get_price_list().version == "2026-08-31"


def test_an_edited_file_takes_effect_without_a_restart(tmp_path: Path) -> None:
    """The whole point of the card: a price change is a file edit, not a deploy."""
    path = write_price_list(tmp_path, VALID)
    assert get_price_list(path).price_for("small").input_per_million == Decimal("0.15")

    raised = {**VALID, "version": "2026-09-01"}
    raised["models"] = {**VALID["models"], "small": {  # type: ignore[dict-item]
        "input_per_million": "0.250000",
        "output_per_million": "0.600000",
    }}
    write_price_list(tmp_path, raised)

    reloaded = get_price_list(path)
    assert reloaded.version == "2026-09-01"
    assert reloaded.price_for("small").input_per_million == Decimal("0.25")


def test_unchanged_contents_are_not_re_parsed(tmp_path: Path) -> None:
    """The file is read every call; parsing and validating it again is what the
    cache saves."""
    path = write_price_list(tmp_path, VALID)
    first = get_price_list(path)

    assert get_price_list(path) is first


def test_an_edit_is_seen_even_when_the_timestamp_and_size_do_not_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bind mount or a network filesystem may report mtime to the whole
    second, so an edit inside one second that keeps the byte count identical
    would be invisible to a stat-based cache. Simulated by pinning both."""
    path = write_price_list(tmp_path, VALID)
    assert get_price_list(path).fx_rate_pln_per_usd == Decimal("4.05")

    frozen = path.stat()
    monkeypatch.setattr(Path, "stat", lambda self, **_kwargs: frozen)

    # Same length, different number: "4.050000" -> "4.150000".
    write_price_list(tmp_path, {**VALID, "fx_rate_pln_per_usd": "4.150000"})

    assert get_price_list(path).fx_rate_pln_per_usd == Decimal("4.15")


def test_a_broken_edit_fails_loudly_instead_of_serving_the_old_list(tmp_path: Path) -> None:
    """Silently pricing traffic with a list the operator replaced is the worse bug.

    It corrupts the ledger for as long as nobody looks, whereas failing on the
    next request puts a typo in front of whoever just made it.
    """
    path = write_price_list(tmp_path, VALID)
    get_price_list(path)

    path.write_text("{ broken", encoding="utf-8")

    with pytest.raises(PricingConfigError):
        get_price_list(path)


def test_the_shipped_example_is_a_valid_price_list() -> None:
    """The example is the documentation for the shape, so it has to still parse."""
    example = Path(__file__).resolve().parent.parent / "pricing.example.json"
    price_list = get_price_list(example)

    assert price_list.models
    # Named so nobody mistakes the illustrative numbers for real prices.
    assert "example" in price_list.version
