"""
MOST Indicator Demo
====================

Interactive demo showing MOST indicator with different parameters and MA types.
Demonstrates trend detection and signal generation.

Usage:
    python demo_most.py
"""

import numpy as np
import matplotlib.pyplot as plt
from most import calculate_most, get_most_signal, most_with_signal


def generate_sample_data(n_points: int = 200, seed: int = 42) -> np.ndarray:
    """
    Generate realistic sample price data with trend changes.
    
    Parameters:
    -----------
    n_points : int
        Number of data points to generate
    seed : int
        Random seed for reproducibility
        
    Returns:
    --------
    np.ndarray
        Simulated price data
    """
    np.random.seed(seed)
    
    # Create a price series with multiple trend phases
    price = 100.0
    prices = [price]
    
    # Phase 1: Uptrend
    for _ in range(n_points // 4):
        price += np.random.randn() * 0.5 + 0.3
        prices.append(price)
    
    # Phase 2: Ranging
    for _ in range(n_points // 4):
        price += np.random.randn() * 0.8
        prices.append(price)
    
    # Phase 3: Downtrend
    for _ in range(n_points // 4):
        price += np.random.randn() * 0.5 - 0.3
        prices.append(price)
    
    # Phase 4: Recovery
    for _ in range(n_points // 4):
        price += np.random.randn() * 0.6 + 0.2
        prices.append(price)
    
    return np.array(prices[:n_points])


def demo_basic_usage():
    """Demo 1: Basic MOST calculation and usage."""
    print("\n" + "="*70)
    print("DEMO 1: Basic MOST Usage")
    print("="*70)
    
    # Generate sample data
    close = generate_sample_data(n_points=100, seed=42)
    
    # Calculate MOST with VAR
    most_line, trend, signal = most_with_signal(
        close, 
        length=9, 
        percent=2.0, 
        ma_type="VAR"
    )
    
    print(f"\n📊 Data Summary:")
    print(f"   Total bars: {len(close)}")
    print(f"   Price range: ${close.min():.2f} - ${close.max():.2f}")
    print(f"   Current price: ${close[-1]:.2f}")
    
    print(f"\n📈 MOST Indicator:")
    print(f"   MOST value: ${most_line[-1]:.2f}")
    print(f"   Trend: {'Uptrend' if trend[-1] == 1 else 'Downtrend'}")
    print(f"   Signal: {signal}")
    
    # Count trend changes
    trend_changes = np.sum(np.diff(trend) != 0)
    uptrend_bars = np.sum(trend == 1)
    downtrend_bars = np.sum(trend == -1)
    
    print(f"\n📊 Statistics:")
    print(f"   Trend changes: {trend_changes}")
    print(f"   Uptrend bars: {uptrend_bars} ({uptrend_bars/len(trend)*100:.1f}%)")
    print(f"   Downtrend bars: {downtrend_bars} ({downtrend_bars/len(trend)*100:.1f}%)")


def demo_ma_types_comparison():
    """Demo 2: Compare different MA types."""
    print("\n" + "="*70)
    print("DEMO 2: MA Types Comparison")
    print("="*70)
    
    close = generate_sample_data(n_points=150, seed=42)
    
    ma_types = ["VAR", "EMA", "HULL", "T3"]
    
    print(f"\n🔍 Comparing {len(ma_types)} MA types with same data:")
    print(f"   Parameters: length=9, percent=2.0")
    print(f"   Data points: {len(close)}")
    
    results = {}
    
    for ma_type in ma_types:
        most_line, trend, signal = most_with_signal(
            close, 
            length=9, 
            percent=2.0, 
            ma_type=ma_type
        )
        
        trend_changes = np.sum(np.diff(trend) != 0)
        uptrend_pct = np.sum(trend == 1) / len(trend) * 100
        
        results[ma_type] = {
            'trend_changes': trend_changes,
            'uptrend_pct': uptrend_pct,
            'current_trend': trend[-1],
            'signal': signal
        }
        
        print(f"\n   {ma_type:6s}: {trend_changes:2d} changes | "
              f"{uptrend_pct:5.1f}% up | "
              f"{'🟢 UP' if trend[-1] == 1 else '🔴 DOWN'} | "
              f"{signal}")


def demo_parameter_sensitivity():
    """Demo 3: Test different parameters."""
    print("\n" + "="*70)
    print("DEMO 3: Parameter Sensitivity")
    print("="*70)
    
    close = generate_sample_data(n_points=100, seed=42)
    
    print(f"\n🔧 Testing different stop loss percentages:")
    print(f"   MA Type: VAR, Length: 9")
    
    percentages = [1.0, 2.0, 3.0, 5.0]
    
    for percent in percentages:
        most_line, trend, signal = most_with_signal(
            close, 
            length=9, 
            percent=percent, 
            ma_type="VAR"
        )
        
        trend_changes = np.sum(np.diff(trend) != 0)
        uptrend_pct = np.sum(trend == 1) / len(trend) * 100
        
        print(f"\n   {percent:.1f}%: {trend_changes:2d} changes | "
              f"{uptrend_pct:5.1f}% uptrend | "
              f"{'🟢 UP' if trend[-1] == 1 else '🔴 DOWN'}")
    
    print(f"\n💡 Observation:")
    print(f"   Lower % = tighter stop = more trend changes")
    print(f"   Higher % = wider stop = fewer trend changes")


def demo_signal_generation():
    """Demo 4: Signal generation in action."""
    print("\n" + "="*70)
    print("DEMO 4: Trading Signal Generation")
    print("="*70)
    
    close = generate_sample_data(n_points=100, seed=123)
    
    most_line, trend = calculate_most(close, length=9, percent=2.0, ma_type="VAR")
    
    # Find all signals
    buy_signals = []
    sell_signals = []
    
    for i in range(1, len(trend)):
        if trend[i] == 1 and trend[i-1] == -1:
            buy_signals.append((i, close[i]))
        elif trend[i] == -1 and trend[i-1] == 1:
            sell_signals.append((i, close[i]))
    
    print(f"\n📊 Signal Analysis:")
    print(f"   Total bars: {len(close)}")
    print(f"   Buy signals: {len(buy_signals)}")
    print(f"   Sell signals: {len(sell_signals)}")
    
    if buy_signals:
        print(f"\n   🟢 Buy Signals:")
        for idx, price in buy_signals[:5]:  # Show first 5
            print(f"      Bar {idx}: ${price:.2f}")
        if len(buy_signals) > 5:
            print(f"      ... and {len(buy_signals)-5} more")
    
    if sell_signals:
        print(f"\n   🔴 Sell Signals:")
        for idx, price in sell_signals[:5]:  # Show first 5
            print(f"      Bar {idx}: ${price:.2f}")
        if len(sell_signals) > 5:
            print(f"      ... and {len(sell_signals)-5} more")


def demo_visualization():
    """Demo 5: Create visualization of MOST indicator."""
    print("\n" + "="*70)
    print("DEMO 5: Visualization")
    print("="*70)
    
    try:
        close = generate_sample_data(n_points=150, seed=42)
        
        # Calculate MOST
        most_line, trend = calculate_most(
            close, 
            length=9, 
            percent=2.0, 
            ma_type="VAR"
        )
        
        # Create figure
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), 
                                       gridspec_kw={'height_ratios': [3, 1]})
        
        # Plot 1: Price and MOST
        ax1.plot(close, label='Price', linewidth=1.5, color='black', alpha=0.7)
        ax1.plot(most_line, label='MOST Line', linewidth=2, color='blue')
        
        # Color background based on trend
        uptrend = trend == 1
        downtrend = trend == -1
        
        ax1.fill_between(range(len(close)), close.min(), close.max(), 
                         where=uptrend, alpha=0.1, color='green', 
                         label='Uptrend')
        ax1.fill_between(range(len(close)), close.min(), close.max(), 
                         where=downtrend, alpha=0.1, color='red', 
                         label='Downtrend')
        
        # Mark signals
        for i in range(1, len(trend)):
            if trend[i] == 1 and trend[i-1] == -1:  # Buy signal
                ax1.scatter(i, close[i], color='green', marker='^', 
                           s=100, zorder=5, label='Buy' if i == 1 else '')
            elif trend[i] == -1 and trend[i-1] == 1:  # Sell signal
                ax1.scatter(i, close[i], color='red', marker='v', 
                           s=100, zorder=5, label='Sell' if i == 1 else '')
        
        ax1.set_title('MOST Indicator (Moving Stop Loss)', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Price', fontsize=12)
        ax1.legend(loc='best', fontsize=10)
        ax1.grid(True, alpha=0.3)
        
        # Plot 2: Trend direction
        ax2.fill_between(range(len(trend)), 0, trend, 
                         where=(trend == 1), color='green', alpha=0.3, 
                         label='Uptrend')
        ax2.fill_between(range(len(trend)), trend, 0, 
                         where=(trend == -1), color='red', alpha=0.3, 
                         label='Downtrend')
        ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax2.set_ylabel('Trend', fontsize=12)
        ax2.set_xlabel('Bar Index', fontsize=12)
        ax2.set_ylim(-1.5, 1.5)
        ax2.set_yticks([-1, 0, 1])
        ax2.set_yticklabels(['Downtrend', 'Neutral', 'Uptrend'])
        ax2.legend(loc='best', fontsize=10)
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # Save figure
        output_path = '/mnt/user-data/outputs/most_indicator_demo.png'
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"\n   ✅ Visualization saved!")
        print(f"   📁 Location: {output_path}")
        
        plt.close()
        
    except Exception as e:
        print(f"\n   ⚠️  Visualization skipped: {e}")
        print(f"   (matplotlib may not be available in this environment)")


def main():
    """Run all demos."""
    print("\n" + "="*70)
    print("🚀 MOST INDICATOR - COMPREHENSIVE DEMO")
    print("="*70)
    print("\nMOST (Moving Stop Loss) is a trend-following indicator that:")
    print("  • Uses adaptive moving averages (VAR, EMA, HULL, T3)")
    print("  • Tracks trend direction with percentage-based stop loss")
    print("  • Generates buy/sell signals on trend changes")
    print("  • Works well in trending markets")
    
    # Run demos
    demo_basic_usage()
    demo_ma_types_comparison()
    demo_parameter_sensitivity()
    demo_signal_generation()
    demo_visualization()
    
    print("\n" + "="*70)
    print("✅ DEMO COMPLETE!")
    print("="*70)
    print("\n💡 Key Takeaways:")
    print("   1. VAR is adaptive - changes smoothing based on momentum")
    print("   2. Lower stop % = more sensitive, more signals")
    print("   3. Different MA types suit different market conditions")
    print("   4. Best used with other indicators for confirmation")
    print("\n📚 Next Steps:")
    print("   • Backtest with historical data")
    print("   • Combine with other indicators (RSI, MACD)")
    print("   • Optimize parameters for your strategy")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()