"""The configurable price list behind the cost ledger.

Prices are not in this file and must never be. Providers change them, the
foundation approves a budget based on them (D11), and reflecting a new price
must not require a deploy. So the list lives in a JSON file whose path comes
from `PRICING_FILE`, and this module reads it, validates it, and re-reads it
whenever the file on disk changes.

Money is parsed as `Decimal` from strings, never from JSON floats: a binary
float reintroduces rounding error into the figure the foundation signs off on,
which is the same reason `queries.cost_usd` is `NUMERIC` (see
`docs/conventions.md`, "Money is `Numeric`, never `Float`").
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.config import settings

# Providers quote per million tokens, so the file does too: a per-token figure
# would be a string of leading zeros that nobody can proofread.
TOKENS_PER_PRICE_UNIT = Decimal(1_000_000)

# Both limits mirror the columns these values end up in (`queries.model`,
# `queries.pricing_version`), so a name too long to store is rejected while
# reading the file rather than at insert time, halfway through a request.
MAX_MODEL_NAME_LENGTH = 100
MAX_VERSION_LENGTH = 50

# The exchange rate is quoted as PLN per one USD, so a list priced in anything
# else would silently produce a wrong PLN figure. Rejected rather than guessed.
SUPPORTED_CURRENCY = "USD"


class PricingConfigError(Exception):
    """The price list is missing, unreadable, or malformed.

    An operator mistake, not a client one. Raised rather than falling back to
    a previously loaded list: silently pricing traffic with a list the operator
    believes they just replaced would corrupt the ledger quietly, for as long
    as nobody looks. Failing on the first request after the edit surfaces a
    typo in seconds instead.
    """


class UnknownModelPrice(Exception):
    """The price list has no entry for this model.

    Means a model reached production before its price did. Costing it at zero
    would understate the bill in exactly the report the foundation reads, so
    this is an error, not a default.
    """


@dataclass(frozen=True)
class ModelPrice:
    """What one model charges, in the price list's currency per million tokens."""

    input_per_million: Decimal
    output_per_million: Decimal


@dataclass(frozen=True)
class PriceList:
    """One loaded, validated price list.

    `version` is stored on every priced query (`queries.pricing_version`), so a
    figure reported months ago can still be traced to the numbers that produced
    it. `fx_rate_pln_per_usd` is stored per row for the same reason: the rate
    moves, and a historical cost recomputed at today's rate is a different
    number pretending to be the same one.
    """

    version: str
    currency: str
    fx_rate_pln_per_usd: Decimal
    models: Mapping[str, ModelPrice]

    def price_for(self, model: str) -> ModelPrice:
        try:
            return self.models[model]
        except KeyError:
            raise UnknownModelPrice(
                f"no price for model {model!r} in price list {self.version!r}"
            ) from None


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PricingConfigError(f"{field} must be an object")
    return value


