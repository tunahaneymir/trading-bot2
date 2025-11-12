"""
Unit Tests for QQE MOD Indicator
=================================

Tests QQE MOD calculation, signal detection, and error handling.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from indicators.qqe_mod import QQEMod, qqe_mod, qqe_signal, InsufficientDataError


class TestQQEMod:
    """Test suite for QQE MOD indicator."""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample price data for testing."""
        np.random.seed(42)
        dates = pd.date_range('2024-01-01', periods=200, freq='15T')
        
        # Simulated price with trend
        price = 100 + np.cumsum(np.random.randn(200) * 2)
        close = pd.Series(price, index=dates)
        
        return close
    
    @pytest.fixture
    def trending_data(self):
        """Create trending price data."""
        dates = pd.date_range('2024-01-01', periods=200, freq='15T')
        
        # Strong uptrend
        price = 100 + np.linspace(0, 50, 200) + np.random.randn(200) * 0.5
        close = pd.Series(price, index=dates)
        
        return close
    
    def test_initialization(self):
        """Test QQE MOD initialization with default parameters."""
        qqe = QQEMod()
        
        assert qqe.rsi_period == 14
        assert qqe.rsi_smoothing == 5
        assert qqe.qqe_factor == 4.236
        assert qqe.signal_smoothing == 5
        assert qqe.min_periods > 0
    
    def test_custom_parameters(self):
        """Test QQE MOD with custom parameters."""
        qqe = QQEMod(
            rsi_period=21,
            rsi_smoothing=9,
            qqe_factor=3.0,
            signal_smoothing=9
        )
        
        assert qqe.rsi_period == 21
        assert qqe.rsi_smoothing == 9
        assert qqe.qqe_factor == 3.0
        assert qqe.signal_smoothing == 9
    
    def test_calculate_basic(self, sample_data):
        """Test basic QQE MOD calculation."""
        qqe = QQEMod()
        qqe_fast, qqe_slow, histogram = qqe.calculate(sample_data)
        
        # Check output types
        assert isinstance(qqe_fast, pd.Series)
        assert isinstance(qqe_slow, pd.Series)
        assert isinstance(histogram, pd.Series)
        
        # Check lengths match
        assert len(qqe_fast) == len(sample_data)
        assert len(qqe_slow) == len(sample_data)
        assert len(histogram) == len(sample_data)
        
        # Check for valid values (no NaN in later periods)
        assert not qqe_fast.iloc[-50:].isna().any()
        assert not qqe_slow.iloc[-50:].isna().any()
        assert not histogram.iloc[-50:].isna().any()
    
    def test_histogram_calculation(self, sample_data):
        """Test histogram is correctly calculated as fast - slow."""
        qqe = QQEMod()
        qqe_fast, qqe_slow, histogram = qqe.calculate(sample_data)
        
        # Verify histogram = fast - slow
        calculated_hist = qqe_fast - qqe_slow
        np.testing.assert_array_almost_equal(
            histogram.values, 
            calculated_hist.values,
            decimal=10
        )
    
    def test_signal_detection(self, trending_data):
        """Test signal detection (crosses)."""
        qqe = QQEMod()
        signal = qqe.get_signal(trending_data)
        
        # Check signal types
        assert signal.isin([-1, 0, 1]).all()
        
        # Should have some signals in trending data
        assert (signal != 0).any()
        
        # Check for bullish signals (uptrend should have bullish signals)
        assert (signal == 1).any()
    
    def test_bullish_cross(self):
        """Test bullish cross detection."""
        # Create data with clear bullish cross
        np.random.seed(123)
        dates = pd.date_range('2024-01-01', periods=150, freq='15min')
        
        # Downtrend then strong uptrend with noise
        downtrend = np.linspace(100, 90, 75) + np.random.randn(75) * 0.5
        uptrend = np.linspace(90, 115, 75) + np.random.randn(75) * 0.5
        price = np.concatenate([downtrend, uptrend])
        close = pd.Series(price, index=dates)
        
        qqe = QQEMod()
        signal = qqe.get_signal(close)
        
        # Should detect bullish cross when trend changes
        # Check that there's at least one bullish signal in the uptrend portion
        uptrend_signals = signal.iloc[75:]
        assert (uptrend_signals == 1).any(), "No bullish signal detected in uptrend"
    
    def test_bearish_cross(self):
        """Test bearish cross detection."""
        # Create data with clear bearish cross
        np.random.seed(456)
        dates = pd.date_range('2024-01-01', periods=150, freq='15min')
        
        # Uptrend then strong downtrend with noise
        uptrend = np.linspace(100, 115, 75) + np.random.randn(75) * 0.5
        downtrend = np.linspace(115, 90, 75) + np.random.randn(75) * 0.5
        price = np.concatenate([uptrend, downtrend])
        close = pd.Series(price, index=dates)
        
        qqe = QQEMod()
        signal = qqe.get_signal(close)
        
        # Should detect bearish cross when trend changes
        # Check that there's at least one bearish signal in the downtrend portion
        downtrend_signals = signal.iloc[75:]
        assert (downtrend_signals == -1).any(), "No bearish signal detected in downtrend"
    
    def test_current_state(self, sample_data):
        """Test get_current_state method."""
        qqe = QQEMod()
        state = qqe.get_current_state(sample_data)
        
        # Check all required keys exist
        required_keys = ['qqe_fast', 'qqe_slow', 'histogram', 'signal', 
                        'bullish', 'bearish', 'strength']
        for key in required_keys:
            assert key in state
        
        # Check types
        assert isinstance(state['qqe_fast'], float)
        assert isinstance(state['qqe_slow'], float)
        assert isinstance(state['histogram'], float)
        assert isinstance(state['signal'], (int, np.integer))
        assert isinstance(state['bullish'], (bool, np.bool_))  # Accept numpy bool too
        assert isinstance(state['bearish'], (bool, np.bool_))  # Accept numpy bool too
        assert isinstance(state['strength'], float)
        
        # Check signal value
        assert state['signal'] in [-1, 0, 1]
        
        # Check bullish/bearish logic
        if state['bullish']:
            assert not state['bearish']
        if state['bearish']:
            assert not state['bullish']
    
    def test_insufficient_data(self):
        """Test error handling for insufficient data."""
        qqe = QQEMod()
        
        # Create data with insufficient length
        dates = pd.date_range('2024-01-01', periods=10, freq='15T')
        close = pd.Series(range(100, 110), index=dates)
        
        with pytest.raises(InsufficientDataError):
            qqe.calculate(close)
    
    def test_nan_handling(self, sample_data):
        """Test handling of NaN values."""
        qqe = QQEMod()
        
        # Insert NaN
        data_with_nan = sample_data.copy()
        data_with_nan.iloc[50] = np.nan
        
        with pytest.raises(ValueError, match="NaN"):
            qqe.calculate(data_with_nan)
    
    def test_inf_handling(self, sample_data):
        """Test handling of infinite values."""
        qqe = QQEMod()
        
        # Insert inf
        data_with_inf = sample_data.copy()
        data_with_inf.iloc[50] = np.inf
        
        with pytest.raises(ValueError, match="infinite"):
            qqe.calculate(data_with_inf)
    
    def test_convenience_functions(self, sample_data):
        """Test convenience functions."""
        # Test qqe_mod function
        qqe_fast, qqe_slow, histogram = qqe_mod(sample_data)
        
        assert isinstance(qqe_fast, pd.Series)
        assert isinstance(qqe_slow, pd.Series)
        assert isinstance(histogram, pd.Series)
        
        # Test qqe_signal function
        signal = qqe_signal(sample_data)
        
        assert isinstance(signal, pd.Series)
        assert signal.isin([-1, 0, 1]).all()
    
    def test_parameter_sensitivity(self, sample_data):
        """Test sensitivity to different parameters."""
        # Default parameters
        qqe_default = QQEMod()
        signal_default = qqe_default.get_signal(sample_data)
        
        # More sensitive parameters
        qqe_sensitive = QQEMod(rsi_period=7, qqe_factor=2.0)
        signal_sensitive = qqe_sensitive.get_signal(sample_data)
        
        # Sensitive version should generate more signals
        assert (signal_sensitive != 0).sum() >= (signal_default != 0).sum()
    
    def test_consistency(self, sample_data):
        """Test calculation consistency (same input = same output)."""
        qqe = QQEMod()
        
        # Calculate twice
        result1 = qqe.calculate(sample_data)
        result2 = qqe.calculate(sample_data)
        
        # Results should be identical
        for r1, r2 in zip(result1, result2):
            np.testing.assert_array_equal(r1.values, r2.values)
    
    def test_signal_alternation(self):
        """Test that signals alternate properly (no consecutive same signals)."""
        # Create oscillating data
        dates = pd.date_range('2024-01-01', periods=200, freq='15T')
        
        # Sine wave to create oscillations
        price = 100 + 10 * np.sin(np.linspace(0, 4*np.pi, 200))
        close = pd.Series(price, index=dates)
        
        qqe = QQEMod()
        signal = qqe.get_signal(close)
        
        # Get non-zero signals
        nonzero_signals = signal[signal != 0]
        
        if len(nonzero_signals) > 1:
            # Check that consecutive non-zero signals alternate
            for i in range(len(nonzero_signals) - 1):
                # Next non-zero signal should be opposite
                curr = nonzero_signals.iloc[i]
                next_sig = nonzero_signals.iloc[i + 1]
                
                # They should have opposite signs (1 → -1 or -1 → 1)
                assert curr * next_sig == -1, "Signals should alternate"
    
    def test_values_in_range(self, sample_data):
        """Test that QQE values stay within reasonable range."""
        qqe = QQEMod()
        qqe_fast, qqe_slow, histogram = qqe.calculate(sample_data)
        
        # QQE values based on RSI should be roughly in 0-200 range
        # (RSI is 0-100, with ATR additions)
        assert qqe_fast.min() >= -50  # Allow some negative due to ATR
        assert qqe_fast.max() <= 250  # Allow some overshoot
        assert qqe_slow.min() >= -50
        assert qqe_slow.max() <= 250


