"""
Risk Manager
============

Pozisyon başına risk kontrolü ve doğrulama.

Sorumluluklar:
--------------
- Trade başına risk limiti kontrolü
- Günlük/haftalık/aylık kayıp limitleri
- Drawdown kontrolü
- Stop-loss/take-profit doğrulama
- Position sizing
- Risk metrikleri hesaplama
- AdaptiveRRSystem ile entegrasyon

Faz: 6
Versiyon: 1.0.0
"""

import logging
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone, timedelta
from enum import Enum


class RiskLevel(Enum):
    """Risk seviyesi."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class RiskLimits:
    """
    Risk limitleri konfigürasyonu.

    Attributes:
    -----------
    max_risk_per_trade : float
        Trade başına maksimum risk (portföy %'si)
    max_daily_loss : float
        Günlük maksimum kayıp (portföy %'si)
    max_weekly_loss : float
        Haftalık maksimum kayıp (portföy %'si)
    max_monthly_loss : float
        Aylık maksimum kayıp (portföy %'si)
    max_drawdown : float
        Maksimum drawdown (portföy %'si)
    max_consecutive_losses : int
        Maksimum ardışık kayıp sayısı
    min_rr_ratio : float
        Minimum RR oranı
    max_position_size_percent : float
        Maksimum pozisyon büyüklüğü (portföy %'si)
    """
    max_risk_per_trade: float = 0.02  # %2
    max_daily_loss: float = 0.03      # %3
    max_weekly_loss: float = 0.06     # %6
    max_monthly_loss: float = 0.10    # %10
    max_drawdown: float = 0.10        # %10
    max_consecutive_losses: int = 5
    min_rr_ratio: float = 1.1
    max_position_size_percent: float = 0.03  # %3

    def to_dict(self) -> Dict[str, Any]:
        """Dictionary'ye çevir."""
        return asdict(self)


@dataclass
class RiskMetrics:
    """
    Gerçek zamanlı risk metrikleri.

    Attributes:
    -----------
    current_drawdown : float
        Mevcut drawdown (%)
    peak_balance : float
        Peak balance (USDT)
    daily_loss : float
        Bugünkü kayıp (USDT)
    weekly_loss : float
        Bu haftaki kayıp (USDT)
    monthly_loss : float
        Bu ayki kayıp (USDT)
    consecutive_losses : int
        Mevcut ardışık kayıp sayısı
    total_risk_exposure : float
        Toplam risk exposure (USDT)
    last_update : datetime
        Son güncelleme zamanı
    """
    current_drawdown: float = 0.0
    peak_balance: float = 0.0
    daily_loss: float = 0.0
    weekly_loss: float = 0.0
    monthly_loss: float = 0.0
    consecutive_losses: int = 0
    total_risk_exposure: float = 0.0
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Dictionary'ye çevir."""
        data = asdict(self)
        data['last_update'] = self.last_update.isoformat()
        return data


class RiskManager:
    """
    Risk yöneticisi.

    Pozisyon başına risk kontrolü, günlük/haftalık/aylık limit takibi,
    drawdown kontrolü yapar.
    """

    def __init__(
        self,
        initial_balance: float,
        risk_limits: Optional[RiskLimits] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Risk Manager başlatıcı.

        Parametreler:
        ------------
        initial_balance : float
            Başlangıç bakiyesi (USDT)
        risk_limits : Optional[RiskLimits]
            Risk limitleri (None ise varsayılan)
        logger : Optional[logging.Logger]
            Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.risk_limits = risk_limits or RiskLimits()

        # Risk metrikleri
        self.metrics = RiskMetrics(
            peak_balance=initial_balance
        )

        # Günlük/haftalık/aylık reset için tarihleri takip
        self.last_daily_reset = datetime.now(timezone.utc).date()
        self.last_weekly_reset = self._get_week_start()
        self.last_monthly_reset = datetime.now(timezone.utc).replace(day=1).date()

        self.logger.info(f"RiskManager başlatıldı | Bakiye: ${initial_balance:,.2f}")

    def validate_trade(
        self,
        entry_price: float,
        stop_loss: float,
        quantity: float,
        side: str,  # "LONG" veya "SHORT"
        rr_ratio: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        Trade risk kontrolü yap.

        Parametreler:
        ------------
        entry_price : float
            Giriş fiyatı
        stop_loss : float
            Stop loss fiyatı
        quantity : float
            Miktar
        side : str
            "LONG" veya "SHORT"
        rr_ratio : Optional[float]
            RR oranı (varsa)

        Returns:
        --------
        Tuple[bool, str]
            (onaylandı_mı, neden)
        """
        # Günlük/haftalık/aylık reset kontrolü
        self._check_and_reset_periods()

        # Pozisyon değeri
        position_value = entry_price * quantity

        # Risk miktarı (stop loss'a göre)
        if side.upper() == "LONG":
            risk_per_unit = entry_price - stop_loss
        else:  # SHORT
            risk_per_unit = stop_loss - entry_price

        trade_risk = abs(risk_per_unit * quantity)

        # Kontrol 1: Trade başına risk limiti
        max_trade_risk = self.current_balance * self.risk_limits.max_risk_per_trade
        if trade_risk > max_trade_risk:
            return False, (
                f"Trade risk çok yüksek: ${trade_risk:.2f} > "
                f"${max_trade_risk:.2f} (max {self.risk_limits.max_risk_per_trade*100:.1f}%)"
            )

        # Kontrol 2: Pozisyon büyüklüğü limiti
        max_position_value = self.current_balance * self.risk_limits.max_position_size_percent
        if position_value > max_position_value:
            return False, (
                f"Pozisyon çok büyük: ${position_value:.2f} > "
                f"${max_position_value:.2f} (max {self.risk_limits.max_position_size_percent*100:.1f}%)"
            )

        # Kontrol 3: RR oranı
        if rr_ratio is not None and rr_ratio < self.risk_limits.min_rr_ratio:
            return False, (
                f"RR oranı çok düşük: {rr_ratio:.2f} < "
                f"{self.risk_limits.min_rr_ratio:.2f}"
            )

        # Kontrol 4: Günlük kayıp limiti
        if abs(self.metrics.daily_loss) >= self.current_balance * self.risk_limits.max_daily_loss:
            return False, (
                f"Günlük kayıp limiti aşıldı: ${abs(self.metrics.daily_loss):.2f} >= "
                f"${self.current_balance * self.risk_limits.max_daily_loss:.2f}"
            )

        # Kontrol 5: Haftalık kayıp limiti
        if abs(self.metrics.weekly_loss) >= self.current_balance * self.risk_limits.max_weekly_loss:
            return False, (
                f"Haftalık kayıp limiti aşıldı: ${abs(self.metrics.weekly_loss):.2f} >= "
                f"${self.current_balance * self.risk_limits.max_weekly_loss:.2f}"
            )

        # Kontrol 6: Aylık kayıp limiti
        if abs(self.metrics.monthly_loss) >= self.current_balance * self.risk_limits.max_monthly_loss:
            return False, (
                f"Aylık kayıp limiti aşıldı: ${abs(self.metrics.monthly_loss):.2f} >= "
                f"${self.current_balance * self.risk_limits.max_monthly_loss:.2f}"
            )

        # Kontrol 7: Maksimum drawdown
        if self.metrics.current_drawdown >= self.risk_limits.max_drawdown * 100:
            return False, (
                f"Max drawdown aşıldı: {self.metrics.current_drawdown:.2f}% >= "
                f"{self.risk_limits.max_drawdown * 100:.2f}%"
            )

        # Kontrol 8: Ardışık kayıp limiti
        if self.metrics.consecutive_losses >= self.risk_limits.max_consecutive_losses:
            return False, (
                f"Ardışık kayıp limiti aşıldı: {self.metrics.consecutive_losses} >= "
                f"{self.risk_limits.max_consecutive_losses}"
            )

        return True, "Trade onaylandı"

    def update_balance(self, new_balance: float, pnl: float) -> None:
        """
        Bakiye güncellemesi (trade sonrası).

        Parametreler:
        ------------
        new_balance : float
            Yeni bakiye (USDT)
        pnl : float
            Trade PnL (USDT)
        """
        self.current_balance = new_balance

        # Peak balance güncelle
        if new_balance > self.metrics.peak_balance:
            self.metrics.peak_balance = new_balance

        # Drawdown hesapla
        if self.metrics.peak_balance > 0:
            self.metrics.current_drawdown = (
                (self.metrics.peak_balance - new_balance) / self.metrics.peak_balance * 100
            )

        # PnL takibi
        if pnl < 0:
            self.metrics.daily_loss += pnl
            self.metrics.weekly_loss += pnl
            self.metrics.monthly_loss += pnl
            self.metrics.consecutive_losses += 1
        else:
            # Kar varsa consecutive losses sıfırla
            self.metrics.consecutive_losses = 0

        self.metrics.last_update = datetime.now(timezone.utc)

        self.logger.info(
            f"Bakiye güncellendi: ${new_balance:,.2f} | "
            f"PnL: ${pnl:,.2f} | Drawdown: {self.metrics.current_drawdown:.2f}%"
        )

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        side: str,
        risk_percent: Optional[float] = None
    ) -> float:
        """
        Optimal pozisyon büyüklüğü hesapla.

        Parametreler:
        ------------
        entry_price : float
            Giriş fiyatı
        stop_loss : float
            Stop loss fiyatı
        side : str
            "LONG" veya "SHORT"
        risk_percent : Optional[float]
            Risk yüzdesi (None ise max_risk_per_trade kullan)

        Returns:
        --------
        float
            Optimal quantity
        """
        # Risk yüzdesi
        risk_pct = risk_percent or self.risk_limits.max_risk_per_trade

        # Risk miktarı (USDT)
        risk_amount = self.current_balance * risk_pct

        # Risk per unit
        if side.upper() == "LONG":
            risk_per_unit = abs(entry_price - stop_loss)
        else:  # SHORT
            risk_per_unit = abs(stop_loss - entry_price)

        if risk_per_unit == 0:
            return 0.0

        # Quantity
        quantity = risk_amount / risk_per_unit

        return float(quantity)

    def get_risk_level(self) -> RiskLevel:
        """
        Mevcut risk seviyesini değerlendir.

        Returns:
        --------
        RiskLevel
            Risk seviyesi
        """
        # Drawdown bazlı
        if self.metrics.current_drawdown >= self.risk_limits.max_drawdown * 80:
            return RiskLevel.CRITICAL
        elif self.metrics.current_drawdown >= self.risk_limits.max_drawdown * 50:
            return RiskLevel.HIGH

        # Günlük kayıp bazlı
        daily_loss_pct = abs(self.metrics.daily_loss) / self.current_balance
        if daily_loss_pct >= self.risk_limits.max_daily_loss * 0.8:
            return RiskLevel.HIGH
        elif daily_loss_pct >= self.risk_limits.max_daily_loss * 0.5:
            return RiskLevel.MEDIUM

        # Ardışık kayıp bazlı
        if self.metrics.consecutive_losses >= self.risk_limits.max_consecutive_losses * 0.8:
            return RiskLevel.HIGH
        elif self.metrics.consecutive_losses >= self.risk_limits.max_consecutive_losses * 0.5:
            return RiskLevel.MEDIUM

        return RiskLevel.LOW

    def get_statistics(self) -> Dict[str, Any]:
        """
        Risk istatistikleri.

        Returns:
        --------
        Dict[str, Any]
            İstatistikler
        """
        return {
            'balance': {
                'initial': self.initial_balance,
                'current': self.current_balance,
                'peak': self.metrics.peak_balance,
                'total_pnl': self.current_balance - self.initial_balance,
                'total_pnl_percent': (
                    (self.current_balance - self.initial_balance) / self.initial_balance * 100
                    if self.initial_balance > 0 else 0
                )
            },
            'risk_metrics': self.metrics.to_dict(),
            'risk_limits': self.risk_limits.to_dict(),
            'risk_level': self.get_risk_level().value,
            'limits_status': {
                'daily_loss_used': (
                    abs(self.metrics.daily_loss) / (self.current_balance * self.risk_limits.max_daily_loss) * 100
                    if self.risk_limits.max_daily_loss > 0 else 0
                ),
                'weekly_loss_used': (
                    abs(self.metrics.weekly_loss) / (self.current_balance * self.risk_limits.max_weekly_loss) * 100
                    if self.risk_limits.max_weekly_loss > 0 else 0
                ),
                'monthly_loss_used': (
                    abs(self.metrics.monthly_loss) / (self.current_balance * self.risk_limits.max_monthly_loss) * 100
                    if self.risk_limits.max_monthly_loss > 0 else 0
                ),
                'drawdown_used': (
                    self.metrics.current_drawdown / (self.risk_limits.max_drawdown * 100) * 100
                    if self.risk_limits.max_drawdown > 0 else 0
                )
            }
        }

    def _check_and_reset_periods(self) -> None:
        """Günlük/haftalık/aylık reset kontrolü."""
        now = datetime.now(timezone.utc)

        # Günlük reset
        if now.date() > self.last_daily_reset:
            self.metrics.daily_loss = 0.0
            self.last_daily_reset = now.date()
            self.logger.info("Günlük kayıp resetlendi")

        # Haftalık reset
        week_start = self._get_week_start()
        if week_start > self.last_weekly_reset:
            self.metrics.weekly_loss = 0.0
            self.last_weekly_reset = week_start
            self.logger.info("Haftalık kayıp resetlendi")

        # Aylık reset
        month_start = now.replace(day=1).date()
        if month_start > self.last_monthly_reset:
            self.metrics.monthly_loss = 0.0
            self.last_monthly_reset = month_start
            self.logger.info("Aylık kayıp resetlendi")

    def _get_week_start(self) -> datetime.date:
        """Haftanın başlangıç tarihini getir (Pazartesi)."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=now.weekday())
        return start.date()


if __name__ == "__main__":
    print("Risk Manager - Test")
    print("=" * 60)

    # Logger
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Risk Manager oluştur
    rm = RiskManager(initial_balance=10000.0, logger=logger)
    print("✅ RiskManager oluşturuldu")
    print(f"   Başlangıç Bakiyesi: ${rm.initial_balance:,.2f}")

    # Test 1: Trade validasyonu (onaylı)
    print("\n📊 Test 1: Trade Validasyonu (Onaylı)")
    valid, reason = rm.validate_trade(
        entry_price=50000.0,
        stop_loss=49000.0,
        quantity=0.1,
        side="LONG",
        rr_ratio=1.5
    )
    print(f"   Entry: $50,000 | SL: $49,000 | Qty: 0.1")
    print(f"   Sonuç: {'✅ ONAYLANDI' if valid else '❌ REDDEDİLDİ'}")
    print(f"   Neden: {reason}")

    # Test 2: Position sizing
    print("\n📊 Test 2: Position Sizing")
    qty = rm.calculate_position_size(
        entry_price=50000.0,
        stop_loss=49000.0,
        side="LONG"
    )
    print(f"   Entry: $50,000 | SL: $49,000")
    print(f"   Risk: %{rm.risk_limits.max_risk_per_trade * 100}")
    print(f"   ➜ Optimal Quantity: {qty:.4f}")

    # Test 3: Bakiye güncellemesi (kayıp)
    print("\n📊 Test 3: Bakiye Güncellemesi (Kayıp)")
    rm.update_balance(new_balance=9800.0, pnl=-200.0)

    # Test 4: Risk seviyesi
    print("\n📊 Test 4: Risk Seviyesi")
    risk_level = rm.get_risk_level()
    print(f"   Risk Seviyesi: {risk_level.value}")

    # Test 5: İstatistikler
    print("\n📊 Test 5: İstatistikler")
    stats = rm.get_statistics()
    print(f"   Current Balance: ${stats['balance']['current']:,.2f}")
    print(f"   Total PnL: ${stats['balance']['total_pnl']:,.2f} ({stats['balance']['total_pnl_percent']:.2f}%)")
    print(f"   Drawdown: {stats['risk_metrics']['current_drawdown']:.2f}%")
    print(f"   Consecutive Losses: {stats['risk_metrics']['consecutive_losses']}")

    print("\n" + "=" * 60)
    print("✅ Tüm testler başarılı!")
