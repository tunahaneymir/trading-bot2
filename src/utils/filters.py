"""
Trading Bot - Coin Filtering System
====================================

Coin selection için filtreleme sistemi.
Likidite, volatilite, spread gibi kriterlere göre filtreler.

Filtre Kategorileri:
    1. Likidite Filtreleri: Minimum hacim, spread
    2. Volatilite Filtreleri: Min/max ATR
    3. Teknik Filtreler: Trend, momentum
    4. Risk Filtreleri: Korelasyon, drawdown

Author: Trading Bot Team
Version: 1.0 (Faz 4)
Python: 3.10+
"""

from typing import List, Dict, Any, Callable
from dataclasses import dataclass


@dataclass
class FilterConfig:
    """Filtre konfigürasyonu."""
    # Likidite
    min_volume_24h: float = 10_000_000  # $10M
    max_spread: float = 0.002           # %0.2
    
    # Volatilite
    min_volatility: float = 0.015       # %1.5
    max_volatility: float = 0.20        # %20
    
    # Teknik
    min_adx: float = None               # Optional
    min_rsi: float = None               # Optional
    max_rsi: float = None               # Optional
    
    # Risk
    max_correlation: float = 0.85       # Diğer coinlerle max korelasyon


class CoinFilter:
    """
    Coin filtreleme sistemi.
    
    Çeşitli kriterlere göre coin'leri filtreler.
    """
    
    def __init__(self, config: FilterConfig = None):
        """
        Args:
            config: Filtre konfigürasyonu
        """
        self.config = config or FilterConfig()
        self.filter_stats = {
            'total_checked': 0,
            'passed': 0,
            'failed_volume': 0,
            'failed_spread': 0,
            'failed_volatility': 0,
            'failed_technical': 0,
            'failed_risk': 0,
        }
    
    # ==================== BASIC FILTERS ====================
    
    def filter_by_volume(self, coins: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Hacim filtreleme.
        
        Args:
            coins: Coin listesi (her biri volume_24h içermeli)
            
        Returns:
            Filtrelenmiş coin listesi
        """
        filtered = []
        for coin in coins:
            volume = coin.get('volume_24h', 0)
            if volume >= self.config.min_volume_24h:
                filtered.append(coin)
            else:
                self.filter_stats['failed_volume'] += 1
        
        return filtered
    
    def filter_by_spread(self, coins: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Spread filtreleme.
        
        Args:
            coins: Coin listesi (her biri spread içermeli)
            
        Returns:
            Filtrelenmiş coin listesi
        """
        filtered = []
        for coin in coins:
            spread = coin.get('spread', float('inf'))
            if spread <= self.config.max_spread:
                filtered.append(coin)
            else:
                self.filter_stats['failed_spread'] += 1
        
        return filtered
    
    def filter_by_volatility(self, coins: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Volatilite filtreleme.
        
        Args:
            coins: Coin listesi (her biri volatility içermeli)
            
        Returns:
            Filtrelenmiş coin listesi
        """
        filtered = []
        for coin in coins:
            volatility = coin.get('volatility', 0)
            if self.config.min_volatility <= volatility <= self.config.max_volatility:
                filtered.append(coin)
            else:
                self.filter_stats['failed_volatility'] += 1
        
        return filtered
    
    # ==================== TECHNICAL FILTERS ====================
    
    def filter_by_adx(self, coins: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        ADX (trend gücü) filtreleme.
        
        Args:
            coins: Coin listesi
            
        Returns:
            Filtrelenmiş coin listesi
        """
        if self.config.min_adx is None:
            return coins
        
        filtered = []
        for coin in coins:
            adx = coin.get('adx', 0)
            if adx >= self.config.min_adx:
                filtered.append(coin)
            else:
                self.filter_stats['failed_technical'] += 1
        
        return filtered
    
    def filter_by_rsi(self, coins: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        RSI filtreleme (extreme değerleri filtrele).
        
        Args:
            coins: Coin listesi
            
        Returns:
            Filtrelenmiş coin listesi
        """
        if self.config.min_rsi is None and self.config.max_rsi is None:
            return coins
        
        filtered = []
        for coin in coins:
            rsi = coin.get('rsi', 50)
            
            passes = True
            if self.config.min_rsi is not None and rsi < self.config.min_rsi:
                passes = False
            if self.config.max_rsi is not None and rsi > self.config.max_rsi:
                passes = False
            
            if passes:
                filtered.append(coin)
            else:
                self.filter_stats['failed_technical'] += 1
        
        return filtered
    
    # ==================== RISK FILTERS ====================
    
    def filter_by_correlation(
        self,
        coins: List[Dict[str, Any]],
        selected_symbols: List[str],
        correlation_matrix: Dict[str, Dict[str, float]] = None
    ) -> List[Dict[str, Any]]:
        """
        Korelasyon filtreleme.
        
        Zaten seçili coinlerle yüksek korelasyonlu olanları filtrele.
        
        Args:
            coins: Coin listesi
            selected_symbols: Zaten seçili coin sembolleri
            correlation_matrix: Korelasyon matrisi
            
        Returns:
            Filtrelenmiş coin listesi
        """
        if not selected_symbols or not correlation_matrix:
            return coins
        
        filtered = []
        for coin in coins:
            symbol = coin.get('symbol')
            if not symbol:
                continue
            
            # Bu coin'in seçili coinlerle korelasyonunu kontrol et
            max_corr = 0
            for selected in selected_symbols:
                if selected in correlation_matrix.get(symbol, {}):
                    corr = abs(correlation_matrix[symbol][selected])
                    max_corr = max(max_corr, corr)
            
            if max_corr <= self.config.max_correlation:
                filtered.append(coin)
            else:
                self.filter_stats['failed_risk'] += 1
        
        return filtered
    
    # ==================== COMPOSITE FILTER ====================
    
    def apply_all_filters(
        self,
        coins: List[Dict[str, Any]],
        selected_symbols: List[str] = None,
        correlation_matrix: Dict[str, Dict[str, float]] = None
    ) -> List[Dict[str, Any]]:
        """
        Tüm filtreleri sırayla uygula.
        
        Args:
            coins: Coin listesi
            selected_symbols: Seçili coinler (korelasyon için)
            correlation_matrix: Korelasyon matrisi
            
        Returns:
            Tüm filtreleri geçen coin listesi
        """
        self.filter_stats['total_checked'] = len(coins)
        
        # Sırayla filtrele
        filtered = coins
        
        # 1. Likidite filtreleri
        filtered = self.filter_by_volume(filtered)
        filtered = self.filter_by_spread(filtered)
        
        # 2. Volatilite filtresi
        filtered = self.filter_by_volatility(filtered)
        
        # 3. Teknik filtreler
        filtered = self.filter_by_adx(filtered)
        filtered = self.filter_by_rsi(filtered)
        
        # 4. Risk filtreleri
        if selected_symbols:
            filtered = self.filter_by_correlation(
                filtered, selected_symbols, correlation_matrix
            )
        
        self.filter_stats['passed'] = len(filtered)
        
        return filtered
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Filtre istatistiklerini döndür.
        
        Returns:
            İstatistik dictionary
        """
        total = self.filter_stats['total_checked']
        passed = self.filter_stats['passed']
        
        stats = {
            'total_checked': total,
            'passed': passed,
            'failed': total - passed,
            'pass_rate': round(passed / total * 100, 2) if total > 0 else 0,
            'failures': {
                'volume': self.filter_stats['failed_volume'],
                'spread': self.filter_stats['failed_spread'],
                'volatility': self.filter_stats['failed_volatility'],
                'technical': self.filter_stats['failed_technical'],
                'risk': self.filter_stats['failed_risk'],
            }
        }
        
        return stats
    
    def reset_statistics(self):
        """İstatistikleri sıfırla."""
        for key in self.filter_stats:
            self.filter_stats[key] = 0


# ==================== HELPER FUNCTIONS ====================

def create_default_filter() -> CoinFilter:
    """
    Default konfigürasyonla filtre oluştur (FAZ 4 gereksinimleri).
    
    Returns:
        CoinFilter instance
    """
    config = FilterConfig(
        min_volume_24h=10_000_000,  # $10M
        max_spread=0.002,            # %0.2
        min_volatility=0.015,        # %1.5
        max_volatility=0.20,         # %20
    )
    return CoinFilter(config)


def create_strict_filter() -> CoinFilter:
    """
    Strict (katı) filtre oluştur.
    
    Returns:
        CoinFilter instance
    """
    config = FilterConfig(
        min_volume_24h=50_000_000,  # $50M
        max_spread=0.001,            # %0.1
        min_volatility=0.02,         # %2
        max_volatility=0.15,         # %15
        min_adx=25,                  # Strong trend
        max_correlation=0.70,        # Düşük korelasyon
    )
    return CoinFilter(config)


def create_relaxed_filter() -> CoinFilter:
    """
    Relaxed (gevşek) filtre oluştur.
    
    Returns:
        CoinFilter instance
    """
    config = FilterConfig(
        min_volume_24h=5_000_000,   # $5M
        max_spread=0.003,            # %0.3
        min_volatility=0.01,         # %1
        max_volatility=0.25,         # %25
    )
    return CoinFilter(config)


if __name__ == "__main__":
    # Test
    print("🧪 Coin Filter Test")
    print("-" * 50)
    
    # Test data
    test_coins = [
        {
            'symbol': 'BTCUSDT',
            'volume_24h': 150_000_000,
            'spread': 0.0015,
            'volatility': 0.035,
            'adx': 35,
            'rsi': 55,
        },
        {
            'symbol': 'SHIBALOWVOL',
            'volume_24h': 2_000_000,  # Çok düşük
            'spread': 0.0025,
            'volatility': 0.008,      # Çok düşük
            'adx': 15,
            'rsi': 50,
        },
        {
            'symbol': 'EXTREMECOIN',
            'volume_24h': 20_000_000,
            'spread': 0.005,          # Çok yüksek
            'volatility': 0.35,       # Çok yüksek
            'adx': 40,
            'rsi': 90,                # Çok yüksek
        },
    ]
    
    # Default filter
    coin_filter = create_default_filter()
    filtered = coin_filter.apply_all_filters(test_coins)
    
    print(f"Toplam coin: {len(test_coins)}")
    print(f"Filtrelendi: {len(filtered)}")
    print(f"\nGeçen coinler:")
    for coin in filtered:
        print(f"  - {coin['symbol']}")
    
    print(f"\nİstatistikler:")
    stats = coin_filter.get_statistics()
    print(f"  Pass rate: {stats['pass_rate']}%")
    print(f"  Failures: {stats['failures']}")
    
    print("\n🎉 Filter test tamamlandı!")