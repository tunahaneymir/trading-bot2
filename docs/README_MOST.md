# MOST (Moving Stop Loss) Indicator

## 📊 Overview

MOST is a trend-following indicator that uses adaptive moving averages with percentage-based stop loss bands to identify trend direction and potential reversal points.

**Version:** 1.0.0  
**Status:** ✅ Production Ready (33/33 tests passing)  
**Author:** Trading Bot System  

## 🎯 Features

- ✅ **Multiple MA Types**: VAR (default), EMA, HULL, T3, SMA, WMA
- ✅ **Adaptive Stop Loss**: Percentage-based stop loss that follows trend
- ✅ **Trend Detection**: Identifies uptrends (1) and downtrends (-1)
- ✅ **Signal Generation**: BUY/SELL/NEUTRAL signals on trend changes
- ✅ **Windows Compatible**: Cross-platform implementation
- ✅ **Well Tested**: Comprehensive test suite with 33 unit tests
- ✅ **Type Hints**: Full type annotations for IDE support
- ✅ **Error Handling**: Proper exceptions and validation

## 📦 Installation

```python
# No installation needed - just copy most.py to your project
from most import calculate_most, most_with_signal
```

## 🚀 Quick Start

### Basic Usage

```python
import numpy as np
from most import calculate_most

# Sample price data
close = np.array([100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 122])

# Calculate MOST
most_line, trend_direction = calculate_most(
    close, 
    length=9,          # MA period
    percent=2.0,       # Stop loss percentage
    ma_type="VAR"      # Moving average type
)

print(f"Current MOST value: {most_line[-1]:.2f}")
print(f"Current trend: {'Uptrend' if trend_direction[-1] == 1 else 'Downtrend'}")
```

### With Signal Generation

```python
from most import most_with_signal

# Get MOST values, trend, and current signal in one call
most_line, trend, signal = most_with_signal(
    close,
    length=9,
    percent=2.0,
    ma_type="VAR"
)

print(f"Current signal: {signal}")  # "BUY", "SELL", or "NEUTRAL"
```

## 📚 API Reference

### Main Functions

#### `calculate_most(close, length=3, percent=2.0, ma_type="VAR")`

Calculate MOST indicator values.

**Parameters:**
- `close` (np.ndarray): Array of closing prices
- `length` (int, default=3): Period for moving average
- `percent` (float, default=2.0): Stop loss percentage (e.g., 2.0 = 2%)
- `ma_type` (str, default="VAR"): Type of moving average
  - `"VAR"`: Variable Index Dynamic Average (adaptive)
  - `"EMA"`: Exponential Moving Average
  - `"HULL"`: Hull Moving Average (smooth & responsive)
  - `"T3"`: Tillson T3 (very smooth)
  - `"SMA"`: Simple Moving Average
  - `"WMA"`: Weighted Moving Average

**Returns:**
- `Tuple[np.ndarray, np.ndarray]`: (most_line, trend_direction)
  - `most_line`: MOST indicator values (stop loss level)
  - `trend_direction`: Trend direction (1 = uptrend, -1 = downtrend)

**Raises:**
- `InsufficientDataError`: Not enough data points
- `ValueError`: Invalid parameters

#### `most_with_signal(close, length=3, percent=2.0, ma_type="VAR")`

Calculate MOST and get current trading signal.

**Returns:**
- `Tuple[np.ndarray, np.ndarray, str]`: (most_line, trend_direction, signal)
  - `signal`: "BUY", "SELL", or "NEUTRAL"

#### `get_most_signal(close, most_line, trend_direction, lookback=1)`

Get trading signal from MOST indicator.

**Parameters:**
- `close` (np.ndarray): Closing prices
- `most_line` (np.ndarray): MOST indicator line
- `trend_direction` (np.ndarray): Trend direction array
- `lookback` (int, default=1): Bars to look back for trend change

**Returns:**
- `str`: "BUY", "SELL", or "NEUTRAL"

## 🎨 Moving Average Types

### VAR (Variable Index Dynamic Average) - Default
- **Best for:** Adaptive to market conditions
- **Characteristics:** More responsive during trends, smoother during consolidation
- **Use case:** All-purpose adaptive indicator

### EMA (Exponential Moving Average)
- **Best for:** Quick response to price changes
- **Characteristics:** Exponentially weighted recent prices
- **Use case:** Short-term trading, fast trends

### HULL (Hull Moving Average)
- **Best for:** Smooth yet responsive
- **Characteristics:** Reduces lag while maintaining smoothness
- **Use case:** Medium-term trends, less noise

### T3 (Tillson T3)
- **Best for:** Very smooth trends
- **Characteristics:** Six-pass smoothing, very low noise
- **Use case:** Long-term trends, stable signals

### SMA (Simple Moving Average)
- **Best for:** Traditional analysis
- **Characteristics:** Simple arithmetic average
- **Use case:** Basic trend following

### WMA (Weighted Moving Average)
- **Best for:** Recent price emphasis
- **Characteristics:** Linearly weighted recent prices
- **Use case:** Short to medium-term trends

## 📊 Usage in Trading System

### Integration Example

