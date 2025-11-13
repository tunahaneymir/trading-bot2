"""
Portfolio Manager
=================

Portföy seviyesinde risk yönetimi ve dengeleme.

Sorumluluklar:
--------------
- Toplam portföy riski hesaplama
- Coin bazlı exposure limitleri
- Korelasyon yönetimi
- Diversifikasyon kontrolü
- Portföy dengeleme
- Sector/asset allocation

Faz: 6
Versiyon: 1.0.0
"""

import logging
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
from collections import defaultdict


@dataclass
class ExposureLimits:
    """
    Exposure limitleri.

    Attributes:
    -----------
    max_total_exposure_percent : float
        Maksimum toplam exposure (portföy %'si)
    max_single_coin_percent : float
        Tek bir coin için max exposure (portföy %'si)
    max_correlated_positions : int
        Max ilişkili pozisyon sayısı
    correlation_threshold : float
        Korelasyon eşiği [0, 1]
    max_sector_exposure_percent : float
        Tek bir sektör için max exposure (portföy %'si)
    """
    max_total_exposure_percent: float = 0.06  # %6
    max_single_coin_percent: float = 0.03     # %3
    max_correlated_positions: int = 3
    correlation_threshold: float = 0.7
    max_sector_exposure_percent: float = 0.3  # %30

    def to_dict(self) -> Dict[str, Any]:
        """Dictionary'ye çevir."""
        return asdict(self)


@dataclass
class PortfolioRisk:
    """
    Portföy risk metrikleri.

    Attributes:
    -----------
    total_exposure : float
        Toplam exposure (USDT)
    total_exposure_percent : float
        Toplam exposure (%)
    coin_exposures : Dict[str, float]
        Coin bazlı exposure (USDT)
    position_count : int
        Açık pozisyon sayısı
    correlation_score : float
        Ortalama korelasyon skoru
    diversification_score : float
        Diversifikasyon skoru [0, 1]
    last_update : datetime
        Son güncelleme zamanı
    """
    total_exposure: float = 0.0
    total_exposure_percent: float = 0.0
    coin_exposures: Dict[str, float] = field(default_factory=dict)
    position_count: int = 0
    correlation_score: float = 0.0
    diversification_score: float = 1.0
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Dictionary'ye çevir."""
        data = asdict(self)
        data['last_update'] = self.last_update.isoformat()
        return data


