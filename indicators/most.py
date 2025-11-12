"""
MOST (Moving Stop Loss) Indicator
==================================

A trend-following indicator that uses a moving average with ATR-based stop loss bands
to identify trend direction and potential reversal points.

Features:
- Multiple MA types: VAR (default), EMA, HULL, T3, SMA, WMA
- Adaptive stop loss based on percentage of MA
- Trend direction tracking (1 for uptrend, -1 for downtrend)
- Windows-compatible implementation

Author: Trading Bot System
Version: 1.0.0
"""

import numpy as np
from typing import Tuple, Optional
import warnings


class InsufficientDataError(Exception):
    """Raised when there's not enough data for calculation."""
    pass


def _calculate_var(close: np.ndarray, length: int) -> np.ndarray:
    """
    Calculate Variable Index Dynamic Average (VAR).
    
    VAR adapts smoothing based on Chande Momentum Oscillator (CMO).
    More responsive during strong trends, smoother during consolidation.
    
    Parameters:
    -----------
    close : np.ndarray
        Closing prices
    length : int
        Period for calculation
        
    Returns:
    --------
    np.ndarray
        VAR values
    """
    if len(close) < length + 9:
        raise InsufficientDataError(
            f"VAR requires at least {length + 9} data points, got {len(close)}"
        )
    
    alpha = 2.0 / (length + 1)
    
    # Calculate up/down movements
    diff = np.diff(close, prepend=close[0])
    up = np.where(diff > 0, diff, 0.0)
    down = np.where(diff < 0, -diff, 0.0)
    
    # Calculate CMO (Chande Momentum Oscillator)
    cmo = np.zeros_like(close)
    for i in range(9, len(close)):
        sum_up = np.sum(up[i-8:i+1])
        sum_down = np.sum(down[i-8:i+1])
        
        if sum_up + sum_down != 0:
            cmo[i] = (sum_up - sum_down) / (sum_up + sum_down)
    
    # Calculate VAR
    var = np.zeros_like(close)
    var[0] = close[0]
    
    for i in range(1, len(close)):
        var[i] = alpha * abs(cmo[i]) * close[i] + (1 - alpha * abs(cmo[i])) * var[i-1]
    
    return var


def _calculate_ema(close: np.ndarray, length: int) -> np.ndarray:
    """
    Calculate Exponential Moving Average (EMA).
    
    Parameters:
    -----------
    close : np.ndarray
        Closing prices
    length : int
        Period for EMA
        
    Returns:
    --------
    np.ndarray
        EMA values
    """
    if len(close) < length:
        raise InsufficientDataError(
            f"EMA requires at least {length} data points, got {len(close)}"
        )
    
    alpha = 2.0 / (length + 1)
    ema = np.zeros_like(close)
    ema[0] = close[0]
    
    for i in range(1, len(close)):
        ema[i] = alpha * close[i] + (1 - alpha) * ema[i-1]
    
    return ema


def _calculate_hull(close: np.ndarray, length: int) -> np.ndarray:
    """
    Calculate Hull Moving Average (HMA).
    
    HMA = WMA(2 * WMA(n/2) - WMA(n)), sqrt(n)
    Provides a smoother, more responsive moving average.
    
    Parameters:
    -----------
    close : np.ndarray
        Closing prices
    length : int
        Period for HMA
        
    Returns:
    --------
    np.ndarray
        HMA values
    """
    if len(close) < length:
        raise InsufficientDataError(
            f"HULL requires at least {length} data points, got {len(close)}"
        )
    
    def wma(data: np.ndarray, period: int) -> np.ndarray:
        """Weighted Moving Average helper."""
        weights = np.arange(1, period + 1)
        result = np.zeros_like(data)
        
        for i in range(period - 1, len(data)):
            result[i] = np.sum(data[i-period+1:i+1] * weights) / np.sum(weights)
        
        # Fill initial values with first calculated value
        result[:period-1] = result[period-1]
        return result
    
    half_length = length // 2
    sqrt_length = int(np.sqrt(length))
    
    wma_half = wma(close, half_length)
    wma_full = wma(close, length)
    raw_hull = 2 * wma_half - wma_full
    hull = wma(raw_hull, sqrt_length)
    
    return hull


