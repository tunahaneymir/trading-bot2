"""
Trading Bot - Coin Scoring System
===================================

Coin seçimi için composite scoring sistemi.
6 farklı metrik üzerinden 0-1 aralığında score hesaplar.

Metrikler:
    1. Liquidity Score: Hacim ve spread bazlı likidite
    2. Volatility Score: Optimal volatilite aralığı (1.5%-5%)
    3. Trend Strength Score: ADX ve trend clarity
    4. Momentum Score: RSI ve MACD bazlı momentum
    5. Volume Profile Score: Hacim profili sağlığı
    6. Correlation Score: Diğer coinlerle korelasyon (düşük tercih)

Author: Trading Bot Team
Version: 1.0 (Faz 4)
Python: 3.10+
"""

from typing import Dict, List, Tuple, Any
import numpy as np
from dataclasses import dataclass


@dataclass
class CoinScores:
    """Bir coin'in tüm skorlarını tutar."""
    symbol: str
    liquidity_score: float
    volatility_score: float
    trend_strength_score: float
    momentum_score: float
    volume_profile_score: float
    correlation_score: float
    final_score: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Dictionary'ye çevir."""
        return {
            'symbol': self.symbol,
            'liquidity_score': round(self.liquidity_score, 4),
            'volatility_score': round(self.volatility_score, 4),
            'trend_strength_score': round(self.trend_strength_score, 4),
            'momentum_score': round(self.momentum_score, 4),
            'volume_profile_score': round(self.volume_profile_score, 4),
            'correlation_score': round(self.correlation_score, 4),
            'final_score': round(self.final_score, 4),
        }


