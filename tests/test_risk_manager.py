"""
Test - Risk Manager
===================

RiskManager ve PortfolioManager için comprehensive unit tests.

Test Coverage:
--------------
- Trade validation (tüm limitler)
- Position sizing
- Drawdown kontrolü
- Günlük/haftalık/aylık limit reset
- Risk seviyesi değerlendirme
- Portfolio exposure kontrolü
- Diversifikasyon skorları

Faz: 6
"""

import pytest
from datetime import datetime, timezone, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from risk.risk_manager import (
    RiskManager,
    RiskLimits,
    RiskMetrics,
    RiskLevel
)

from risk.portfolio_manager import (
    PortfolioManager,
    ExposureLimits,
    PortfolioRisk
)


class TestRiskLimits:
    """RiskLimits dataclass testleri."""

    def test_default_limits(self):
        """Varsayılan limitler."""
        limits = RiskLimits()
        assert limits.max_risk_per_trade == 0.02
        assert limits.max_daily_loss == 0.03
        assert limits.max_drawdown == 0.10
        assert limits.max_consecutive_losses == 5


class TestRiskManager:
    """RiskManager testleri."""

    @pytest.fixture
    def risk_manager(self):
        """Test risk manager instance."""
        return RiskManager(initial_balance=10000.0)

    def test_initialization(self, risk_manager):
        """Başlatma testi."""
        assert risk_manager.initial_balance == 10000.0
        assert risk_manager.current_balance == 10000.0
        assert risk_manager.metrics.current_drawdown == 0.0

    def test_validate_trade_approved(self, risk_manager):
        """Trade validasyonu - onaylı."""
        valid, reason = risk_manager.validate_trade(
            entry_price=50000.0,
            stop_loss=49000.0,
            quantity=0.1,
            side="LONG",
            rr_ratio=1.5
        )

        assert valid is True
        assert "onaylandı" in reason.lower()

    def test_validate_trade_risk_too_high(self, risk_manager):
        """Trade validasyonu - risk çok yüksek."""
        # Risk = (50000 - 49000) * 1.0 = 1000 USDT
        # Max risk = 10000 * 0.02 = 200 USDT
        valid, reason = risk_manager.validate_trade(
            entry_price=50000.0,
            stop_loss=49000.0,
            quantity=1.0,  # Çok büyük
            side="LONG",
            rr_ratio=1.5
        )

        assert valid is False
        assert "risk çok yüksek" in reason.lower()

    def test_validate_trade_position_too_large(self, risk_manager):
        """Trade validasyonu - pozisyon çok büyük."""
        # Position value = 50000 * 0.02 = 1000 USDT
        # Max position = 10000 * 0.03 = 300 USDT
        valid, reason = risk_manager.validate_trade(
            entry_price=50000.0,
            stop_loss=49500.0,  # Düşük risk
            quantity=0.02,  # Büyük miktar
            side="LONG"
        )

        assert valid is False
        assert "pozisyon çok büyük" in reason.lower()

    def test_validate_trade_rr_too_low(self, risk_manager):
        """Trade validasyonu - RR çok düşük."""
        valid, reason = risk_manager.validate_trade(
            entry_price=50000.0,
            stop_loss=49000.0,
            quantity=0.01,
            side="LONG",
            rr_ratio=0.5  # Çok düşük
        )

        assert valid is False
        assert "rr oranı çok düşük" in reason.lower()

    def test_validate_trade_daily_loss_exceeded(self, risk_manager):
        """Trade validasyonu - günlük kayıp limiti."""
        # Günlük kayıp limitine ulaş
        risk_manager.metrics.daily_loss = -300.0  # %3 = 300 USDT

        valid, reason = risk_manager.validate_trade(
            entry_price=50000.0,
            stop_loss=49000.0,
            quantity=0.01,
            side="LONG",
            rr_ratio=1.5
        )

        assert valid is False
        assert "günlük kayıp" in reason.lower()

    def test_validate_trade_max_drawdown(self, risk_manager):
        """Trade validasyonu - max drawdown."""
        # Drawdown limitine ulaş
        risk_manager.metrics.current_drawdown = 11.0  # %11 (limit %10)

        valid, reason = risk_manager.validate_trade(
            entry_price=50000.0,
            stop_loss=49000.0,
            quantity=0.01,
            side="LONG",
            rr_ratio=1.5
        )

        assert valid is False
        assert "drawdown" in reason.lower()

    def test_validate_trade_consecutive_losses(self, risk_manager):
        """Trade validasyonu - ardışık kayıp."""
        # Ardışık kayıp limitine ulaş
        risk_manager.metrics.consecutive_losses = 5

        valid, reason = risk_manager.validate_trade(
            entry_price=50000.0,
            stop_loss=49000.0,
            quantity=0.01,
            side="LONG",
            rr_ratio=1.5
        )

        assert valid is False
        assert "ardışık kayıp" in reason.lower()

    def test_update_balance_profit(self, risk_manager):
        """Bakiye güncellemesi - kar."""
        risk_manager.update_balance(new_balance=10500.0, pnl=500.0)

        assert risk_manager.current_balance == 10500.0
        assert risk_manager.metrics.peak_balance == 10500.0
        assert risk_manager.metrics.consecutive_losses == 0  # Reset

    def test_update_balance_loss(self, risk_manager):
        """Bakiye güncellemesi - zarar."""
        risk_manager.update_balance(new_balance=9800.0, pnl=-200.0)

        assert risk_manager.current_balance == 9800.0
        assert risk_manager.metrics.daily_loss == -200.0
        assert risk_manager.metrics.consecutive_losses == 1

    def test_calculate_position_size(self, risk_manager):
        """Position sizing."""
        qty = risk_manager.calculate_position_size(
            entry_price=50000.0,
            stop_loss=49000.0,
            side="LONG"
        )

        # Risk = 10000 * 0.02 = 200 USDT
        # Risk per unit = 50000 - 49000 = 1000
        # Qty = 200 / 1000 = 0.2
        assert qty == pytest.approx(0.2, rel=1e-2)

    def test_get_risk_level_low(self, risk_manager):
        """Risk seviyesi - LOW."""
        level = risk_manager.get_risk_level()
        assert level == RiskLevel.LOW

    def test_get_risk_level_medium(self, risk_manager):
        """Risk seviyesi - MEDIUM."""
        # Orta seviye drawdown
        risk_manager.metrics.current_drawdown = 6.0  # %6 (limit %10)
        level = risk_manager.get_risk_level()
        assert level == RiskLevel.MEDIUM

    def test_get_risk_level_high(self, risk_manager):
        """Risk seviyesi - HIGH."""
        # Yüksek drawdown
        risk_manager.metrics.current_drawdown = 9.0  # %9 (limit %10)
        level = risk_manager.get_risk_level()
        assert level == RiskLevel.HIGH

    def test_get_risk_level_critical(self, risk_manager):
        """Risk seviyesi - CRITICAL."""
        # Kritik drawdown
        risk_manager.metrics.current_drawdown = 9.5  # %9.5 (limit %10)
        level = risk_manager.get_risk_level()
        assert level == RiskLevel.CRITICAL

    def test_statistics(self, risk_manager):
        """İstatistikler."""
        stats = risk_manager.get_statistics()

        assert 'balance' in stats
        assert 'risk_metrics' in stats
        assert 'risk_limits' in stats
        assert 'risk_level' in stats
        assert stats['balance']['initial'] == 10000.0