```python
from most import calculate_most

def check_trend_signal(prices, length=9, percent=2.0):
    """
    Check MOST trend signal for trading decision.
    
    Parameters:
    -----------
    prices : np.ndarray
        Historical closing prices
    length : int
        MOST period parameter
    percent : float
        Stop loss percentage
        
    Returns:
    --------
    dict : Trading signal information
    """
    # Calculate MOST
    most_line, trend = calculate_most(
        prices,
        length=length,
        percent=percent,
        ma_type="VAR"
    )
    
    # Check for trend change
    current_trend = trend[-1]
    previous_trend = trend[-2] if len(trend) > 1 else current_trend
    
    # Determine signal
    if current_trend == 1 and previous_trend == -1:
        signal = "BUY"
    elif current_trend == -1 and previous_trend == 1:
        signal = "SELL"
    else:
        signal = "HOLD"
    
    return {
        'signal': signal,
        'trend': 'UPTREND' if current_trend == 1 else 'DOWNTREND',
        'most_value': most_line[-1],
        'current_price': prices[-1],
        'stop_loss': most_line[-1]
    }
```

### Multi-Timeframe Example

```python
def multi_timeframe_most(prices_15m, prices_1h):
    """
    Use MOST on multiple timeframes for confirmation.
    
    Returns True if both timeframes show uptrend.
    """
    # 15-minute timeframe (faster)
    _, trend_15m = calculate_most(prices_15m, length=9, percent=2.0, ma_type="VAR")
    
    # 1-hour timeframe (slower)
    _, trend_1h = calculate_most(prices_1h, length=21, percent=3.0, ma_type="HULL")
    
    # Both must agree
    return trend_15m[-1] == 1 and trend_1h[-1] == 1
```

## ⚙️ Parameter Guidelines

### Length (MA Period)
- **3-9**: Very short-term, quick signals, more noise
- **9-21**: Medium-term, balanced (recommended for 15m charts)
- **21-50**: Long-term, stable, less noise (recommended for 1h charts)

### Percent (Stop Loss)
- **1.0-2.0%**: Tight stop, more signals, good for volatile markets
- **2.0-3.0%**: Balanced, moderate signals (recommended)
- **3.0-5.0%**: Wide stop, fewer signals, good for ranging markets

### MA Type Selection
- **Trending markets**: VAR or EMA (responsive)
- **Choppy markets**: HULL or T3 (smooth)
- **Mixed conditions**: VAR (adaptive)

## 🧪 Testing

Run comprehensive test suite:

```bash
pytest test_most.py -v
```

**Test Coverage:**
- ✅ Helper functions (all MA types)
- ✅ MOST calculation
- ✅ Trend detection
- ✅ Signal generation
- ✅ Edge cases
- ✅ Real-world scenarios
- ✅ Performance tests

**Result:** 33/33 tests passing ✅

## 📈 Demo

Run interactive demo:

```bash
python demo_most.py
```

Demo includes:
1. Basic usage examples
2. MA type comparison
3. Parameter sensitivity analysis
4. Signal generation demo
5. Visualization (if matplotlib available)

## 📋 Requirements

```
numpy >= 1.20.0
```

**Optional:**
```
matplotlib >= 3.0.0  # For visualization
pytest >= 7.0.0      # For testing
```

## 🎯 Best Practices

1. **Combine with other indicators**: MOST works best with confirmation
   - Use with momentum indicators (RSI, MACD)
   - Combine with volume indicators (RVOL)
   - Add support/resistance levels

2. **Multi-timeframe analysis**: 
   - Use shorter MOST for entry timing
   - Use longer MOST for trend confirmation

3. **Parameter optimization**:
   - Test different lengths for your timeframe
   - Adjust percent based on asset volatility
   - Consider market conditions when choosing MA type

4. **Risk management**:
   - Use MOST line as trailing stop loss
   - Don't trade against the trend
   - Wait for confirmation signals

## ⚠️ Limitations

- Works best in trending markets
- Can generate false signals in ranging/choppy markets
- Lags during rapid price movements
- Not suitable as standalone indicator

## 📊 Performance Characteristics

- **Calculation time**: O(n) for most MA types
- **Memory usage**: O(n) where n is data length
- **Data requirements**: 
  - VAR: length + 9 data points minimum
  - Other MA types: length data points minimum

## 🔧 Troubleshooting

### InsufficientDataError

**Problem:** Not enough data points for calculation

**Solution:**
```python
# For VAR (default), need length + 9 points
close = np.array([...])  # Make sure len(close) >= length + 9

# Or use EMA which needs less data
most_line, trend = calculate_most(close, length=9, ma_type="EMA")
```

### Unexpected trend changes

**Problem:** Too many trend switches

**Solution:**
```python
# Increase stop loss percentage
most_line, trend = calculate_most(close, percent=3.0)  # Instead of 2.0

# Or use smoother MA type
most_line, trend = calculate_most(close, ma_type="HULL")  # Instead of EMA
```

## 📚 References

- Pine Script MOST indicator
- Variable Index Dynamic Average (Tushar Chande)
- Adaptive moving average techniques

## 📝 License

Part of Trading Bot System - Internal Use

## 🤝 Contributing

For bugs or improvements, contact the development team.

---

**Last Updated:** November 2025  
**Status:** ✅ Production Ready