class CoinScorer:
    """
    Coin scoring sistemi.
    
    Composite scoring: 6 metriği ağırlıklı toplama göre birleştirir.
    """
    
    def __init__(
        self,
        weights: Dict[str, float] = None
    ):
        """
        Args:
            weights: Metrik ağırlıkları (toplam 1.0 olmalı)
        """
        # Default ağırlıklar (FAZ 4 gereksinimlerinden)
        self.weights = weights or {
            'liquidity': 0.25,
            'volatility': 0.20,
            'trend_strength': 0.20,
            'momentum': 0.15,
            'volume_profile': 0.10,
            'correlation': 0.10,
        }
        
        # Ağırlık toplamı kontrolü
        weight_sum = sum(self.weights.values())
        if not np.isclose(weight_sum, 1.0):
            raise ValueError(f"Ağırlık toplamı 1.0 olmalı, mevcut: {weight_sum}")
    
    # ==================== 1. LIQUIDITY SCORE ====================
    
    def calculate_liquidity_score(
        self,
        volume_24h: float,
        spread: float,
        orderbook_depth: float = None
    ) -> float:
        """
        Likidite skoru hesapla.
        
        Yüksek hacim + düşük spread = yüksek likidite
        
        Args:
            volume_24h: 24 saatlik hacim (USD)
            spread: Bid-ask spread (yüzde)
            orderbook_depth: Orderbook derinliği (opsiyonel)
            
        Returns:
            0-1 arası likidite skoru
        """
        # Hacim skoru (logaritmik scale)
        # $10M = 0.5, $100M = 0.8, $1B = 1.0
        volume_score = min(1.0, np.log10(volume_24h / 10_000_000) / 2.0) if volume_24h > 0 else 0
        volume_score = max(0, volume_score)
        
        # Spread skoru (düşük spread = yüksek skor)
        # %0.05 = 1.0, %0.10 = 0.5, %0.20 = 0
        spread_score = max(0, min(1.0, (0.20 - spread) / 0.15))
        
        # Orderbook depth skoru (opsiyonel)
        if orderbook_depth:
            depth_score = min(1.0, orderbook_depth / 1_000_000)  # $1M = 1.0
        else:
            depth_score = 0.5  # Nötr
        
        # Birleştir (hacim %50, spread %40, depth %10)
        liquidity_score = (
            volume_score * 0.50 +
            spread_score * 0.40 +
            depth_score * 0.10
        )
        
        return liquidity_score
    
    # ==================== 2. VOLATILITY SCORE ====================
    
    def calculate_volatility_score(
        self,
        volatility: float,
        optimal_min: float = 1.5,
        optimal_max: float = 5.0
    ) -> float:
        """
        Volatilite skoru hesapla.
        
        Optimal range içinde = yüksek skor
        Çok düşük veya çok yüksek = düşük skor
        
        Args:
            volatility: ATR bazlı volatilite (yüzde)
            optimal_min: Optimal minimum (%)
            optimal_max: Optimal maksimum (%)
            
        Returns:
            0-1 arası volatilite skoru
        """
        if volatility <= 0:
            return 0.0
        
        # Optimal range içindeyse 1.0
        if optimal_min <= volatility <= optimal_max:
            # Range içinde de gradyan olsun
            mid = (optimal_min + optimal_max) / 2
            distance_from_mid = abs(volatility - mid)
            range_width = (optimal_max - optimal_min) / 2
            return 1.0 - (distance_from_mid / range_width) * 0.2
        
        # Optimal range dışında - distance'a göre azalt
        if volatility < optimal_min:
            # Çok düşük volatilite
            return max(0, 1.0 - (optimal_min - volatility) / optimal_min)
        else:
            # Çok yüksek volatilite
            max_acceptable = optimal_max * 2  # 10%
            if volatility >= max_acceptable:
                return 0.0
            return max(0, 1.0 - (volatility - optimal_max) / (max_acceptable - optimal_max))
    
    # ==================== 3. TREND STRENGTH SCORE ====================
    
    def calculate_trend_strength_score(
        self,
        adx: float = None,
        trend_direction: int = 0,
        price_position: float = 0.5
    ) -> float:
        """
        Trend gücü skoru hesapla.
        
        Güçlü ve net trend = yüksek skor
        
        Args:
            adx: Average Directional Index (0-100)
            trend_direction: 1 (up), -1 (down), 0 (sideways)
            price_position: Fiyatın range içindeki pozisyonu (0-1)
            
        Returns:
            0-1 arası trend gücü skoru
        """
        # ADX skoru (25+ = strong trend)
        if adx is not None:
            adx_score = min(1.0, adx / 50.0)  # 50+ = 1.0
        else:
            adx_score = 0.5  # Nötr
        
        # Trend clarity (net trend = yüksek skor)
        clarity_score = 1.0 if abs(trend_direction) == 1 else 0.3
        
        # Position score (extreme değil = iyi)
        # 0.3-0.7 arası ideal (çok extreme değil)
        if 0.3 <= price_position <= 0.7:
            position_score = 1.0
        else:
            # Extreme pozisyonlarda düşür
            distance = min(abs(price_position - 0.3), abs(price_position - 0.7))
            position_score = max(0.5, 1.0 - distance)
        
        # Birleştir
        trend_score = (
            adx_score * 0.50 +
            clarity_score * 0.30 +
            position_score * 0.20
        )
        
        return trend_score
    
    # ==================== 4. MOMENTUM SCORE ====================
    
    def calculate_momentum_score(
        self,
        rsi: float = None,
        macd_histogram: float = None,
        price_change_24h: float = None
    ) -> float:
        """
        Momentum skoru hesapla.
        
        Güçlü ve sürdürülebilir momentum = yüksek skor
        
        Args:
            rsi: Relative Strength Index (0-100)
            macd_histogram: MACD histogram değeri
            price_change_24h: 24 saatlik fiyat değişimi (%)
            
        Returns:
            0-1 arası momentum skoru
        """
        # RSI skoru (40-60 ideal, extreme'ler düşük)
        if rsi is not None:
            if 40 <= rsi <= 60:
                rsi_score = 1.0
            elif rsi < 40:
                # Oversold - düşük skor
                rsi_score = max(0.3, rsi / 40)
            else:
                # Overbought - düşük skor
                rsi_score = max(0.3, (100 - rsi) / 40)
        else:
            rsi_score = 0.5  # Nötr
        
        # MACD skoru (pozitif ve artan = iyi)
        if macd_histogram is not None:
            # Normalize et
            macd_score = 1.0 / (1.0 + np.exp(-macd_histogram))  # Sigmoid
        else:
            macd_score = 0.5  # Nötr
        
        # Price change skoru (2-8% günlük değişim ideal)
        if price_change_24h is not None:
            abs_change = abs(price_change_24h)
            if 2 <= abs_change <= 8:
                price_score = 1.0
            elif abs_change < 2:
                # Çok az hareket
                price_score = max(0.4, abs_change / 2)
            else:
                # Çok fazla hareket
                price_score = max(0.3, 1.0 - (abs_change - 8) / 12)
        else:
            price_score = 0.5  # Nötr
        
        # Birleştir
        momentum_score = (
            rsi_score * 0.40 +
            macd_score * 0.35 +
            price_score * 0.25
        )
        
        return momentum_score
    
    # ==================== 5. VOLUME PROFILE SCORE ====================
    
    def calculate_volume_profile_score(
        self,
        volume_24h: float,
        volume_7d_avg: float = None,
        volume_trend: str = 'stable'
    ) -> float:
        """
        Hacim profili skoru hesapla.
        
        Dengeli ve artan hacim = yüksek skor
        
        Args:
            volume_24h: 24 saatlik hacim
            volume_7d_avg: 7 günlük ortalama hacim
            volume_trend: 'increasing', 'decreasing', 'stable'
            
        Returns:
            0-1 arası hacim profili skoru
        """
        # Volume consistency (24h vs 7d avg)
        if volume_7d_avg and volume_7d_avg > 0:
            ratio = volume_24h / volume_7d_avg
            # 0.8-1.5 arası ideal (stabil veya hafif artan)
            if 0.8 <= ratio <= 1.5:
                consistency_score = 1.0
            elif ratio < 0.8:
                # Düşüş
                consistency_score = max(0.3, ratio / 0.8)
            else:
                # Çok fazla artış (spike - şüpheli)
                consistency_score = max(0.5, 1.0 - (ratio - 1.5) / 2)
        else:
            consistency_score = 0.5  # Nötr
        
        # Volume trend skoru
        trend_scores = {
            'increasing': 0.9,  # Artan hacim iyi
            'stable': 0.7,      # Stabil hacim kabul edilebilir
            'decreasing': 0.3   # Azalan hacim kötü
        }
        trend_score = trend_scores.get(volume_trend, 0.5)
        
        # Birleştir
        volume_profile_score = (
            consistency_score * 0.60 +
            trend_score * 0.40
        )
        
        return volume_profile_score
    
    # ==================== 6. CORRELATION SCORE ====================
    
    def calculate_correlation_score(
        self,
        correlations: List[float]
    ) -> float:
        """
        Korelasyon skoru hesapla.
        
        Düşük korelasyon = yüksek skor (diversifikasyon için)
        
        Args:
            correlations: Diğer selected coinlerle korelasyon değerleri
            
        Returns:
            0-1 arası korelasyon skoru
        """
        if not correlations:
            return 1.0  # İlk coin, korelasyon yok
        
        # Ortalama korelasyon al
        avg_correlation = np.mean([abs(c) for c in correlations])
        
        # Düşük korelasyon = yüksek skor
        # <0.3 = excellent (1.0)
        # 0.3-0.5 = good (0.8)
        # 0.5-0.7 = acceptable (0.5)
        # >0.7 = poor (0.2)
        
        if avg_correlation < 0.3:
            score = 1.0
        elif avg_correlation < 0.5:
            score = 0.8
        elif avg_correlation < 0.7:
            score = 0.5
        else:
            score = max(0.1, 1.0 - (avg_correlation - 0.7) / 0.3)
        
        return score
    
    # ==================== COMPOSITE SCORE ====================
    
    def calculate_composite_score(
        self,
        liquidity_score: float,
        volatility_score: float,
        trend_strength_score: float,
        momentum_score: float,
        volume_profile_score: float,
        correlation_score: float
    ) -> float:
        """
        Composite (final) score hesapla.
        
        Tüm skorları ağırlıklı toplamla birleştirir.
        
        Returns:
            0-1 arası final skor
        """
        composite = (
            liquidity_score * self.weights['liquidity'] +
            volatility_score * self.weights['volatility'] +
            trend_strength_score * self.weights['trend_strength'] +
            momentum_score * self.weights['momentum'] +
            volume_profile_score * self.weights['volume_profile'] +
            correlation_score * self.weights['correlation']
        )
        
        return min(1.0, max(0.0, composite))
    
    def score_coin(
        self,
        symbol: str,
        metrics: Dict[str, Any],
        correlations: List[float] = None
    ) -> CoinScores:
        """
        Bir coin için tüm skorları hesapla.
        
        Args:
            symbol: Coin sembolü
            metrics: Metrik dictionary'si
            correlations: Korelasyon değerleri
            
        Returns:
            CoinScores object
        """
        # Her bir skoru hesapla
        liquidity_score = self.calculate_liquidity_score(
            metrics.get('volume_24h', 0),
            metrics.get('spread', 0),
            metrics.get('orderbook_depth')
        )
        
        volatility_score = self.calculate_volatility_score(
            metrics.get('volatility', 0)
        )
        
        trend_strength_score = self.calculate_trend_strength_score(
            metrics.get('adx'),
            metrics.get('trend_direction', 0),
            metrics.get('price_position', 0.5)
        )
        
        momentum_score = self.calculate_momentum_score(
            metrics.get('rsi'),
            metrics.get('macd_histogram'),
            metrics.get('price_change_24h')
        )
        
        volume_profile_score = self.calculate_volume_profile_score(
            metrics.get('volume_24h', 0),
            metrics.get('volume_7d_avg'),
            metrics.get('volume_trend', 'stable')
        )
        
        correlation_score = self.calculate_correlation_score(
            correlations or []
        )
        
        # Final score
        final_score = self.calculate_composite_score(
            liquidity_score,
            volatility_score,
            trend_strength_score,
            momentum_score,
            volume_profile_score,
            correlation_score
        )
        
        return CoinScores(
            symbol=symbol,
            liquidity_score=liquidity_score,
            volatility_score=volatility_score,
            trend_strength_score=trend_strength_score,
            momentum_score=momentum_score,
            volume_profile_score=volume_profile_score,
            correlation_score=correlation_score,
            final_score=final_score
        )


