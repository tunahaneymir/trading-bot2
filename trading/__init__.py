"""
Trading Paketi
==============

Tam trading sistemi bile_enleri.

Modüller:
--------
- signal_generator : Multi-timeframe sinyal üretimi
- position_manager : Pozisyon yönetimi ve takibi
- order_executor   : Binance emir yürütme
- trading_engine   : Ana trading loop orkestratörü

Faz 5: Trading Components (TAMAMLANDI)
--------------------------------------

Kullan1m Örnei:
---------------
```python
from trading import (
    SignalGenerator,
    PositionManager,
    OrderExecutor,
    TradingEngine
)

# Bile_enleri olu_tur
signal_gen = SignalGenerator()
pos_mgr = PositionManager()
order_exec = OrderExecutor(binance_manager)

# Trading engine
engine = TradingEngine(
    signal_generator=signal_gen,
    position_manager=pos_mgr,
    order_executor=order_exec
)

# Ba_lat
await engine.start()
```

Yazar: Trading Bot Sistemi
Versiyon: 1.0.0
Faz: 5
"""

# Signal Generator
from .signal_generator import (
    SignalGenerator,
    SignalType,
    ConfidenceLevel,
    TradingSignal,
    IndicatorSignal
)

# Position Manager
from .position_manager import (
    PositionManager,
    Position,
    PositionState,
    PositionSide,
    CloseReason
)

# Order Executor
from .order_executor import (
    OrderExecutor,
    Order,
    OrderType,
    OrderSide,
    OrderStatus,
    TimeInForce
)

# Trading Engine
from .trading_engine import (
    TradingEngine,
    EngineState,
    TradingStats
)


# Public API
__all__ = [
    # Signal Generator
    'SignalGenerator',
    'SignalType',
    'ConfidenceLevel',
    'TradingSignal',
    'IndicatorSignal',

    # Position Manager
    'PositionManager',
    'Position',
    'PositionState',
    'PositionSide',
    'CloseReason',

    # Order Executor
    'OrderExecutor',
    'Order',
    'OrderType',
    'OrderSide',
    'OrderStatus',
    'TimeInForce',

    # Trading Engine
    'TradingEngine',
    'EngineState',
    'TradingStats',
]

# Paket metadata
__version__ = '1.0.0'
__author__ = 'Trading Bot Sistemi'
__phase__ = 5
__status__ = 'COMPLETED'
__description__ = 'Tam trading sistemi: Sinyal üretimi, pozisyon yönetimi, emir yürütme ve ana motor'


def get_version_info() -> dict:
    """
    Paket versiyon bilgilerini getir.

    Returns:
    --------
    dict
        Versiyon bilgileri
    """
    return {
        'version': __version__,
        'author': __author__,
        'phase': __phase__,
        'status': __status__,
        'description': __description__,
        'components': [
            'SignalGenerator',
            'PositionManager',
            'OrderExecutor',
            'TradingEngine'
        ]
    }


if __name__ == "__main__":
    print("=æ Trading Paketi")
    print("=" * 60)

    info = get_version_info()
    print(f"\n Versiyon: {info['version']}")
    print(f" Faz: {info['phase']}")
    print(f" Durum: {info['status']}")
    print(f" Aç1klama: {info['description']}")

    print(f"\n=Ê Bile_enler:")
    for component in info['components']:
        print(f"  " {component}")

    print("\n" + "=" * 60)
    print(" Paket haz1r!")
