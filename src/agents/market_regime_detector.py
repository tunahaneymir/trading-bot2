"""
Trading Bot - Market Regime Detector
=====================================

Piyasa rejimini tespit eden sistem.
Bull, Bear, Sideways durumlarını belirler.

Rejim Tipleri:
    - BULL: Yükseliş trendi (bullish)
    - BEAR: Düşüş trendi (bearish)
    - SIDEWAYS: Yatay trend (ranging)
    - VOLATILE: Yüksek volatilite (choppy)

Kullanılan Metrikler:
    - Moving averages (20, 50, 200 EMA)
    - Trend pattern (higher highs/lows)
    - Volatility (ATR)
    - Volume trend
    - Market breadth (optional)

Author: Trading Bot Team
Version: 1.0 (Faz 4)
Python: 3.10+
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import numpy as np


class MarketRegime(Enum):
    """Piyasa rejim tipleri."""
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


@dataclass
class RegimeMetrics:
    """Rejim belirleme için metrikler."""
    regime: MarketRegime
    confidence: float  # 0-1 arası güven
    trend_strength: float  # -1 (strong bear) to +1 (strong bull)
    volatility_level: float  # 0-1 arası
    volume_trend: str  # 'increasing', 'decreasing', 'stable'
    
    # Ek bilgiler
    price_above_ma20: bool
    price_above_ma50: bool
    price_above_ma200: bool
    higher_highs: bool
    higher_lows: bool
    
    def to_dict(self) -> Dict:
        """Dictionary'ye çevir."""
        return {
            'regime': self.regime.value,
            'confidence': round(self.confidence, 4),
            'trend_strength': round(self.trend_strength, 4),
            'volatility_level': round(self.volatility_level, 4),
            'volume_trend': self.volume_trend,
            'price_above_ma20': self.price_above_ma20,
            'price_above_ma50': self.price_above_ma50,
            'price_above_ma200': self.price_above_ma200,
            'higher_highs': self.higher_highs,
            'higher_lows': self.higher_lows,
        }


