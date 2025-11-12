"""
SuperTrend Indicator
====================

ATR-based trend following indicator that identifies trend direction and generates
buy/sell signals based on volatility-adjusted stop loss levels.

Features:
- ATR (Average True Range) based calculation
- Volatility-adaptive stop loss
- Trend direction tracking (1 for uptrend, -1 for downtrend)
- Buy/sell signal generation
- Windows-compatible implementation

Author: Trading Bot System
Version: 1.0.0
"""

import numpy as np
from typing import Tuple, Optional, Union


class InsufficientDataError(Exception):
    """Raised when there's not enough data for calculation."""
    pass


def calculate_true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """
    Calculate True Range for each bar.
    
    True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
    
    Parameters:
    -----------
    high : np.ndarray
        High prices
    low : np.ndarray
        Low prices
    close : np.ndarray
        Closing prices
        
    Returns:
    --------
    np.ndarray
        True Range values
    """
    # Calculate components
    hl = high - low
    hc = np.abs(high - np.roll(close, 1))
    lc = np.abs(low - np.roll(close, 1))
    
    # First bar uses only high - low
    hc[0] = 0
    lc[0] = 0
    
    # True Range is the maximum of the three
    tr = np.maximum(hl, np.maximum(hc, lc))
    
    return tr


def calculate_atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 10,
    method: str = "rma"
) -> np.ndarray:
    """
    Calculate Average True Range (ATR).
    
    Parameters:
    -----------
    high : np.ndarray
        High prices
    low : np.ndarray
        Low prices
    close : np.ndarray
        Closing prices
    period : int, default=10
        ATR period
    method : str, default="rma"
        Calculation method:
        - "rma": RMA (Wilder's smoothing) - default, matches Pine Script atr()
        - "sma": Simple Moving Average - matches Pine Script sma(tr)
        
    Returns:
    --------
    np.ndarray
        ATR values
    """
    if len(high) < period:
        raise InsufficientDataError(
            f"ATR requires at least {period} data points, got {len(high)}"
        )
    
    # Calculate True Range
    tr = calculate_true_range(high, low, close)
    
    if method.lower() == "sma":
        # Simple Moving Average of TR
        atr = np.zeros_like(tr)
        for i in range(period - 1, len(tr)):
            atr[i] = np.mean(tr[i-period+1:i+1])
        # Fill initial values
        atr[:period-1] = atr[period-1]
        
    else:  # rma (Wilder's smoothing)
        # RMA formula: alpha = 1/period
        # RMA[i] = (RMA[i-1] * (period-1) + TR[i]) / period
        alpha = 1.0 / period
        atr = np.zeros_like(tr)
        
        # Initialize with SMA for first period
        atr[period-1] = np.mean(tr[:period])
        
        # Apply RMA
        for i in range(period, len(tr)):
            atr[i] = alpha * tr[i] + (1 - alpha) * atr[i-1]
        
        # Fill initial values
        atr[:period-1] = atr[period-1]
    
    return atr


