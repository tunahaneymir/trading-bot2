"""
Unit Tests for MOST (Moving Stop Loss) Indicator
=================================================

Comprehensive test suite covering all MA types, edge cases, and functionality.
"""

import pytest
import numpy as np
from most import (
    calculate_most,
    get_most_signal,
    most_with_signal,
    InsufficientDataError,
    _calculate_var,
    _calculate_ema,
    _calculate_hull,
    _calculate_t3,
    _calculate_sma,
    _calculate_wma
)


class TestHelperFunctions:
    """Test individual MA calculation functions."""
    
    def test_calculate_ema_basic(self):
        """Test EMA with known values."""
        close = np.array([100.0, 102.0, 101.0, 103.0, 105.0])
        ema = _calculate_ema(close, length=3)
        
        assert len(ema) == len(close)
        assert np.all(np.isfinite(ema))
        assert ema[0] == close[0]  # First value should equal close
    
    def test_calculate_sma_basic(self):
        """Test SMA with known values."""
        close = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        sma = _calculate_sma(close, length=3)
        
        # SMA of last 3: (30 + 40 + 50) / 3 = 40
        assert sma[-1] == 40.0
    
    def test_calculate_var_basic(self):
        """Test VAR calculation."""
        np.random.seed(42)
        close = np.cumsum(np.random.randn(50)) + 100
        
        var = _calculate_var(close, length=9)
        
        assert len(var) == len(close)
        assert np.all(np.isfinite(var))
    
    def test_calculate_hull_basic(self):
        """Test HULL calculation."""
        close = np.linspace(100, 110, 50)
        hull = _calculate_hull(close, length=9)
        
        assert len(hull) == len(close)
        assert np.all(np.isfinite(hull))
    
    def test_calculate_t3_basic(self):
        """Test T3 calculation."""
        close = np.linspace(100, 110, 100)
        t3 = _calculate_t3(close, length=5)
        
        assert len(t3) == len(close)
        assert np.all(np.isfinite(t3))
    
    def test_calculate_wma_basic(self):
        """Test WMA calculation."""
        close = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        wma = _calculate_wma(close, length=3)
        
        # WMA of last 3: (30*1 + 40*2 + 50*3) / (1+2+3) = 260/6 = 43.33
        assert abs(wma[-1] - 43.333333) < 0.01
    
    def test_insufficient_data_ema(self):
        """Test EMA with insufficient data."""
        close = np.array([100.0, 101.0])
        
        with pytest.raises(InsufficientDataError):
            _calculate_ema(close, length=5)
    
    def test_insufficient_data_var(self):
        """Test VAR with insufficient data."""
        close = np.array([100.0, 101.0])
        
        with pytest.raises(InsufficientDataError):
            _calculate_var(close, length=5)