class MarketRegimeDetector:
    """
    Piyasa rejimi dedektörü.
    
    Multiple metriği birleştirerek market rejimini belirler.
    """
    
    def __init__(self):
        """Initialize detector."""
        # Volatility thresholds (ATR bazlı, yüzde olarak)
        self.low_volatility_threshold = 0.015   # %1.5
        self.high_volatility_threshold = 0.05   # %5
        
        # Trend thresholds
        self.strong_trend_threshold = 0.6       # 0-1 arası
        
    # ==================== HELPER FUNCTIONS ====================
    
    def _calculate_ema(self, prices: List[float], period: int) -> float:
        """
        EMA hesapla (basit).
        
        Args:
            prices: Fiyat listesi (son price en sonda)
            period: EMA periyodu
            
        Returns:
            EMA değeri
        """
        if len(prices) < period:
            return np.mean(prices) if prices else 0
        
        # Multiplier
        multiplier = 2 / (period + 1)
        
        # İlk EMA = SMA
        ema = np.mean(prices[:period])
        
        # EMA hesapla
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def _detect_higher_highs(self, highs: List[float], lookback: int = 10) -> bool:
        """
        Higher highs pattern tespit et.
        
        Args:
            highs: Yüksek fiyatlar
            lookback: Geri bakılacak periyot
            
        Returns:
            Higher highs var mı
        """
        if len(highs) < lookback + 1:
            return False
        
        recent_highs = highs[-lookback:]
        # Son N barın yükseklerinin genelde artan olup olmadığını kontrol et
        increasing_count = sum(1 for i in range(1, len(recent_highs)) 
                              if recent_highs[i] > recent_highs[i-1])
        
        return increasing_count / (len(recent_highs) - 1) > 0.6
    
    def _detect_higher_lows(self, lows: List[float], lookback: int = 10) -> bool:
        """
        Higher lows pattern tespit et.
        
        Args:
            lows: Düşük fiyatlar
            lookback: Geri bakılacak periyot
            
        Returns:
            Higher lows var mı
        """
        if len(lows) < lookback + 1:
            return False
        
        recent_lows = lows[-lookback:]
        # Son N barın düşüklerinin genelde artan olup olmadığını kontrol et
        increasing_count = sum(1 for i in range(1, len(recent_lows)) 
                              if recent_lows[i] > recent_lows[i-1])
        
        return increasing_count / (len(recent_lows) - 1) > 0.6
    
    def _calculate_trend_strength(
        self,
        price: float,
        ma20: float,
        ma50: float,
        ma200: float
    ) -> float:
        """
        Trend gücünü hesapla (-1 to +1).
        
        Args:
            price: Güncel fiyat
            ma20, ma50, ma200: Moving averages
            
        Returns:
            Trend strength (-1 = strong bear, +1 = strong bull)
        """
        # MA'ların sıralamasını kontrol et
        ma_order_score = 0
        
        # Bull için: price > ma20 > ma50 > ma200
        # Bear için: price < ma20 < ma50 < ma200
        
        if price > ma20:
            ma_order_score += 0.25
        if ma20 > ma50:
            ma_order_score += 0.25
        if ma50 > ma200:
            ma_order_score += 0.25
        
        # Price distance from MAs
        if ma200 > 0:
            distance_from_ma200 = (price - ma200) / ma200
            # +10% = +0.25, -10% = -0.25
            distance_score = max(-0.25, min(0.25, distance_from_ma200 / 0.10 * 0.25))
            ma_order_score += distance_score
        
        # Normalize to -1 to +1
        trend_strength = (ma_order_score - 0.5) * 2
        
        return max(-1.0, min(1.0, trend_strength))
    
    def _calculate_volatility_level(self, atr: float, price: float) -> float:
        """
        Volatilite seviyesini 0-1 arası normalize et.
        
        Args:
            atr: Average True Range
            price: Güncel fiyat
            
        Returns:
            Normalized volatility (0 = low, 1 = very high)
        """
        if price == 0:
            return 0.5
        
        atr_percentage = atr / price
        
        # Normalize: %1.5 = 0, %5+ = 1
        volatility_level = (atr_percentage - self.low_volatility_threshold) / \
                          (self.high_volatility_threshold - self.low_volatility_threshold)
        
        return max(0.0, min(1.0, volatility_level))
    
    def _detect_volume_trend(self, volumes: List[float], lookback: int = 20) -> str:
        """
        Hacim trendini tespit et.
        
        Args:
            volumes: Hacim listesi
            lookback: Geri bakılacak periyot
            
        Returns:
            'increasing', 'decreasing', 'stable'
        """
        if len(volumes) < lookback:
            return 'stable'
        
        recent_volumes = volumes[-lookback:]
        first_half = recent_volumes[:lookback//2]
        second_half = recent_volumes[lookback//2:]
        
        first_avg = np.mean(first_half)
        second_avg = np.mean(second_half)
        
        if first_avg == 0:
            return 'stable'
        
        change = (second_avg - first_avg) / first_avg
        
        if change > 0.15:  # %15+ artış
            return 'increasing'
        elif change < -0.15:  # %15+ azalış
            return 'decreasing'
        else:
            return 'stable'
    
    # ==================== MAIN DETECTION ====================
    
    def detect_regime(
        self,
        prices: List[float],
        highs: List[float],
        lows: List[float],
        volumes: List[float],
        atr: float = None
    ) -> RegimeMetrics:
        """
        Market rejimini tespit et.
        
        Args:
            prices: Kapanış fiyatları (son fiyat en sonda)
            highs: Yüksek fiyatlar
            lows: Düşük fiyatlar
            volumes: Hacimler
            atr: Average True Range (opsiyonel)
            
        Returns:
            RegimeMetrics object
        """
        if len(prices) < 20:
            return RegimeMetrics(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                trend_strength=0.0,
                volatility_level=0.5,
                volume_trend='stable',
                price_above_ma20=False,
                price_above_ma50=False,
                price_above_ma200=False,
                higher_highs=False,
                higher_lows=False,
            )
        
        # Current price
        current_price = prices[-1]
        
        # Calculate MAs
        ma20 = self._calculate_ema(prices, 20)
        ma50 = self._calculate_ema(prices, 50) if len(prices) >= 50 else ma20
        ma200 = self._calculate_ema(prices, 200) if len(prices) >= 200 else ma50
        
        # MA positions
        price_above_ma20 = current_price > ma20
        price_above_ma50 = current_price > ma50
        price_above_ma200 = current_price > ma200
        
        # Pattern detection
        higher_highs = self._detect_higher_highs(highs)
        higher_lows = self._detect_higher_lows(lows)
        
        # Trend strength
        trend_strength = self._calculate_trend_strength(
            current_price, ma20, ma50, ma200
        )
        
        # Volatility
        if atr is None:
            # Calculate simple ATR if not provided
            if len(highs) >= 14 and len(lows) >= 14:
                true_ranges = [highs[i] - lows[i] for i in range(-14, 0)]
                atr = np.mean(true_ranges)
            else:
                atr = (max(prices[-14:]) - min(prices[-14:])) / 14 if len(prices) >= 14 else 0
        
        volatility_level = self._calculate_volatility_level(atr, current_price)
        
        # Volume trend
        volume_trend = self._detect_volume_trend(volumes)
        
        # ========== REGIME DETERMINATION ==========
        
        regime = MarketRegime.UNKNOWN
        confidence = 0.0
        
        # BULL: Positive trend, higher highs, higher lows
        if (trend_strength > 0.3 and higher_highs and higher_lows and 
            price_above_ma20 and price_above_ma50):
            regime = MarketRegime.BULL
            confidence = min(1.0, (trend_strength + 0.3) * 1.2)
        
        # BEAR: Negative trend, lower lows
        elif (trend_strength < -0.3 and not higher_highs and not higher_lows and
              not price_above_ma20 and not price_above_ma50):
            regime = MarketRegime.BEAR
            confidence = min(1.0, (abs(trend_strength) + 0.3) * 1.2)
        
        # VOLATILE: High volatility, no clear trend
        elif volatility_level > 0.7:
            regime = MarketRegime.VOLATILE
            confidence = volatility_level
        
        # SIDEWAYS: Low/medium volatility, no strong trend
        elif abs(trend_strength) < 0.3 and volatility_level < 0.5:
            regime = MarketRegime.SIDEWAYS
            confidence = 1.0 - abs(trend_strength) / 0.3
        
        # Mixed signals - default to sideways with low confidence
        else:
            regime = MarketRegime.SIDEWAYS
            confidence = 0.4
        
        return RegimeMetrics(
            regime=regime,
            confidence=confidence,
            trend_strength=trend_strength,
            volatility_level=volatility_level,
            volume_trend=volume_trend,
            price_above_ma20=price_above_ma20,
            price_above_ma50=price_above_ma50,
            price_above_ma200=price_above_ma200,
            higher_highs=higher_highs,
            higher_lows=higher_lows,
        )
    
    def get_regime_weights(self, regime: MarketRegime) -> Dict[str, float]:
        """
        Rejime göre metrik ağırlıklarını döndür.
        
        Coin selection'da kullanılmak üzere.
        
        Args:
            regime: Market rejimi
            
        Returns:
            Metrik ağırlıkları
        """
        weights = {
            MarketRegime.BULL: {
                'liquidity': 0.20,
                'volatility': 0.15,
                'trend_strength': 0.35,  # Bull'da trend önemli
                'momentum': 0.20,
                'volume_profile': 0.05,
                'correlation': 0.05,
            },
            MarketRegime.BEAR: {
                'liquidity': 0.30,      # Bear'de likidite önemli
                'volatility': 0.25,      # Volatilite kontrolü önemli
                'trend_strength': 0.20,
                'momentum': 0.10,
                'volume_profile': 0.05,
                'correlation': 0.10,     # Diversifikasyon önemli
            },
            MarketRegime.SIDEWAYS: {
                'liquidity': 0.25,
                'volatility': 0.20,
                'trend_strength': 0.10,   # Sideways'de trend az önemli
                'momentum': 0.30,         # Momentum daha önemli
                'volume_profile': 0.10,
                'correlation': 0.05,
            },
            MarketRegime.VOLATILE: {
                'liquidity': 0.35,        # Volatil piyasada likidite çok önemli
                'volatility': 0.25,
                'trend_strength': 0.05,
                'momentum': 0.15,
                'volume_profile': 0.10,
                'correlation': 0.10,
            },
        }
        
        return weights.get(regime, weights[MarketRegime.SIDEWAYS])


if __name__ == "__main__":
    # Test
    print("🧪 Market Regime Detector Test")
    print("-" * 50)
    
    detector = MarketRegimeDetector()
    
    # Test 1: Bull market (yükseliş trendi)
    print("\n📈 Test 1: Bull Market")
    bull_prices = [100 + i * 0.5 for i in range(100)]  # Artan
    bull_highs = [p + 1 for p in bull_prices]
    bull_lows = [p - 1 for p in bull_prices]
    bull_volumes = [1000000 + i * 1000 for i in range(100)]
    
    regime = detector.detect_regime(bull_prices, bull_highs, bull_lows, bull_volumes)
    print(f"Regime: {regime.regime.value}")
    print(f"Confidence: {regime.confidence:.2%}")
    print(f"Trend Strength: {regime.trend_strength:.2f}")
    print(f"Volatility: {regime.volatility_level:.2f}")
    
    # Test 2: Bear market (düşüş trendi)
    print("\n📉 Test 2: Bear Market")
    bear_prices = [100 - i * 0.5 for i in range(100)]  # Azalan
    bear_highs = [p + 1 for p in bear_prices]
    bear_lows = [p - 1 for p in bear_prices]
    bear_volumes = [1000000] * 100
    
    regime = detector.detect_regime(bear_prices, bear_highs, bear_lows, bear_volumes)
    print(f"Regime: {regime.regime.value}")
    print(f"Confidence: {regime.confidence:.2%}")
    print(f"Trend Strength: {regime.trend_strength:.2f}")
    
    # Test 3: Sideways (yatay)
    print("\n↔️  Test 3: Sideways Market")
    sideways_prices = [100 + (i % 10 - 5) * 0.2 for i in range(100)]  # Yatay
    sideways_highs = [p + 0.5 for p in sideways_prices]
    sideways_lows = [p - 0.5 for p in sideways_prices]
    sideways_volumes = [1000000] * 100
    
    regime = detector.detect_regime(sideways_prices, sideways_highs, sideways_lows, sideways_volumes)
    print(f"Regime: {regime.regime.value}")
    print(f"Confidence: {regime.confidence:.2%}")
    print(f"Trend Strength: {regime.trend_strength:.2f}")
    
    # Regime weights
    print("\n⚖️  Regime-based Weights:")
    for regime_type in [MarketRegime.BULL, MarketRegime.BEAR, MarketRegime.SIDEWAYS]:
        weights = detector.get_regime_weights(regime_type)
        print(f"\n{regime_type.value.upper()}:")
        for metric, weight in weights.items():
            print(f"  {metric}: {weight:.2f}")
    
    print("\n🎉 Regime detector test tamamlandı!")