def _calculate_t3(close: np.ndarray, length: int, v_factor: float = 0.7) -> np.ndarray:
    """
    Calculate Tillson T3 Moving Average.
    
    T3 applies exponential smoothing six times with a volume factor
    to create a very smooth, responsive moving average.
    
    Parameters:
    -----------
    close : np.ndarray
        Closing prices
    length : int
        Period for T3
    v_factor : float
        Volume factor (default 0.7, range 0-1)
        
    Returns:
    --------
    np.ndarray
        T3 values
    """
    if len(close) < length * 6:
        raise InsufficientDataError(
            f"T3 requires at least {length * 6} data points, got {len(close)}"
        )
    
    # Six-pass EMA
    e1 = _calculate_ema(close, length)
    e2 = _calculate_ema(e1, length)
    e3 = _calculate_ema(e2, length)
    e4 = _calculate_ema(e3, length)
    e5 = _calculate_ema(e4, length)
    e6 = _calculate_ema(e5, length)
    
    # T3 coefficients
    c1 = -v_factor ** 3
    c2 = 3 * v_factor ** 2 + 3 * v_factor ** 3
    c3 = -6 * v_factor ** 2 - 3 * v_factor - 3 * v_factor ** 3
    c4 = 1 + 3 * v_factor + v_factor ** 3 + 3 * v_factor ** 2
    
    t3 = c1 * e6 + c2 * e5 + c3 * e4 + c4 * e3
    
    return t3


def _calculate_sma(close: np.ndarray, length: int) -> np.ndarray:
    """
    Calculate Simple Moving Average (SMA).
    
    Parameters:
    -----------
    close : np.ndarray
        Closing prices
    length : int
        Period for SMA
        
    Returns:
    --------
    np.ndarray
        SMA values
    """
    if len(close) < length:
        raise InsufficientDataError(
            f"SMA requires at least {length} data points, got {len(close)}"
        )
    
    sma = np.zeros_like(close)
    for i in range(length - 1, len(close)):
        sma[i] = np.mean(close[i-length+1:i+1])
    
    # Fill initial values
    sma[:length-1] = sma[length-1]
    return sma


def _calculate_wma(close: np.ndarray, length: int) -> np.ndarray:
    """
    Calculate Weighted Moving Average (WMA).
    
    Parameters:
    -----------
    close : np.ndarray
        Closing prices
    length : int
        Period for WMA
        
    Returns:
    --------
    np.ndarray
        WMA values
    """
    if len(close) < length:
        raise InsufficientDataError(
            f"WMA requires at least {length} data points, got {len(close)}"
        )
    
    weights = np.arange(1, length + 1)
    wma = np.zeros_like(close)
    
    for i in range(length - 1, len(close)):
        wma[i] = np.sum(close[i-length+1:i+1] * weights) / np.sum(weights)
    
    # Fill initial values
    wma[:length-1] = wma[length-1]
    return wma


