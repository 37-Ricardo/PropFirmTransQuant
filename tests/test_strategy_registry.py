from __future__ import annotations

from strategies.registry import create_strategy, list_strategies


def test_registry_lists_strategies() -> None:
    names = {item["name"] for item in list_strategies()}
    assert "macd_rsi_prime" in names
    assert "simple_ma_cross" in names


def test_registry_can_create_macd_rsi_prime() -> None:
    strategy = create_strategy("macd_rsi_prime")
    assert strategy.name == "macd_rsi_prime"


def test_registry_can_create_simple_ma_cross() -> None:
    strategy = create_strategy("simple_ma_cross")
    assert strategy.name == "simple_ma_cross"
