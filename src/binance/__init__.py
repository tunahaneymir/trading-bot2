"""
Trading Bot - Binance Module
=============================

Binance Futures API entegrasyonu ve market data yönetimi.

Modüller:
    - binance_manager: Ana Binance API yöneticisi
    - rate_limiter: Rate limiting ve throttling
    - websocket_manager: WebSocket streams (Faz 3.2)

Author: Trading Bot Team
Version: 1.0 (Faz 3)
Python: 3.10+
"""

from src.binance.binance_manager import BinanceManager, BinanceError
from src.binance.rate_limiter import RateLimiter

__all__ = [
    'BinanceManager',
    'BinanceError',
    'RateLimiter',
]

__version__ = '1.0.0'