class TestQQEModIntegration:
    """Integration tests for QQE MOD with real-world scenarios."""
    
    def test_sideways_market(self):
        """Test QQE in sideways market (should generate fewer signals)."""
        dates = pd.date_range('2024-01-01', periods=200, freq='15min')
        
        # Sideways market with noise
        price = 100 + np.random.randn(200) * 2
        close = pd.Series(price, index=dates)
        
        qqe = QQEMod()
        signal = qqe.get_signal(close)
        
        # Sideways market should have relatively few signals compared to trending
        # But with random noise, it can still generate some false signals
        signal_rate = (signal != 0).sum() / len(signal)
        assert signal_rate < 0.40, f"Too many signals in sideways market: {signal_rate:.2%}"
    
    def test_volatile_market(self):
        """Test QQE in volatile market."""
        dates = pd.date_range('2024-01-01', periods=200, freq='15T')
        
        # Volatile market
        price = 100 + np.cumsum(np.random.randn(200) * 5)
        close = pd.Series(price, index=dates)
        
        qqe = QQEMod()
        signal = qqe.get_signal(close)
        
        # Volatile market should generate signals
        assert (signal != 0).any()
    
    def test_real_world_pattern(self):
        """Test with real-world-like price pattern."""
        dates = pd.date_range('2024-01-01', periods=500, freq='15T')
        
        # Complex pattern: trend + cycle + noise
        t = np.linspace(0, 10, 500)
        trend = 0.5 * t
        cycle = 10 * np.sin(t)
        noise = np.random.randn(500) * 2
        
        price = 100 + trend + cycle + noise
        close = pd.Series(price, index=dates)
        
        qqe = QQEMod()
        qqe_fast, qqe_slow, histogram = qqe.calculate(close)
        signal = qqe.get_signal(close)
        
        # Should generate some signals
        assert (signal != 0).any()
        
        # Should have both bullish and bearish signals
        assert (signal == 1).any()
        assert (signal == -1).any()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])