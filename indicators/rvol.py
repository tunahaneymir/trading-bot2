"""
RVOL (Relative Volume)
======================

Volume confirmation indicator that compares current volume to historical average.

Formula:
1. Current volume = volume[0]
2. Average volume = mean(volume[-lookback:])
3. RVOL = current_volume / avg_volume
4. Signal = 1 if rvol > threshold else 0

High RVOL (> 1.5-2.0) indicates strong momentum and reduces false signals.
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class RVOL:
    """
    Relative Volume indicator implementation.
    
    RVOL measures current volume relative to historical average to confirm
    the strength of price movements.
    """
    
    def __init__(
        self,
        lookback: int = 20,
        threshold: float = 1.5
    ):
        """
        Initialize RVOL.
        
        Args:
            lookback: Number of periods for average volume calculation
            threshold: RVOL threshold for signal generation (typically 1.2-2.5)
        """
        self.lookback = lookback
        self.threshold = threshold
        
        # Minimum data requirement
        self.min_periods = lookback + 1
    
    def calculate(
        self,
        volume: pd.Series
    ) -> pd.Series:
        """
        Calculate RVOL.
        
        Args:
            volume: Volume series
        
        Returns:
            RVOL values (current volume / average volume)
            
        Raises:
            ValueError: If insufficient data or invalid values
        """
        # Validate data length
        if len(volume) < self.min_periods:
            raise ValueError(
                f"Insufficient data. Need at least {self.min_periods} candles, got {len(volume)}"
            )
        
        # Check for negative volumes
        if (volume < 0).any():
            raise ValueError("Volume contains negative values")
        
        # Check for NaN or inf
        if volume.isna().any():
            raise ValueError("Volume contains NaN values")
        if np.isinf(volume).any():
            raise ValueError("Volume contains infinite values")
        
        try:
            # Calculate rolling average volume
            avg_volume = volume.rolling(window=self.lookback, min_periods=1).mean()
            
            # Avoid division by zero
            avg_volume = avg_volume.replace(0, np.nan)
            
            # Calculate RVOL
            rvol = volume / avg_volume
            
            # Fill NaN with 0
            rvol = rvol.fillna(0)
            
            return rvol
            
        except Exception as e:
            logger.error(f"RVOL calculation failed: {e}")
            raise
    
    def get_signal(
        self,
        volume: pd.Series
    ) -> pd.Series:
        """
        Get RVOL signals.
        
        Args:
            volume: Volume series
        
        Returns:
            Signal series:
            - 1 (high volume, RVOL > threshold)
            - 0 (normal/low volume)
        """
        rvol = self.calculate(volume)
        
        # Generate signal based on threshold
        signal = (rvol > self.threshold).astype(int)
        
        return signal
    
    def get_current_state(
        self,
        volume: pd.Series
    ) -> dict:
        """
        Get current RVOL state for the latest candle.
        
        Args:
            volume: Volume series
            
        Returns:
            Dictionary with current state:
            {
                'rvol': float,
                'current_volume': float,
                'avg_volume': float,
                'signal': int (0 or 1),
                'high_volume': bool,
                'strength': str ('low', 'normal', 'high', 'very_high')
            }
        """
        rvol = self.calculate(volume)
        signal = self.get_signal(volume)
        
        # Get latest values
        latest_rvol = rvol.iloc[-1]
        latest_signal = signal.iloc[-1]
        current_volume = volume.iloc[-1]
        
        # Calculate average volume
        avg_volume = volume.iloc[-self.lookback:].mean()
        
        # Determine strength
        if latest_rvol < 0.8:
            strength = 'low'
        elif latest_rvol < 1.2:
            strength = 'normal'
        elif latest_rvol < 2.0:
            strength = 'high'
        else:
            strength = 'very_high'
        
        return {
            'rvol': float(latest_rvol),
            'current_volume': float(current_volume),
            'avg_volume': float(avg_volume),
            'signal': int(latest_signal),
            'high_volume': latest_rvol > self.threshold,
            'strength': strength,
            'threshold': self.threshold
        }
    
    def get_volume_profile(
        self,
        volume: pd.Series,
        bins: int = 10
    ) -> dict:
        """
        Get volume distribution profile.
        
        Args:
            volume: Volume series
            bins: Number of bins for histogram
            
        Returns:
            Dictionary with volume profile:
            {
                'histogram': numpy array,
                'bin_edges': numpy array,
                'percentile_50': float,
                'percentile_75': float,
                'percentile_95': float
            }
        """
        hist, bin_edges = np.histogram(volume, bins=bins)
        
        return {
            'histogram': hist,
            'bin_edges': bin_edges,
            'percentile_50': volume.quantile(0.50),
            'percentile_75': volume.quantile(0.75),
            'percentile_95': volume.quantile(0.95),
            'mean': volume.mean(),
            'median': volume.median()
        }


# Helper functions
def rvol(
    volume: pd.Series,
    lookback: int = 20,
    threshold: float = 1.5
) -> pd.Series:
    """
    Convenience function for RVOL calculation.
    
    Args:
        volume: Volume series
        lookback: Lookback period
        threshold: Signal threshold
    
    Returns:
        RVOL values
    """
    rvol_indicator = RVOL(lookback, threshold)
    return rvol_indicator.calculate(volume)


def rvol_signal(
    volume: pd.Series,
    lookback: int = 20,
    threshold: float = 1.5
) -> pd.Series:
    """
    Convenience function to get RVOL signals directly.
    
    Args:
        volume: Volume series
        lookback: Lookback period
        threshold: Signal threshold
    
    Returns:
        Signal series (0 or 1)
    """
    rvol_indicator = RVOL(lookback, threshold)
    return rvol_indicator.get_signal(volume)


if __name__ == "__main__":
    # Example usage
    import matplotlib.pyplot as plt
    
    # Generate sample data
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=200, freq='15min')
    
    # Simulated volume data with spikes
    base_volume = 1000000
    volume_data = []
    
    for i in range(200):
        # Base volume with random noise
        vol = base_volume * (1 + np.random.randn() * 0.3)
        
        # Add occasional volume spikes (high RVOL events)
        if np.random.rand() > 0.90:  # 10% chance of spike
            vol *= np.random.uniform(2.0, 4.0)
        
        volume_data.append(max(0, vol))  # Ensure non-negative
    
    volume = pd.Series(volume_data, index=dates)
    
    # Calculate RVOL
    rvol_indicator = RVOL(lookback=20, threshold=1.5)
    rvol_values = rvol_indicator.calculate(volume)
    signal = rvol_indicator.get_signal(volume)
    
    # Get current state
    state = rvol_indicator.get_current_state(volume)
    
    # Get volume profile
    profile = rvol_indicator.get_volume_profile(volume)
    
    print("RVOL Indicator Test")
    print("=" * 50)
    print(f"\nCurrent State:")
    print(f"  RVOL:           {state['rvol']:.2f}")
    print(f"  Current Volume: {state['current_volume']:,.0f}")
    print(f"  Avg Volume:     {state['avg_volume']:,.0f}")
    print(f"  Signal:         {state['signal']}")
    print(f"  High Volume:    {state['high_volume']}")
    print(f"  Strength:       {state['strength']}")
    print(f"  Threshold:      {state['threshold']}")
    
    print(f"\nVolume Profile:")
    print(f"  Mean:           {profile['mean']:,.0f}")
    print(f"  Median:         {profile['median']:,.0f}")
    print(f"  50th percentile: {profile['percentile_50']:,.0f}")
    print(f"  75th percentile: {profile['percentile_75']:,.0f}")
    print(f"  95th percentile: {profile['percentile_95']:,.0f}")
    
    print(f"\nSignal Statistics:")
    print(f"  High volume periods: {signal.sum()} ({signal.sum()/len(signal)*100:.1f}%)")
    print(f"  Normal periods:      {(signal == 0).sum()} ({(signal == 0).sum()/len(signal)*100:.1f}%)")
    
    # Plot
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10))
    
    # Volume bars
    colors = ['red' if s == 1 else 'blue' for s in signal]
    ax1.bar(volume.index, volume.values, color=colors, alpha=0.6, label='Volume')
    ax1.axhline(y=state['avg_volume'], color='green', linestyle='--', 
                linewidth=2, label=f"Avg Volume: {state['avg_volume']:,.0f}")
    ax1.set_ylabel('Volume')
    ax1.set_title('RVOL Indicator Example')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.ticklabel_format(style='plain', axis='y')
    
    # RVOL line
    ax2.plot(rvol_values.index, rvol_values.values, linewidth=2, label='RVOL')
    ax2.axhline(y=rvol_indicator.threshold, color='red', linestyle='--', 
                linewidth=2, label=f'Threshold: {rvol_indicator.threshold}')
    ax2.axhline(y=1.0, color='gray', linestyle='-', linewidth=0.5, alpha=0.5)
    ax2.fill_between(rvol_values.index, rvol_indicator.threshold, 
                      rvol_values.values, where=(rvol_values > rvol_indicator.threshold),
                      alpha=0.3, color='red', label='High Volume Zone')
    ax2.set_ylabel('RVOL')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Signal markers
    ax3.bar(signal.index, signal.values, color='red', alpha=0.6)
    ax3.set_ylabel('Signal')
    ax3.set_xlabel('Date')
    ax3.set_title('High Volume Signals')
    ax3.set_ylim(-0.1, 1.5)
    ax3.grid(True, alpha=0.3)
    
    import os

    output_dir = os.path.join(os.path.dirname(__file__), "..", "outputs")
    os.makedirs(output_dir, exist_ok=True)

    save_path = os.path.join(output_dir, "rvol_example.png")

    plt.savefig(save_path, dpi=150)
    print(f"✅ Plot saved to: {os.path.abspath(save_path)}")
