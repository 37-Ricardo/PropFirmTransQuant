from __future__ import annotations

from strategies.base import BaseStrategy


_STRATEGIES: dict[str, type[BaseStrategy]] = {}


def register_strategy(strategy_cls: type[BaseStrategy]) -> type[BaseStrategy]:
    """注册策略类，供命令行和回测流程按名称加载。"""

    if not issubclass(strategy_cls, BaseStrategy):
        raise TypeError("strategy_cls must inherit BaseStrategy")
    if not strategy_cls.name:
        raise ValueError("strategy_cls.name must be defined")

    _STRATEGIES[strategy_cls.name] = strategy_cls
    return strategy_cls


def get_strategy(name: str) -> type[BaseStrategy]:
    """按策略名称获取策略类。"""

    try:
        return _STRATEGIES[name]
    except KeyError as exc:
        available = ", ".join(sorted(_STRATEGIES)) or "<none>"
        raise KeyError(f"Unknown strategy '{name}'. Available strategies: {available}") from exc


def create_strategy(name: str) -> BaseStrategy:
    """按策略名称创建策略实例。"""

    return get_strategy(name)()


def list_strategies() -> list[dict[str, str]]:
    """返回当前可用策略的名称和描述。"""

    return [
        {"name": name, "description": strategy_cls.description}
        for name, strategy_cls in sorted(_STRATEGIES.items())
    ]


def _register_builtin_strategies() -> None:
    """注册项目内置策略。

    新增策略文件后，应在这里导入并调用 register_strategy。
    """

    from strategies.examples.simple_ma_cross import SimpleMaCrossStrategy
    from strategies.macd_rsi_prime import MacdRsiPrimeStrategy

    register_strategy(MacdRsiPrimeStrategy)
    register_strategy(SimpleMaCrossStrategy)


_register_builtin_strategies()