class TestPortfolioManager:
    """PortfolioManager testleri."""

    @pytest.fixture
    def portfolio_manager(self):
        """Test portfolio manager instance."""
        return PortfolioManager(total_balance=10000.0)

    def test_initialization(self, portfolio_manager):
        """Başlatma testi."""
        assert portfolio_manager.total_balance == 10000.0
        assert len(portfolio_manager.active_exposures) == 0
        assert portfolio_manager.portfolio_risk.total_exposure == 0.0

    def test_can_open_position_approved(self, portfolio_manager):
        """Pozisyon açma kontrolü - onaylı."""
        can_open, reason = portfolio_manager.can_open_position(
            symbol="BTCUSDT",
            position_value=300.0
        )

        assert can_open is True
        assert "açılabilir" in reason.lower()

    def test_can_open_position_total_exposure_exceeded(self, portfolio_manager):
        """Pozisyon açma kontrolü - toplam exposure aşımı."""
        # Mevcut exposure'ı yüksek tut
        portfolio_manager.active_exposures["ETHUSDT"] = 500.0
        portfolio_manager._update_portfolio_risk()

        # Yeni pozisyon toplam limiti aşacak
        # Max total = 10000 * 0.06 = 600 USDT
        can_open, reason = portfolio_manager.can_open_position(
            symbol="BTCUSDT",
            position_value=200.0  # 500 + 200 = 700 > 600
        )

        assert can_open is False
        assert "toplam exposure" in reason.lower()

    def test_can_open_position_single_coin_exceeded(self, portfolio_manager):
        """Pozisyon açma kontrolü - tek coin limiti."""
        # Max coin = 10000 * 0.03 = 300 USDT
        can_open, reason = portfolio_manager.can_open_position(
            symbol="BTCUSDT",
            position_value=350.0  # Limit aşımı
        )

        assert can_open is False
        assert "exposure limiti" in reason.lower()

    def test_add_position(self, portfolio_manager):
        """Pozisyon ekleme."""
        portfolio_manager.add_position("BTCUSDT", 300.0)

        assert "BTCUSDT" in portfolio_manager.active_exposures
        assert portfolio_manager.active_exposures["BTCUSDT"] == 300.0
        assert portfolio_manager.portfolio_risk.total_exposure == 300.0

    def test_remove_position(self, portfolio_manager):
        """Pozisyon kaldırma."""
        portfolio_manager.add_position("BTCUSDT", 300.0)
        portfolio_manager.remove_position("BTCUSDT", 300.0)

        assert "BTCUSDT" not in portfolio_manager.active_exposures
        assert portfolio_manager.portfolio_risk.total_exposure == 0.0

    def test_update_position_value(self, portfolio_manager):
        """Pozisyon değeri güncelleme."""
        portfolio_manager.add_position("BTCUSDT", 300.0)
        portfolio_manager.update_position_value("BTCUSDT", 350.0)

        assert portfolio_manager.active_exposures["BTCUSDT"] == 350.0
        assert portfolio_manager.portfolio_risk.total_exposure == 350.0

    def test_calculate_diversification_score_single(self, portfolio_manager):
        """Diversifikasyon - tek coin."""
        portfolio_manager.add_position("BTCUSDT", 300.0)

        div_score = portfolio_manager.calculate_diversification_score()

        # Tek coin = düşük diversifikasyon (HHI = 1.0, div = 0.0)
        assert div_score == pytest.approx(0.0, abs=1e-6)

    def test_calculate_diversification_score_multiple(self, portfolio_manager):
        """Diversifikasyon - çoklu coin."""
        portfolio_manager.add_position("BTCUSDT", 200.0)
        portfolio_manager.add_position("ETHUSDT", 200.0)
        portfolio_manager.add_position("BNBUSDT", 200.0)

        div_score = portfolio_manager.calculate_diversification_score()

        # Eşit dağılım = yüksek diversifikasyon
        # 3 coin eşit: HHI = 3 * (1/3)^2 = 0.333, div = 0.666
        assert div_score > 0.5

    def test_optimal_allocation_equal(self, portfolio_manager):
        """Optimal tahsis - eşit ağırlık."""
        coins = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        allocation = portfolio_manager.calculate_optimal_allocation(coins)

        # Eşit dağılım
        assert len(allocation) == 3
        for coin in coins:
            assert allocation[coin] == pytest.approx(1.0 / 3, rel=1e-2)

    def test_optimal_allocation_scored(self, portfolio_manager):
        """Optimal tahsis - skor bazlı."""
        coins = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        scores = {"BTCUSDT": 0.9, "ETHUSDT": 0.6, "BNBUSDT": 0.3}

        allocation = portfolio_manager.calculate_optimal_allocation(coins, scores)

        # Yüksek skor = yüksek ağırlık
        assert allocation["BTCUSDT"] > allocation["ETHUSDT"]
        assert allocation["ETHUSDT"] > allocation["BNBUSDT"]

        # Toplam 1.0
        assert sum(allocation.values()) == pytest.approx(1.0, rel=1e-2)

    def test_statistics(self, portfolio_manager):
        """İstatistikler."""
        portfolio_manager.add_position("BTCUSDT", 300.0)
        portfolio_manager.add_position("ETHUSDT", 200.0)

        stats = portfolio_manager.get_statistics()

        assert stats['balance'] == 10000.0
        assert stats['active_coins'] == 2
        assert 'portfolio_risk' in stats
        assert 'exposure_by_coin' in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
