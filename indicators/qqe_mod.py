"""
QQE MOD (Quantum Qualitative Estimation Modified)
=================================================

Momentum ve trend detection için RSI bazlı indicator.

References:
- TradingView QQE MOD indicator
- Original QQE by Glaz

Formula:
1. RSI hesapla (period=14)
2. RSI'yi EMA ile smoothing (period=5)
3. RSI ATR hesapla
4. QQE fast = RSI_smooth + (multiplier * RSI_ATR)
5. QQE slow = EMA(QQE_fast, period=5)
6. Signal = 1 if fast > slow else -1
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class InsufficientDataError(Exception):
    """Raised when there's not enough data for indicator calculation."""
    pass


class QQEMod:
    """
    QQE MOD indicator implementation.
    
    QQE MOD combines RSI with ATR-based smoothing to generate
    momentum signals with reduced noise.
    """
    
    def __init__(
        self,
        rsi_period: int = 14,
        rsi_smoothing: int = 5,
        qqe_factor: float = 4.236,
        signal_smoothing: int = 5
    ):
        """
        Initialize QQE MOD.
        
        Args:
            rsi_period: RSI calculation period
            rsi_smoothing: EMA smoothing for RSI
            qqe_factor: QQE multiplier factor
            signal_smoothing: Signal line smoothing
        """
        self.rsi_period = rsi_period
        self.rsi_smoothing = rsi_smoothing
        self.qqe_factor = qqe_factor
        self.signal_smoothing = signal_smoothing
        
        # Minimum data requirement
        self.min_periods = self.rsi_period + self.rsi_smoothing + self.signal_smoothing + 10
    
    def _calculate_rsi(self, close: pd.Series) -> pd.Series:
        """
        Calculate RSI.
        
        Args:
            close: Close prices
            
        Returns:
            RSI values (0-100)
        """
        # Calculate price changes
        delta = close.diff()
        
        # Separate gains and losses
        gains = delta.where(delta > 0, 0)
        losses = -delta.where(delta < 0, 0)
        
        # Calculate average gains and losses using EMA
        avg_gains = gains.ewm(span=self.rsi_period, adjust=False).mean()
        avg_losses = losses.ewm(span=self.rsi_period, adjust=False).mean()
        
        # Calculate RS and RSI
        rs = avg_gains / avg_losses
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_ema(self, series: pd.Series, period: int) -> pd.Series:
        """
        Calculate EMA.
        
        Args:
            series: Input series
            period: EMA period
            
        Returns:
            EMA values
        """
        return series.ewm(span=period, adjust=False).mean()
    
    def _calculate_atr(self, series: pd.Series, period: int) -> pd.Series:
        """
        Calculate ATR on a series (for RSI).
        
        Args:
            series: Input series (RSI in this case)
            period: ATR period
            
        Returns:
            ATR values
        """
        # For RSI, we calculate the range between consecutive values
        high_low = series.diff().abs()
        
        # Calculate ATR using EMA
        atr = high_low.ewm(span=period, adjust=False).mean()
        
        return atr
    
    def calculate(
        self,
        close: pd.Series
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate QQE MOD indicator.
        
        Args:
            close: Close prices (pandas Series)
        
        Returns:
            Tuple of (qqe_fast, qqe_slow, histogram)
            
        Raises:
            InsufficientDataError: If insufficient data
            ValueError: If invalid data (NaN, inf)
        """
        # Validate data length
        if len(close) < self.min_periods:
            raise InsufficientDataError(
                f"Insufficient data. Need at least {self.min_periods} candles, got {len(close)}"
            )
        
        # Check for NaN or inf
        if close.isna().any():
            raise ValueError("Close prices contain NaN values")
        if np.isinf(close).any():
            raise ValueError("Close prices contain infinite values")
        
        try:
            # 1. Calculate RSI
            rsi = self._calculate_rsi(close)
            
            # 2. Smooth RSI with EMA
            rsi_smooth = self._calculate_ema(rsi, self.rsi_smoothing)
            
            # 3. Calculate RSI ATR
            rsi_atr = self._calculate_atr(rsi_smooth, self.rsi_period)
            
            # 4. Calculate QQE fast
            qqe_fast = rsi_smooth + (self.qqe_factor * rsi_atr)
            
            # 5. Calculate QQE slow (signal line)
            qqe_slow = self._calculate_ema(qqe_fast, self.signal_smoothing)
            
            # 6. Calculate histogram
            histogram = qqe_fast - qqe_slow
            
            # Fill initial NaN values with 0
            qqe_fast = qqe_fast.fillna(0)
            qqe_slow = qqe_slow.fillna(0)
            histogram = histogram.fillna(0)
            
            return qqe_fast, qqe_slow, histogram
            
        except Exception as e:
            logger.error(f"QQE MOD calculation failed: {e}")
            raise
    
    def get_signal(
        self,
        close: pd.Series
    ) -> pd.Series:
        """
        Get trading signals (-1, 0, 1).
        
        Args:
            close: Close prices
        
        Returns:
            Signal series: 
            - 1 (bullish cross - fast crosses above slow)
            - -1 (bearish cross - fast crosses below slow)
            - 0 (no signal)
        """
        qqe_fast, qqe_slow, _ = self.calculate(close)
        
        # Detect crosses
        prev_diff = (qqe_fast - qqe_slow).shift(1)
        curr_diff = qqe_fast - qqe_slow
        
        # Bullish cross: was negative, now positive
        bullish = (prev_diff < 0) & (curr_diff > 0)
        
        # Bearish cross: was positive, now negative
        bearish = (prev_diff > 0) & (curr_diff < 0)
        
        # Create signal series
        signal = pd.Series(0, index=close.index)
        signal[bullish] = 1
        signal[bearish] = -1
        
        return signal
    
    def get_current_state(
        self,
        close: pd.Series
    ) -> dict:
        """
        Get current QQE state for the latest candle.
        
        Args:
            close: Close prices
            
        Returns:
            Dictionary with current state:
            {
                'qqe_fast': float,
                'qqe_slow': float,
                'histogram': float,
                'signal': int (-1, 0, 1),
                'bullish': bool,
                'bearish': bool
            }
        """
        qqe_fast, qqe_slow, histogram = self.calculate(close)
        signal = self.get_signal(close)
        
        # Get latest values
        latest_fast = qqe_fast.iloc[-1]
        latest_slow = qqe_slow.iloc[-1]
        latest_hist = histogram.iloc[-1]
        latest_signal = signal.iloc[-1]
        
        return {
            'qqe_fast': float(latest_fast),
            'qqe_slow': float(latest_slow),
            'histogram': float(latest_hist),
            'signal': int(latest_signal),
            'bullish': latest_fast > latest_slow,
            'bearish': latest_fast < latest_slow,
            'strength': abs(float(latest_hist))  # Signal strength
        }


# Helper function
def qqe_mod(
    close: pd.Series,
    rsi_period: int = 14,
    rsi_smoothing: int = 5,
    qqe_factor: float = 4.236,
    signal_smoothing: int = 5
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Convenience function for QQE MOD.
    
    Args:
        close: Close prices
        rsi_period: RSI period
        rsi_smoothing: RSI smoothing period
        qqe_factor: QQE multiplier
        signal_smoothing: Signal line smoothing
    
    Returns:
        Tuple of (qqe_fast, qqe_slow, histogram)
    """
    qqe = QQEMod(rsi_period, rsi_smoothing, qqe_factor, signal_smoothing)
    return qqe.calculate(close)


def qqe_signal(
    close: pd.Series,
    rsi_period: int = 14,
    rsi_smoothing: int = 5,
    qqe_factor: float = 4.236,
    signal_smoothing: int = 5
) -> pd.Series:
    """
    Convenience function to get QQE signals directly.
    
    Args:
        close: Close prices
        rsi_period: RSI period
        rsi_smoothing: RSI smoothing period
        qqe_factor: QQE multiplier
        signal_smoothing: Signal line smoothing
    
    Returns:
        Signal series (-1, 0, 1)
    """
    qqe = QQEMod(rsi_period, rsi_smoothing, qqe_factor, signal_smoothing)
    return qqe.get_signal(close)


if __name__ == "__main__":
    # Example usage
    import matplotlib.pyplot as plt
    
    # Generate sample data
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=200, freq='15T')
    
    # Simulated price data with trend
    price = 100 + np.cumsum(np.random.randn(200) * 2)
    close = pd.Series(price, index=dates)
    
    # Calculate QQE MOD
    qqe = QQEMod()
    qqe_fast, qqe_slow, histogram = qqe.calculate(close)
    signal = qqe.get_signal(close)
    
    # Get current state
    state = qqe.get_current_state(close)
    
    print("QQE MOD Indicator Test")
    print("=" * 50)
    print(f"\nCurrent State:")
    print(f"  QQE Fast:  {state['qqe_fast']:.2f}")
    print(f"  QQE Slow:  {state['qqe_slow']:.2f}")
    print(f"  Histogram: {state['histogram']:.2f}")
    print(f"  Signal:    {state['signal']}")
    print(f"  Bullish:   {state['bullish']}")
    print(f"  Strength:  {state['strength']:.2f}")
    
    print(f"\nSignal Count:")
    print(f"  Bullish signals:  {(signal == 1).sum()}")
    print(f"  Bearish signals:  {(signal == -1).sum()}")
    print(f"  Neutral periods:  {(signal == 0).sum()}")
    
    # Plot
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10))
    
    # Price
    ax1.plot(close.index, close.values, label='Close Price', linewidth=2)
    ax1.set_ylabel('Price')
    ax1.set_title('QQE MOD Indicator Example')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # QQE Lines
    ax2.plot(qqe_fast.index, qqe_fast.values, label='QQE Fast', linewidth=2)
    ax2.plot(qqe_slow.index, qqe_slow.values, label='QQE Slow', linewidth=2)
    ax2.set_ylabel('QQE Value')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Histogram and signals
    ax3.bar(histogram.index, histogram.values, label='Histogram', alpha=0.6)
    
    # Mark bullish signals
    bullish_idx = signal[signal == 1].index
    ax3.scatter(bullish_idx, [histogram[idx] for idx in bullish_idx], 
                color='green', s=100, marker='^', label='Bullish', zorder=5)
    
    # Mark bearish signals
    bearish_idx = signal[signal == -1].index
    ax3.scatter(bearish_idx, [histogram[idx] for idx in bearish_idx], 
                color='red', s=100, marker='v', label='Bearish', zorder=5)
    
    ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax3.set_xlabel('Date')
    ax3.set_ylabel('Histogram')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    import os

    # "outputs" klasörü yoksa oluştur
    output_dir = os.path.join(os.path.dirname(__file__), "..", "outputs")
    os.makedirs(output_dir, exist_ok=True)

    # Kaydetme yolunu oluştur
    save_path = os.path.join(output_dir, "qqe_mod_example.png")

    # Grafiği kaydet
    plt.savefig(save_path, dpi=150)
    print(f"✅ Plot saved to: {os.path.abspath(save_path)}")