def calculate_most(
    close: np.ndarray,
    length: int = 3,
    percent: float = 2.0,
    ma_type: str = "VAR"
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate MOST (Moving Stop Loss) indicator.
    
    MOST uses a moving average with percentage-based stop loss bands to track
    trend direction. When price crosses above/below the stop loss, trend reverses.
    
    Parameters:
    -----------
    close : np.ndarray
        Array of closing prices
    length : int, default=3
        Period for moving average calculation
    percent : float, default=2.0
        Stop loss percentage (e.g., 2.0 = 2% stop loss)
    ma_type : str, default="VAR"
        Type of moving average to use:
        - "VAR": Variable Index Dynamic Average (default, adaptive)
        - "EMA": Exponential Moving Average
        - "HULL": Hull Moving Average (smooth & responsive)
        - "T3": Tillson T3 (very smooth)
        - "SMA": Simple Moving Average
        - "WMA": Weighted Moving Average
        
    Returns:
    --------
    Tuple[np.ndarray, np.ndarray]
        - most_line: MOST indicator line (stop loss level)
        - trend_direction: Trend direction (1 = uptrend, -1 = downtrend)
        
    Raises:
    -------
    InsufficientDataError
        If not enough data points for calculation
    ValueError
        If invalid ma_type specified
        
    Example:
    --------
    >>> import numpy as np
    >>> close = np.array([100, 102, 101, 103, 105, 104, 106, 108])
    >>> most_line, trend = calculate_most(close, length=3, percent=2.0)
    >>> print(f"Current trend: {'Uptrend' if trend[-1] == 1 else 'Downtrend'}")
    """
    # Input validation
    if not isinstance(close, np.ndarray):
        close = np.array(close, dtype=np.float64)
    
    if len(close) < length:
        raise InsufficientDataError(
            f"MOST requires at least {length} data points, got {len(close)}"
        )
    
    if percent <= 0:
        raise ValueError(f"percent must be positive, got {percent}")
    
    # Calculate moving average based on type
    ma_type = ma_type.upper()
    
    if ma_type == "VAR":
        ma = _calculate_var(close, length)
    elif ma_type == "EMA":
        ma = _calculate_ema(close, length)
    elif ma_type == "HULL":
        ma = _calculate_hull(close, length)
    elif ma_type == "T3":
        ma = _calculate_t3(close, length)
    elif ma_type == "SMA":
        ma = _calculate_sma(close, length)
    elif ma_type == "WMA":
        ma = _calculate_wma(close, length)
    else:
        raise ValueError(
            f"Invalid ma_type '{ma_type}'. "
            f"Supported types: VAR, EMA, HULL, T3, SMA, WMA"
        )
    
    # Calculate stop loss offset
    offset = ma * percent * 0.01
    
    # Initialize stop loss arrays
    long_stop = ma - offset
    short_stop = ma + offset
    
    # Initialize direction and MOST arrays
    direction = np.ones(len(close), dtype=np.int32)
    most = np.zeros_like(close)
    
    # Calculate adaptive stop loss (stop can only move in trend direction)
    for i in range(1, len(close)):
        # Long stop: can only increase during uptrend
        if ma[i] > long_stop[i-1]:
            long_stop[i] = max(long_stop[i], long_stop[i-1])
        
        # Short stop: can only decrease during downtrend
        if ma[i] < short_stop[i-1]:
            short_stop[i] = min(short_stop[i], short_stop[i-1])
        
        # Determine trend direction
        if direction[i-1] == 1 and ma[i] < long_stop[i-1]:
            # Uptrend broken: switch to downtrend
            direction[i] = -1
        elif direction[i-1] == -1 and ma[i] > short_stop[i-1]:
            # Downtrend broken: switch to uptrend
            direction[i] = 1
        else:
            # Continue current trend
            direction[i] = direction[i-1]
        
        # MOST line follows current trend's stop loss
        most[i] = long_stop[i] if direction[i] == 1 else short_stop[i]
    
    # Set initial MOST value
    most[0] = long_stop[0]
    
    return most, direction


def get_most_signal(
    close: np.ndarray,
    most_line: np.ndarray,
    trend_direction: np.ndarray,
    lookback: int = 1
) -> str:
    """
    Get trading signal from MOST indicator.
    
    Parameters:
    -----------
    close : np.ndarray
        Closing prices
    most_line : np.ndarray
        MOST indicator line
    trend_direction : np.ndarray
        Trend direction array
    lookback : int, default=1
        Number of bars to look back for trend change
        
    Returns:
    --------
    str
        "BUY", "SELL", or "NEUTRAL"
    """
    if len(close) < lookback + 1:
        return "NEUTRAL"
    
    # Check for trend change
    current_trend = trend_direction[-1]
    previous_trend = trend_direction[-lookback - 1]
    
    if current_trend == 1 and previous_trend == -1:
        return "BUY"
    elif current_trend == -1 and previous_trend == 1:
        return "SELL"
    else:
        return "NEUTRAL"


# Convenience function for common use case
def most_with_signal(
    close: np.ndarray,
    length: int = 3,
    percent: float = 2.0,
    ma_type: str = "VAR"
) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Calculate MOST and get current signal in one call.
    
    Returns:
    --------
    Tuple[np.ndarray, np.ndarray, str]
        - most_line: MOST indicator line
        - trend_direction: Trend direction (1 or -1)
        - signal: Current trading signal ("BUY", "SELL", "NEUTRAL")
    """
    most_line, trend = calculate_most(close, length, percent, ma_type)
    signal = get_most_signal(close, most_line, trend)
    return most_line, trend, signal


if __name__ == "__main__":
    # Quick test
    print("MOST Indicator - Quick Test")
    print("=" * 50)
    
    # Generate sample data
    np.random.seed(42)
    prices = np.cumsum(np.random.randn(100)) + 100
    
    try:
        most_line, trend, signal = most_with_signal(prices, length=9, percent=2.0)
        
        print(f"✅ Calculation successful!")
        print(f"Last 5 prices: {prices[-5:]}")
        print(f"Last 5 MOST values: {most_line[-5:]}")
        print(f"Last 5 trend: {trend[-5:]}")
        print(f"Current signal: {signal}")
        
    except Exception as e:
        print(f"❌ Error: {e}")