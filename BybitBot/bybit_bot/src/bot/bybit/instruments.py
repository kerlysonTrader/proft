"""Regras de precisão por par spot (tickSize, basePrecision, mínimos).

Tudo em Decimal para não errar arredondamento. A quantidade é sempre
arredondada PARA BAIXO; se não couber nos mínimos, a ordem não é feita.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any, Literal, Protocol

from bot.logging_setup import get_logger

Rounding = Literal["down", "up", "nearest"]
_ROUNDING = {"down": ROUND_FLOOR, "up": ROUND_CEILING, "nearest": ROUND_HALF_UP}

log = get_logger("bybit.instruments")


class OrderValidationError(ValueError):
    """A ordem não respeita as regras do instrumento."""


class UnknownSymbolError(KeyError):
    pass


def to_decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def quantize_step(value: Decimal, step: Decimal, rounding: Rounding) -> Decimal:
    """Arredonda `value` para um múltiplo de `step`."""
    if step <= 0:
        raise ValueError("passo de arredondamento deve ser positivo")
    units = (value / step).to_integral_value(rounding=_ROUNDING[rounding])
    return (units * step).quantize(step)


def fmt(value: Decimal) -> str:
    """Decimal em texto sem notação científica nem zeros à direita (formato aceito pela Bybit)."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


@dataclass(frozen=True)
class InstrumentRules:
    symbol: str
    base_coin: str
    quote_coin: str
    status: str
    tick_size: Decimal
    base_precision: Decimal
    quote_precision: Decimal
    min_order_qty: Decimal
    max_order_qty: Decimal
    min_order_amt: Decimal
    max_order_amt: Decimal

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> InstrumentRules:
        lot = item.get("lotSizeFilter") or {}
        price = item.get("priceFilter") or {}
        return cls(
            symbol=item["symbol"],
            base_coin=item.get("baseCoin", ""),
            quote_coin=item.get("quoteCoin", ""),
            status=item.get("status", ""),
            tick_size=to_decimal(price["tickSize"]),
            base_precision=to_decimal(lot["basePrecision"]),
            quote_precision=to_decimal(lot.get("quotePrecision", "0.00000001")),
            min_order_qty=to_decimal(lot.get("minOrderQty", "0")),
            max_order_qty=to_decimal(lot.get("maxOrderQty") or lot.get("maxLimitOrderQty") or "Infinity"),
            min_order_amt=to_decimal(lot.get("minOrderAmt", "0")),
            max_order_amt=to_decimal(lot.get("maxOrderAmt") or "Infinity"),
        )

    @property
    def trading(self) -> bool:
        return self.status == "Trading"

    def round_price(self, price: Any, rounding: Rounding = "nearest") -> Decimal:
        return quantize_step(to_decimal(price), self.tick_size, rounding)

    def round_qty(self, qty: Any) -> Decimal:
        """Quantidade sempre para baixo, no múltiplo de basePrecision."""
        return quantize_step(to_decimal(qty), self.base_precision, "down")

    def min_qty_for_price(self, price: Any) -> Decimal:
        """Menor quantidade que respeita minOrderQty e minOrderAmt a este preço."""
        price = to_decimal(price)
        by_amount = quantize_step(self.min_order_amt / price, self.base_precision, "up") if price > 0 else 0
        return max(self.min_order_qty, to_decimal(by_amount))

    def validate_order(self, qty: Any, price: Any) -> tuple[Decimal, Decimal]:
        """Arredonda (qty para baixo, preço no tick) e confere os limites. Devolve (qty, price)."""
        if not self.trading:
            raise OrderValidationError(f"{self.symbol} não está em negociação (status={self.status})")
        price_d = self.round_price(price)
        qty_d = self.round_qty(qty)
        if price_d <= 0:
            raise OrderValidationError(f"{self.symbol}: preço inválido {price}")
        if qty_d <= 0 or qty_d < self.min_order_qty:
            raise OrderValidationError(
                f"{self.symbol}: quantidade {fmt(qty_d)} abaixo do mínimo {fmt(self.min_order_qty)}")
        if qty_d > self.max_order_qty:
            raise OrderValidationError(
                f"{self.symbol}: quantidade {fmt(qty_d)} acima do máximo {fmt(self.max_order_qty)}")
        amount = qty_d * price_d
        if amount < self.min_order_amt:
            raise OrderValidationError(
                f"{self.symbol}: valor {fmt(amount)} abaixo do mínimo {fmt(self.min_order_amt)} {self.quote_coin}")
        if amount > self.max_order_amt:
            raise OrderValidationError(
                f"{self.symbol}: valor {fmt(amount)} acima do máximo {fmt(self.max_order_amt)} {self.quote_coin}")
        return qty_d, price_d


class InstrumentsSource(Protocol):
    def get_instruments_info(self, symbol: str | None = None, category: str = "spot") -> list[dict]: ...


class InstrumentRegistry:
    """Regras de todos os pares spot, carregadas de /v5/market/instruments-info."""

    def __init__(self, rules: dict[str, InstrumentRules] | None = None) -> None:
        self._rules = rules or {}

    @classmethod
    def load(cls, client: InstrumentsSource, quote: str | None = "USDT") -> InstrumentRegistry:
        rules: dict[str, InstrumentRules] = {}
        skipped = 0
        for item in client.get_instruments_info(category="spot"):
            if quote and item.get("quoteCoin") != quote:
                continue
            try:
                rule = InstrumentRules.from_api(item)
            except (KeyError, ArithmeticError, ValueError):
                skipped += 1
                continue
            rules[rule.symbol] = rule
        log.info("regras de instrumentos carregadas", extra={"data": {"pares": len(rules), "ignorados": skipped}})
        return cls(rules)

    def __contains__(self, symbol: str) -> bool:
        return symbol in self._rules

    def __len__(self) -> int:
        return len(self._rules)

    def get(self, symbol: str) -> InstrumentRules:
        try:
            return self._rules[symbol]
        except KeyError as exc:
            raise UnknownSymbolError(f"par desconhecido: {symbol}") from exc

    def symbols(self) -> list[str]:
        return sorted(self._rules)

    def round_price(self, symbol: str, price: Any, rounding: Rounding = "nearest") -> Decimal:
        return self.get(symbol).round_price(price, rounding)

    def round_qty(self, symbol: str, qty: Any) -> Decimal:
        return self.get(symbol).round_qty(qty)

    def validate_order(self, symbol: str, qty: Any, price: Any) -> tuple[Decimal, Decimal]:
        return self.get(symbol).validate_order(qty, price)