def _require_text(value: Any, field: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PricingConfigError(f"{field} must be a non-empty string")
    text = value.strip()
    if len(text) > max_length:
        raise PricingConfigError(f"{field} is longer than {max_length} characters")
    return text


def _require_decimal(value: Any, field: str, *, positive: bool = False) -> Decimal:
    # `bool` is an `int` in Python, and a JSON float is where binary rounding
    # error would enter a figure that ends up in front of the foundation.
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise PricingConfigError(
            f"{field} must be a number written as a string (a JSON float loses precision)"
        )
    try:
        amount = Decimal(str(value))
    except InvalidOperation as error:
        raise PricingConfigError(f"{field} is not a valid number: {value!r}") from error
    if not amount.is_finite() or amount < 0:
        raise PricingConfigError(f"{field} must be a finite, non-negative number")
    if positive and amount == 0:
        raise PricingConfigError(f"{field} must be greater than zero")
    return amount


def _parse_models(raw: Any) -> dict[str, ModelPrice]:
    models_raw = _require_mapping(raw, "models")
    if not models_raw:
        # An empty list can never price anything. Failing here names the real
        # problem; failing later would only report "unknown model".
        raise PricingConfigError("models must hold at least one entry")

    models: dict[str, ModelPrice] = {}
    for name, entry in models_raw.items():
        model = _require_text(name, "a model name", MAX_MODEL_NAME_LENGTH)
        fields = _require_mapping(entry, f"models[{model!r}]")
        models[model] = ModelPrice(
            input_per_million=_require_decimal(
                fields.get("input_per_million"), f"models[{model!r}].input_per_million"
            ),
            output_per_million=_require_decimal(
                fields.get("output_per_million"), f"models[{model!r}].output_per_million"
            ),
        )
    return models


def parse_price_list(data: Any) -> PriceList:
    """Validate an already-decoded price list. Raises `PricingConfigError`."""
    root = _require_mapping(data, "the price list")

    currency = _require_text(root.get("currency"), "currency", 3).upper()
    if currency != SUPPORTED_CURRENCY:
        raise PricingConfigError(
            f"currency must be {SUPPORTED_CURRENCY}, because the exchange rate is "
            f"quoted as PLN per USD; got {currency!r}"
        )

    return PriceList(
        version=_require_text(root.get("version"), "version", MAX_VERSION_LENGTH),
        currency=currency,
        # Strictly positive, unlike a price: a price of zero is a real thing
        # (a free tier), whereas a rate of zero would report every question as
        # costing 0 PLN, which is the one wrong answer that looks like good
        # news. The ledger's own check constraint requires the same, so
        # accepting it here would only move the failure to the first write.
        fx_rate_pln_per_usd=_require_decimal(
            root.get("fx_rate_pln_per_usd"), "fx_rate_pln_per_usd", positive=True
        ),
        models=_parse_models(root.get("models")),
    )


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise PricingConfigError(
            f"price list is missing or not readable at {path}; copy "
            "backend/pricing.example.json and set the real prices and exchange rate"
        ) from error


def _decode(raw: bytes, path: Path) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise PricingConfigError(f"price list at {path} is not valid JSON: {error}") from error


# Keyed by path plus the exact bytes last parsed, so an edit is picked up
# without a restart. That is the whole point of the card: a price change is a
# file edit, not a deploy.
#
# The bytes themselves rather than a digest of them: they are already in hand,
# so a comparison is a memcmp that stops at the first differing byte, where
# hashing always walks the whole buffer and then claims equality only
# probabilistically. A price list is a few kilobytes, less than the parsed
# `PriceList` beside it.
_cache: tuple[str, bytes, PriceList] | None = None


def get_price_list(path: str | Path | None = None) -> PriceList:
    """The current price list, re-parsed only when the file's contents changed.

    The file is read on every call and the cache is keyed by what was read,
    rather than by `stat()`. Timestamp resolution is not something this can rely
    on: a container bind mount or a network filesystem may report mtime to the
    whole second, and an edit inside one second that happens to keep the byte
    count identical would then be invisible. Serving superseded prices is the
    failure this module exists to prevent, so it does not trade correctness for
    a `stat()`.

    A caller that prices several model calls for one question should load the
    list once and pass it to `price_usage`, which is what its `price_list`
    parameter is for: that turns N reads per request into one.

    Two threads can parse the same file at once (endpoints are sync, so they run
    in a threadpool). The only cost is duplicated parsing of identical bytes, so
    this is deliberately left unlocked.
    """
    global _cache

    target = Path(path if path is not None else settings.pricing_file)
    raw = _read_bytes(target)

    cached = _cache
    if cached is not None and cached[0] == str(target) and cached[1] == raw:
        return cached[2]

    # A raise here leaves the old entry in place but unreachable, since its
    # bytes no longer match the file: a broken edit fails loudly instead of
    # quietly serving prices the operator thinks they replaced.
    price_list = parse_price_list(_decode(raw, target))
    _cache = (str(target), raw, price_list)
    return price_list


def reset_price_list_cache() -> None:
    """Drop the cached list. For tests, and for a forced re-read."""
    global _cache
    _cache = None