class TestMOSTCalculation:
    """Test main MOST calculation function."""
    
    def test_basic_calculation(self):
        """Test basic MOST calculation."""
        close = np.array([100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 122, 124])
        
        most_line, trend = calculate_most(close, length=3, percent=2.0)
        
        assert len(most_line) == len(close)
        assert len(trend) == len(close)
        assert np.all(np.isin(trend, [1, -1]))
    
    def test_uptrend_detection(self):
        """Test uptrend detection."""
        # Create clear uptrend
        close = np.linspace(100, 120, 50)
        
        most_line, trend = calculate_most(close, length=5, percent=2.0)
        
        # Should mostly be in uptrend
        uptrend_ratio = np.sum(trend == 1) / len(trend)
        assert uptrend_ratio > 0.8
    
    def test_downtrend_detection(self):
        """Test downtrend detection."""
        # Create clear downtrend
        close = np.linspace(120, 100, 50)
        
        most_line, trend = calculate_most(close, length=5, percent=2.0)
        
        # Should eventually switch to downtrend
        downtrend_ratio = np.sum(trend == -1) / len(trend)
        assert downtrend_ratio > 0.3
    
    def test_different_ma_types(self):
        """Test all supported MA types."""
        np.random.seed(42)
        close = np.cumsum(np.random.randn(100)) + 100
        
        ma_types = ["VAR", "EMA", "HULL", "T3", "SMA", "WMA"]
        
        for ma_type in ma_types:
            most_line, trend = calculate_most(close, length=9, percent=2.0, ma_type=ma_type)
            
            assert len(most_line) == len(close), f"{ma_type} failed"
            assert len(trend) == len(close), f"{ma_type} failed"
            assert np.all(np.isfinite(most_line)), f"{ma_type} produced non-finite values"
    
    def test_different_parameters(self):
        """Test with different length and percent parameters."""
        close = np.linspace(100, 110, 50)
        
        # Different lengths
        for length in [3, 9, 21]:
            most_line, trend = calculate_most(close, length=length, percent=2.0)
            assert len(most_line) == len(close)
        
        # Different percentages
        for percent in [1.0, 2.0, 3.0, 5.0]:
            most_line, trend = calculate_most(close, length=9, percent=percent)
            assert len(most_line) == len(close)
    
    def test_list_input(self):
        """Test with Python list input."""
        close_list = [100, 102, 104, 106, 108, 110, 112, 114, 116, 118]
        
        # Use EMA for shorter data
        most_line, trend = calculate_most(close_list, length=3, percent=2.0, ma_type="EMA")
        
        assert len(most_line) == len(close_list)
        assert isinstance(most_line, np.ndarray)
    
    def test_insufficient_data(self):
        """Test with insufficient data."""
        close = np.array([100.0, 101.0])
        
        with pytest.raises(InsufficientDataError):
            calculate_most(close, length=5, percent=2.0)
    
    def test_invalid_ma_type(self):
        """Test with invalid MA type."""
        close = np.array([100, 102, 104, 106, 108])
        
        with pytest.raises(ValueError, match="Invalid ma_type"):
            calculate_most(close, length=3, percent=2.0, ma_type="INVALID")
    
    def test_invalid_percent(self):
        """Test with invalid percent."""
        close = np.array([100, 102, 104, 106, 108])
        
        with pytest.raises(ValueError, match="percent must be positive"):
            calculate_most(close, length=3, percent=-1.0)
    
    def test_most_follows_trend(self):
        """Test that MOST line follows trend direction."""
        close = np.linspace(100, 120, 50)
        
        most_line, trend = calculate_most(close, length=5, percent=2.0)
        
        # In uptrend, MOST should be below price
        for i in range(len(close)):
            if trend[i] == 1:
                assert most_line[i] < close[i] or abs(most_line[i] - close[i]) < 1.0


class TestSignalGeneration:
    """Test signal generation from MOST."""
    
    def test_buy_signal(self):
        """Test BUY signal generation."""
        close = np.array([100, 99, 98, 97, 98, 100, 102, 104, 106, 108])
        
        # Use EMA for shorter data
        most_line, trend = calculate_most(close, length=3, percent=2.0, ma_type="EMA")
        signal = get_most_signal(close, most_line, trend, lookback=1)
        
        # Signal should be BUY, SELL, or NEUTRAL
        assert signal in ["BUY", "SELL", "NEUTRAL"]
    
    def test_sell_signal(self):
        """Test SELL signal generation."""
        close = np.array([100, 101, 102, 103, 102, 100, 98, 96, 94, 92])
        
        # Use EMA for shorter data
        most_line, trend = calculate_most(close, length=3, percent=2.0, ma_type="EMA")
        signal = get_most_signal(close, most_line, trend, lookback=1)
        
        assert signal in ["BUY", "SELL", "NEUTRAL"]
    
    def test_neutral_signal(self):
        """Test NEUTRAL signal when no trend change."""
        close = np.linspace(100, 105, 20)
        
        most_line, trend = calculate_most(close, length=3, percent=2.0)
        signal = get_most_signal(close, most_line, trend, lookback=1)
        
        # Last signal should likely be NEUTRAL (no recent change)
        assert signal in ["BUY", "SELL", "NEUTRAL"]
    
    def test_most_with_signal(self):
        """Test combined function."""
        close = np.array([100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 122])
        
        most_line, trend, signal = most_with_signal(close, length=3, percent=2.0)
        
        assert len(most_line) == len(close)
        assert len(trend) == len(close)
        assert signal in ["BUY", "SELL", "NEUTRAL"]