def calculate_supertrend(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr_period: int = 10,
    multiplier: float = 3.0,
    atr_method: str = "rma"
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate SuperTrend indicator.
    
    SuperTrend uses ATR-based bands to identify trend direction.
    When price crosses above the lower band, it signals uptrend.
    When price crosses below the upper band, it signals downtrend.
    
    Parameters:
    -----------
    high : np.ndarray
        Array of high prices
    low : np.ndarray
        Array of low prices
    close : np.ndarray
        Array of closing prices
    atr_period : int, default=10
        Period for ATR calculation
    multiplier : float, default=3.0
        ATR multiplier for band width
    atr_method : str, default="rma"
        ATR calculation method:
        - "rma": Wilder's smoothing (default, matches Pine Script)
        - "sma": Simple moving average
        
    Returns:
    --------
    Tuple[np.ndarray, np.ndarray]
        - supertrend: SuperTrend indicator line
        - trend: Trend direction (1 = uptrend, -1 = downtrend)
        
    Raises:
    -------
    InsufficientDataError
        If not enough data points for calculation
    ValueError
        If invalid parameters
        
    Example:
    --------
    >>> import numpy as np
    >>> high = np.array([102, 104, 103, 105, 107, 106, 108, 110])
    >>> low = np.array([98, 100, 99, 101, 103, 102, 104, 106])
    >>> close = np.array([100, 102, 101, 103, 105, 104, 106, 108])
    >>> supertrend, trend = calculate_supertrend(high, low, close)
    >>> print(f"Current trend: {'Uptrend' if trend[-1] == 1 else 'Downtrend'}")
    """
    # Input validation
    if not isinstance(high, np.ndarray):
        high = np.array(high, dtype=np.float64)
    if not isinstance(low, np.ndarray):
        low = np.array(low, dtype=np.float64)
    if not isinstance(close, np.ndarray):
        close = np.array(close, dtype=np.float64)
    
    if len(high) != len(low) or len(high) != len(close):
        raise ValueError("high, low, and close arrays must have the same length")
    
    if len(high) < atr_period:
        raise InsufficientDataError(
            f"SuperTrend requires at least {atr_period} data points, got {len(high)}"
        )
    
    if multiplier <= 0:
        raise ValueError(f"multiplier must be positive, got {multiplier}")
    
    if atr_period < 1:
        raise ValueError(f"atr_period must be at least 1, got {atr_period}")
    
    # Calculate ATR
    atr = calculate_atr(high, low, close, atr_period, atr_method)
    
    # Calculate basic upper and lower bands
    # Using hl2 as source (high + low) / 2
    hl2 = (high + low) / 2.0
    
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)
    
    # Initialize final bands
    final_upper = np.copy(basic_upper)
    final_lower = np.copy(basic_lower)
    
    # Calculate final bands (bands can only move in favorable direction)
    for i in range(1, len(close)):
        # Upper band can only decrease or stay same during downtrend
        if basic_upper[i] < final_upper[i-1] or close[i-1] > final_upper[i-1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i-1]
        
        # Lower band can only increase or stay same during uptrend
        if basic_lower[i] > final_lower[i-1] or close[i-1] < final_lower[i-1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i-1]
    
    # Determine trend direction
    trend = np.ones(len(close), dtype=np.int32)
    supertrend = np.zeros_like(close)
    
    # Initial trend based on first close position
    if close[0] <= final_upper[0]:
        trend[0] = -1
        supertrend[0] = final_upper[0]
    else:
        trend[0] = 1
        supertrend[0] = final_lower[0]
    
    for i in range(1, len(close)):
        # Trend changes when price crosses the bands
        if trend[i-1] == 1:
            # In uptrend, check if price breaks below lower band
            if close[i] <= final_lower[i]:
                trend[i] = -1
            else:
                trend[i] = 1
        else:  # trend[i-1] == -1
            # In downtrend, check if price breaks above upper band
            if close[i] >= final_upper[i]:
                trend[i] = 1
            else:
                trend[i] = -1
        
        # SuperTrend line follows the appropriate band
        if trend[i] == 1:
            supertrend[i] = final_lower[i]
        else:
            supertrend[i] = final_upper[i]
    
    return supertrend, trend


def get_supertrend_signal(
    close: np.ndarray,
    trend: np.ndarray,
    lookback: int = 1
) -> str:
    """
    Get trading signal from SuperTrend indicator.
    
    Parameters:
    -----------
    close : np.ndarray
        Closing prices
    trend : np.ndarray
        Trend direction array from calculate_supertrend
    lookback : int, default=1
        Number of bars to look back for trend change
        
    Returns:
    --------
    str
        "BUY", "SELL", or "NEUTRAL"
    """
    if len(trend) < lookback + 1:
        return "NEUTRAL"
    
    # Check for trend change
    current_trend = trend[-1]
    previous_trend = trend[-lookback - 1]
    
    if current_trend == 1 and previous_trend == -1:
        return "BUY"
    elif current_trend == -1 and previous_trend == 1:
        return "SELL"
    else:
        return "NEUTRAL"


def supertrend_with_signal(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr_period: int = 10,
    multiplier: float = 3.0,
    atr_method: str = "rma"
) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Calculate SuperTrend and get current signal in one call.
    
    Returns:
    --------
    Tuple[np.ndarray, np.ndarray, str]
        - supertrend: SuperTrend indicator line
        - trend: Trend direction (1 or -1)
        - signal: Current trading signal ("BUY", "SELL", "NEUTRAL")
    """
    supertrend, trend = calculate_supertrend(
        high, low, close, atr_period, multiplier, atr_method
    )
    signal = get_supertrend_signal(close, trend)
    return supertrend, trend, signal


if __name__ == "__main__":
    # Quick test
    print("SuperTrend Indicator - Quick Test")
    print("=" * 50)
    
    # Generate sample data
    np.random.seed(42)
    n = 100
    base_price = 100
    
    # Simulate price movement
    high = np.cumsum(np.random.randn(n) * 0.5) + base_price + 1
    low = high - np.random.rand(n) * 2
    close = low + (high - low) * np.random.rand(n)
    
    try:
        supertrend, trend, signal = supertrend_with_signal(
            high, low, close,
            atr_period=10,
            multiplier=3.0
        )
        
        print(f"✅ Calculation successful!")
        print(f"Last 5 closes: {close[-5:]}")
        print(f"Last 5 SuperTrend values: {supertrend[-5:]}")
        print(f"Last 5 trend: {trend[-5:]}")
        print(f"Current signal: {signal}")
        
        # Statistics
        uptrend_bars = np.sum(trend == 1)
        downtrend_bars = np.sum(trend == -1)
        trend_changes = np.sum(np.diff(trend) != 0)
        
        print(f"\n📊 Statistics:")
        print(f"Uptrend bars: {uptrend_bars} ({uptrend_bars/len(trend)*100:.1f}%)")
        print(f"Downtrend bars: {downtrend_bars} ({downtrend_bars/len(trend)*100:.1f}%)")
        print(f"Trend changes: {trend_changes}")
        
    except Exception as e:
        print(f"❌ Error: {e}")