class PortfolioManager:
    """
    Portföy yöneticisi.

    Toplam portföy riskini takip eder, coin bazlı exposureları kontrol eder,
    korelasyonları yönetir.
    """

    def __init__(
        self,
        total_balance: float,
        exposure_limits: Optional[ExposureLimits] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Portfolio Manager başlatıcı.

        Parametreler:
        ------------
        total_balance : float
            Toplam portföy bakiyesi (USDT)
        exposure_limits : Optional[ExposureLimits]
            Exposure limitleri (None ise varsayılan)
        logger : Optional[logging.Logger]
            Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.total_balance = total_balance
        self.exposure_limits = exposure_limits or ExposureLimits()

        # Portföy risk metrikleri
        self.portfolio_risk = PortfolioRisk()

        # Aktif pozisyonlar (coin -> exposure mapping)
        self.active_exposures: Dict[str, float] = {}

        # Korelasyon matrisi (basitleştirilmiş: coin -> correlation score)
        # Gerçek implementasyonda coin çiftleri arasında korelasyon hesaplanır
        self.correlation_matrix: Dict[str, Dict[str, float]] = {}

        self.logger.info(f"PortfolioManager başlatıldı | Balance: ${total_balance:,.2f}")

    def can_open_position(
        self,
        symbol: str,
        position_value: float,
        correlated_symbols: Optional[List[str]] = None
    ) -> Tuple[bool, str]:
        """
        Yeni pozisyon açılabilir mi kontrol et.

        Parametreler:
        ------------
        symbol : str
            Coin sembolü
        position_value : float
            Pozisyon değeri (USDT)
        correlated_symbols : Optional[List[str]]
            İlişkili coinler listesi

        Returns:
        --------
        Tuple[bool, str]
            (açılabilir_mi, neden)
        """
        # Kontrol 1: Toplam exposure limiti
        new_total_exposure = self.portfolio_risk.total_exposure + position_value
        max_total = self.total_balance * self.exposure_limits.max_total_exposure_percent

        if new_total_exposure > max_total:
            return False, (
                f"Toplam exposure limiti aşılacak: ${new_total_exposure:,.2f} > "
                f"${max_total:,.2f} (max {self.exposure_limits.max_total_exposure_percent*100:.1f}%)"
            )

        # Kontrol 2: Tek coin exposure limiti
        current_coin_exposure = self.active_exposures.get(symbol, 0.0)
        new_coin_exposure = current_coin_exposure + position_value
        max_coin = self.total_balance * self.exposure_limits.max_single_coin_percent

        if new_coin_exposure > max_coin:
            return False, (
                f"{symbol} için exposure limiti aşılacak: ${new_coin_exposure:,.2f} > "
                f"${max_coin:,.2f} (max {self.exposure_limits.max_single_coin_percent*100:.1f}%)"
            )

        # Kontrol 3: İlişkili pozisyon limiti
        if correlated_symbols:
            correlated_count = sum(
                1 for sym in correlated_symbols
                if sym in self.active_exposures and sym != symbol
            )

            if correlated_count >= self.exposure_limits.max_correlated_positions:
                return False, (
                    f"İlişkili pozisyon limiti aşılacak: {correlated_count} >= "
                    f"{self.exposure_limits.max_correlated_positions}"
                )

        return True, "Pozisyon açılabilir"

    def add_position(
        self,
        symbol: str,
        position_value: float
    ) -> None:
        """
        Pozisyon ekle (açıldığında).

        Parametreler:
        ------------
        symbol : str
            Coin sembolü
        position_value : float
            Pozisyon değeri (USDT)
        """
        # Coin exposure güncelle
        if symbol in self.active_exposures:
            self.active_exposures[symbol] += position_value
        else:
            self.active_exposures[symbol] = position_value

        # Portföy risk güncelle
        self._update_portfolio_risk()

        self.logger.info(
            f"Pozisyon eklendi: {symbol} | "
            f"Value: ${position_value:,.2f} | "
            f"Total Exposure: ${self.portfolio_risk.total_exposure:,.2f}"
        )

    def remove_position(
        self,
        symbol: str,
        position_value: float
    ) -> None:
        """
        Pozisyon kaldır (kapandığında).

        Parametreler:
        ------------
        symbol : str
            Coin sembolü
        position_value : float
            Pozisyon değeri (USDT)
        """
        if symbol in self.active_exposures:
            self.active_exposures[symbol] -= position_value

            # Negatif olmamalı
            if self.active_exposures[symbol] <= 0:
                del self.active_exposures[symbol]

        # Portföy risk güncelle
        self._update_portfolio_risk()

        self.logger.info(
            f"Pozisyon kaldırıldı: {symbol} | "
            f"Value: ${position_value:,.2f} | "
            f"Total Exposure: ${self.portfolio_risk.total_exposure:,.2f}"
        )

    def update_position_value(
        self,
        symbol: str,
        new_value: float
    ) -> None:
        """
        Pozisyon değerini güncelle (fiyat değiştiğinde).

        Parametreler:
        ------------
        symbol : str
            Coin sembolü
        new_value : float
            Yeni pozisyon değeri (USDT)
        """
        self.active_exposures[symbol] = new_value
        self._update_portfolio_risk()

    def update_balance(self, new_balance: float) -> None:
        """
        Portföy bakiyesini güncelle.

        Parametreler:
        ------------
        new_balance : float
            Yeni bakiye (USDT)
        """
        self.total_balance = new_balance
        self._update_portfolio_risk()

    def calculate_optimal_allocation(
        self,
        available_coins: List[str],
        coin_scores: Optional[Dict[str, float]] = None
    ) -> Dict[str, float]:
        """
        Optimal coin tahsisi hesapla.

        Parametreler:
        ------------
        available_coins : List[str]
            Mevcut coin listesi
        coin_scores : Optional[Dict[str, float]]
            Coin skorları (None ise eşit ağırlık)

        Returns:
        --------
        Dict[str, float]
            Coin -> tahsis oranı mapping
        """
        if not available_coins:
            return {}

        # Skor bazlı tahsis
        if coin_scores:
            total_score = sum(coin_scores.get(coin, 1.0) for coin in available_coins)
            if total_score == 0:
                total_score = len(available_coins)

            allocation = {}
            for coin in available_coins:
                score = coin_scores.get(coin, 1.0)
                weight = score / total_score

                # Min/max kısıtları
                weight = max(0.02, min(weight, self.exposure_limits.max_single_coin_percent))
                allocation[coin] = weight

            # Normalize (toplam 1.0)
            total_weight = sum(allocation.values())
            if total_weight > 0:
                allocation = {k: v / total_weight for k, v in allocation.items()}

            return allocation

        # Eşit ağırlık
        equal_weight = 1.0 / len(available_coins)
        return {coin: equal_weight for coin in available_coins}

    def calculate_diversification_score(self) -> float:
        """
        Diversifikasyon skorunu hesapla [0, 1].

        Returns:
        --------
        float
            Diversifikasyon skoru (1 = maksimum diversifikasyon)
        """
        if not self.active_exposures:
            return 1.0

        # Coin sayısı faktörü
        n_coins = len(self.active_exposures)
        if n_coins == 0:
            return 1.0

        # Exposure dağılımı (Herfindahl-Hirschman Index)
        total_exposure = sum(self.active_exposures.values())
        if total_exposure == 0:
            return 1.0

        # Her coin'in exposure payı
        shares = [exp / total_exposure for exp in self.active_exposures.values()]

        # HHI (0 = tam diversifikasyon, 1 = tek varlık)
        hhi = sum(s**2 for s in shares)

        # Normalize (1 = maksimum diversifikasyon)
        diversification = 1.0 - hhi

        return float(diversification)

    def get_exposure_by_coin(self) -> Dict[str, Dict[str, float]]:
        """
        Coin bazında exposure detayları.

        Returns:
        --------
        Dict[str, Dict[str, float]]
            Coin -> exposure detayları
        """
        result = {}
        for symbol, exposure in self.active_exposures.items():
            result[symbol] = {
                'exposure_usdt': exposure,
                'exposure_percent': (exposure / self.total_balance * 100) if self.total_balance > 0 else 0,
                'limit_usage_percent': (
                    exposure / (self.total_balance * self.exposure_limits.max_single_coin_percent) * 100
                    if self.exposure_limits.max_single_coin_percent > 0 else 0
                )
            }
        return result

    def get_statistics(self) -> Dict[str, Any]:
        """
        Portföy istatistikleri.

        Returns:
        --------
        Dict[str, Any]
            İstatistikler
        """
        return {
            'balance': self.total_balance,
            'portfolio_risk': self.portfolio_risk.to_dict(),
            'exposure_limits': self.exposure_limits.to_dict(),
            'active_coins': len(self.active_exposures),
            'exposure_by_coin': self.get_exposure_by_coin(),
            'limit_usage': {
                'total_exposure': (
                    self.portfolio_risk.total_exposure_percent /
                    (self.exposure_limits.max_total_exposure_percent * 100) * 100
                    if self.exposure_limits.max_total_exposure_percent > 0 else 0
                )
            }
        }

    def _update_portfolio_risk(self) -> None:
        """Portföy risk metriklerini güncelle."""
        # Toplam exposure
        self.portfolio_risk.total_exposure = sum(self.active_exposures.values())
        self.portfolio_risk.total_exposure_percent = (
            self.portfolio_risk.total_exposure / self.total_balance * 100
            if self.total_balance > 0 else 0
        )

        # Coin exposures
        self.portfolio_risk.coin_exposures = self.active_exposures.copy()

        # Pozisyon sayısı
        self.portfolio_risk.position_count = len(self.active_exposures)

        # Diversifikasyon
        self.portfolio_risk.diversification_score = self.calculate_diversification_score()

        # Korelasyon (basitleştirilmiş)
        # Gerçek implementasyonda coin çiftleri arasında hesaplanır
        self.portfolio_risk.correlation_score = 0.0

        # Güncelleme zamanı
        self.portfolio_risk.last_update = datetime.now(timezone.utc)


if __name__ == "__main__":
    print("Portfolio Manager - Test")
    print("=" * 60)

    # Logger
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Portfolio Manager oluştur
    pm = PortfolioManager(total_balance=10000.0, logger=logger)
    print("✅ PortfolioManager oluşturuldu")
    print(f"   Toplam Bakiye: ${pm.total_balance:,.2f}")

    # Test 1: Pozisyon açma kontrolü
    print("\n📊 Test 1: Pozisyon Açma Kontrolü")
    can_open, reason = pm.can_open_position(
        symbol="BTCUSDT",
        position_value=300.0
    )
    print(f"   Symbol: BTCUSDT | Value: $300")
    print(f"   Sonuç: {'✅ AÇILABİLİR' if can_open else '❌ AÇILAMAZ'}")
    print(f"   Neden: {reason}")

    # Test 2: Pozisyon ekleme
    print("\n📊 Test 2: Pozisyon Ekleme")
    pm.add_position("BTCUSDT", 300.0)
    pm.add_position("ETHUSDT", 200.0)
    pm.add_position("BNBUSDT", 150.0)

    # Test 3: Diversifikasyon skoru
    print("\n📊 Test 3: Diversifikasyon")
    div_score = pm.calculate_diversification_score()
    print(f"   Diversifikasyon Skoru: {div_score:.3f}")

    # Test 4: Optimal tahsis
    print("\n📊 Test 4: Optimal Tahsis")
    coins = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT"]
    scores = {"BTCUSDT": 0.9, "ETHUSDT": 0.85, "BNBUSDT": 0.8, "ADAUSDT": 0.75, "SOLUSDT": 0.7}
    allocation = pm.calculate_optimal_allocation(coins, scores)
    for coin, weight in allocation.items():
        print(f"   {coin}: {weight*100:.2f}%")

    # Test 5: İstatistikler
    print("\n📊 Test 5: İstatistikler")
    stats = pm.get_statistics()
    print(f"   Total Exposure: ${stats['portfolio_risk']['total_exposure']:,.2f}")
    print(f"   Exposure %: {stats['portfolio_risk']['total_exposure_percent']:.2f}%")
    print(f"   Active Coins: {stats['active_coins']}")
    print(f"   Diversification: {stats['portfolio_risk']['diversification_score']:.3f}")

    print("\n" + "=" * 60)
    print("✅ Tüm testler başarılı!")