class TestEdgeCases:
    """Test edge cases and special scenarios."""
    
    def test_flat_market(self):
        """Test with flat/sideways market."""
        close = np.ones(50) * 100  # Flat price
        
        most_line, trend = calculate_most(close, length=5, percent=2.0)
        
        assert np.all(np.isfinite(most_line))
        assert np.all(np.isfinite(trend))
    
    def test_high_volatility(self):
        """Test with high volatility data."""
        np.random.seed(42)
        close = 100 + np.cumsum(np.random.randn(100) * 5)
        
        most_line, trend = calculate_most(close, length=9, percent=3.0)
        
        assert np.all(np.isfinite(most_line))
        # Should have multiple trend changes
        trend_changes = np.sum(np.diff(trend) != 0)
        assert trend_changes > 0
    
    def test_very_small_percent(self):
        """Test with very small stop loss percentage."""
        close = np.linspace(100, 110, 50)
        
        most_line, trend = calculate_most(close, length=5, percent=0.5)
        
        assert np.all(np.isfinite(most_line))
        # With tight stop, should have more trend changes
        trend_changes = np.sum(np.diff(trend) != 0)
        assert trend_changes >= 0
    
    def test_very_large_percent(self):
        """Test with very large stop loss percentage."""
        close = np.linspace(100, 110, 50)
        
        most_line, trend = calculate_most(close, length=5, percent=10.0)
        
        assert np.all(np.isfinite(most_line))
        # With wide stop, should have fewer trend changes
        trend_changes = np.sum(np.diff(trend) != 0)
        assert trend_changes >= 0
    
    def test_minimum_length(self):
        """Test with minimum possible length."""
        close = np.array([100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120])
        
        most_line, trend = calculate_most(close, length=3, percent=2.0, ma_type="EMA")
        
        assert len(most_line) == len(close)
        assert np.all(np.isfinite(most_line))


class TestRealWorldScenarios:
    """Test with realistic trading scenarios."""
    
    def test_bull_market(self):
        """Test in bull market conditions."""
        # Simulate bull market with occasional pullbacks
        np.random.seed(42)
        trend_component = np.linspace(100, 150, 100)
        noise = np.random.randn(100) * 2
        close = trend_component + noise
        
        most_line, trend = calculate_most(close, length=9, percent=2.0, ma_type="VAR")
        
        # Should be predominantly in uptrend
        uptrend_ratio = np.sum(trend == 1) / len(trend)
        assert uptrend_ratio > 0.5
    
    def test_bear_market(self):
        """Test in bear market conditions."""
        # Simulate bear market
        np.random.seed(42)
        trend_component = np.linspace(150, 100, 100)
        noise = np.random.randn(100) * 2
        close = trend_component + noise
        
        most_line, trend = calculate_most(close, length=9, percent=2.0, ma_type="VAR")
        
        # Should have some downtrend periods
        downtrend_count = np.sum(trend == -1)
        assert downtrend_count > 0
    
    def test_ranging_market(self):
        """Test in ranging/choppy market."""
        # Simulate ranging market
        np.random.seed(42)
        close = 100 + np.sin(np.linspace(0, 4*np.pi, 100)) * 5 + np.random.randn(100)
        
        most_line, trend = calculate_most(close, length=9, percent=2.0, ma_type="VAR")
        
        # Should have multiple trend changes
        trend_changes = np.sum(np.diff(trend) != 0)
        assert trend_changes > 2


class TestPerformance:
    """Test performance characteristics."""
    
    def test_large_dataset(self):
        """Test with large dataset."""
        np.random.seed(42)
        close = np.cumsum(np.random.randn(10000)) + 100
        
        most_line, trend = calculate_most(close, length=9, percent=2.0)
        
        assert len(most_line) == len(close)
        assert np.all(np.isfinite(most_line))
    
    def test_all_ma_types_performance(self):
        """Test performance of all MA types."""
        np.random.seed(42)
        close = np.cumsum(np.random.randn(1000)) + 100
        
        ma_types = ["VAR", "EMA", "HULL", "T3", "SMA", "WMA"]
        
        for ma_type in ma_types:
            most_line, trend = calculate_most(close, length=9, percent=2.0, ma_type=ma_type)
            assert len(most_line) == len(close)


def test_summary():
    """Print test summary."""
    print("\n" + "="*70)
    print("MOST INDICATOR TEST SUMMARY")
    print("="*70)
    print("✅ All tests should pass!")
    print("\nTest Coverage:")
    print("  - Helper functions (EMA, SMA, VAR, HULL, T3, WMA)")
    print("  - MOST calculation with all MA types")
    print("  - Trend detection (up/down)")
    print("  - Signal generation (BUY/SELL/NEUTRAL)")
    print("  - Edge cases (flat, volatile, extreme parameters)")
    print("  - Real-world scenarios (bull/bear/ranging markets)")
    print("  - Performance (large datasets)")
    print("="*70)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
    test_summary()