if __name__ == "__main__":
    # Test
    print("🧪 Coin Scoring Test")
    print("-" * 50)
    
    scorer = CoinScorer()
    
    # Test coin metrikleri
    metrics = {
        'volume_24h': 150_000_000,  # $150M
        'spread': 0.08,              # %0.08
        'volatility': 3.5,           # %3.5 ATR
        'adx': 35,
        'trend_direction': 1,
        'price_position': 0.6,
        'rsi': 55,
        'macd_histogram': 0.5,
        'price_change_24h': 4.2,
        'volume_7d_avg': 140_000_000,
        'volume_trend': 'increasing'
    }
    
    scores = scorer.score_coin('BTCUSDT', metrics, correlations=[])
    
    print(f"Symbol: {scores.symbol}")
    print(f"Liquidity: {scores.liquidity_score:.4f}")
    print(f"Volatility: {scores.volatility_score:.4f}")
    print(f"Trend Strength: {scores.trend_strength_score:.4f}")
    print(f"Momentum: {scores.momentum_score:.4f}")
    print(f"Volume Profile: {scores.volume_profile_score:.4f}")
    print(f"Correlation: {scores.correlation_score:.4f}")
    print(f"🎯 Final Score: {scores.final_score:.4f}")
    
    print("\n🎉 Scoring test tamamlandı!")