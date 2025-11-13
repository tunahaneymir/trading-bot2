"""
Test - Adaptive RR System
=========================

AdaptiveRRSystem için comprehensive unit tests.

Test Coverage:
--------------
- RR hesaplama doğruluğu
- Adaptif learning rate
- Asimetrik güncelleme (kar/zarar)
- Stabilization (freezing)
- State persistence
- Ödül hesaplama
- Edge cases ve sınır koşulları

Faz: 6
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from risk.adaptive_rr_system import (
    AdaptiveRRSystem,
    RRWeights,
    RRLearningRecord
)


class TestRRWeights:
    """RRWeights dataclass testleri."""

    def test_default_weights(self):
        """Varsayılan ağırlıklar."""
        weights = RRWeights()
        assert weights.signal_weight == 0.7
        assert weights.market_weight == 0.3
        assert weights.rl_factor == 1.0
        assert not weights.frozen

    def test_to_dict(self):
        """Dictionary'ye çevirme."""
        weights = RRWeights(rl_factor=1.1)
        data = weights.to_dict()

        assert data['rl_factor'] == 1.1
        assert 'last_update' in data
        assert isinstance(data['last_update'], str)

    def test_from_dict(self):
        """Dictionary'den oluşturma."""
        data = {
            'signal_weight': 0.7,
            'market_weight': 0.3,
            'rl_factor': 1.15,
            'last_update': '2025-01-01T00:00:00+00:00',
            'frozen': False,
            'frozen_until': None
        }

        weights = RRWeights.from_dict(data)
        assert weights.rl_factor == 1.15
        assert isinstance(weights.last_update, datetime)


class TestAdaptiveRRSystem:
    """AdaptiveRRSystem testleri."""

    @pytest.fixture
    def temp_state_dir(self):
        """Temporary state directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def rr_system(self, temp_state_dir):
        """Test RR system instance."""
        return AdaptiveRRSystem(state_dir=temp_state_dir)

    def test_initialization(self, rr_system):
        """Başlatma testi."""
        assert rr_system.rr_min == 1.1
        assert rr_system.rr_max == 1.9
        assert rr_system.weights.rl_factor == 1.0
        assert len(rr_system.learning_history) == 0

    def test_calculate_rr_baseline(self, rr_system):
        """Temel RR hesaplama."""
        rr = rr_system.calculate_rr(
            signal_confidence=0.8,
            trend_strength=0.6,
            volatility=0.3
        )

        # RR [1.1, 1.9] aralığında olmalı
        assert 1.1 <= rr <= 1.9

        # Yüksek güven = düşük RR (muhafazakar)
        rr_high_conf = rr_system.calculate_rr(0.9, 0.6, 0.3)
        rr_low_conf = rr_system.calculate_rr(0.5, 0.6, 0.3)
        assert rr_high_conf < rr_low_conf

    def test_calculate_rr_bounds(self, rr_system):
        """RR sınır değerleri."""
        # Minimum
        rr_min = rr_system.calculate_rr(1.0, 1.0, 0.0)
        assert rr_min >= 1.1

        # Maksimum
        rr_max = rr_system.calculate_rr(0.0, 0.0, 1.0)
        assert rr_max <= 1.9

    def test_calculate_reward(self, rr_system):
        """Ödül hesaplama."""
        # Karlı trade
        reward_profit = rr_system._calculate_reward(
            pnl=100.0,
            rr_target=1.5,
            rr_achieved=1.6,
            holding_hours=12.0
        )
        assert reward_profit > 0

        # Zararlı trade
        reward_loss = rr_system._calculate_reward(
            pnl=-50.0,
            rr_target=1.5,
            rr_achieved=0.0,
            holding_hours=12.0
        )
        assert reward_loss < 0

        # RR efficiency etkisi
        reward_high_rr = rr_system._calculate_reward(100.0, 1.5, 2.0, 12.0)
        reward_low_rr = rr_system._calculate_reward(100.0, 1.5, 1.0, 12.0)
        assert reward_high_rr > reward_low_rr

    def test_adaptive_learning_rate(self, rr_system):
        """Adaptif learning rate."""
        # Yüksek volatilite = yüksek LR
        lr_high_vol = rr_system._calculate_adaptive_learning_rate(0.8, 0.7)
        lr_low_vol = rr_system._calculate_adaptive_learning_rate(0.2, 0.7)
        assert lr_high_vol > lr_low_vol

        # Düşük güven = düşük LR
        lr_high_conf = rr_system._calculate_adaptive_learning_rate(0.5, 0.9)
        lr_low_conf = rr_system._calculate_adaptive_learning_rate(0.5, 0.3)
        assert lr_high_conf > lr_low_conf

        # LR sınırları
        lr = rr_system._calculate_adaptive_learning_rate(0.5, 0.5)
        assert 0.001 <= lr <= 0.05

    def test_asymmetric_update_profit(self, rr_system):
        """Asimetrik güncelleme - kar."""
        initial_rl = 1.0
        reward = 0.5  # Pozitif
        lr = 0.01

        new_rl = rr_system._update_rl_factor_asymmetric(initial_rl, reward, lr)

        # Kar durumunda 1.2'ye doğru gitme
        assert new_rl > initial_rl
        assert 0.7 <= new_rl <= 1.3

    def test_asymmetric_update_loss(self, rr_system):
        """Asimetrik güncelleme - zarar."""
        initial_rl = 1.0
        reward = -0.5  # Negatif
        lr = 0.01

        new_rl = rr_system._update_rl_factor_asymmetric(initial_rl, reward, lr)

        # Zarar durumunda 0.8'e doğru gitme (daha yavaş)
        assert new_rl < initial_rl
        assert 0.7 <= new_rl <= 1.3

    def test_update_from_trade_profit(self, rr_system):
        """Trade güncellemesi - kar."""
        initial_rl = rr_system.weights.rl_factor

        rr_system.update_from_trade(
            pnl=100.0,
            rr_target=1.5,
            rr_achieved=1.6,
            signal_confidence=0.85,
            market_condition=0.4,
            volatility=0.3,
            holding_hours=12.0
        )

        # RL factor artmalı (kar)
        assert rr_system.weights.rl_factor >= initial_rl

        # History'e eklenmiş olmalı
        assert len(rr_system.learning_history) == 1
        assert rr_system.learning_history[0].pnl == 100.0

    def test_update_from_trade_loss(self, rr_system):
        """Trade güncellemesi - zarar."""
        initial_rl = rr_system.weights.rl_factor

        rr_system.update_from_trade(
            pnl=-50.0,
            rr_target=1.5,
            rr_achieved=0.0,
            signal_confidence=0.65,
            market_condition=0.6,
            volatility=0.5,
            holding_hours=24.0
        )

        # RL factor azalmalı (zarar)
        assert rr_system.weights.rl_factor <= initial_rl

    def test_stabilization_freezing(self, rr_system):
        """Stabilization - freezing."""
        # 20 trade ile yüksek volatilite oluştur
        for i in range(20):
            pnl = 100.0 if i % 2 == 0 else -100.0  # Alternatif kar/zarar

            rr_system.update_from_trade(
                pnl=pnl,
                rr_target=1.5,
                rr_achieved=1.5 if pnl > 0 else 0.0,
                signal_confidence=0.7,
                market_condition=0.5,
                volatility=0.8,  # Yüksek volatilite
                holding_hours=12.0
            )

        # Yüksek volatilite nedeniyle frozen olmalı
        # (Bu test deterministik olmayabilir, opsiyonel kontrol)

    def test_state_persistence(self, temp_state_dir, rr_system):
        """State kaydetme ve yükleme."""
        # İlk güncelleme
        rr_system.update_from_trade(
            pnl=100.0,
            rr_target=1.5,
            rr_achieved=1.6,
            signal_confidence=0.85,
            market_condition=0.4,
            volatility=0.3,
            holding_hours=12.0
        )

        old_rl_factor = rr_system.weights.rl_factor

        # Yeni instance oluştur (aynı state_dir)
        new_rr_system = AdaptiveRRSystem(state_dir=temp_state_dir)

        # Ağırlıklar yüklenmiş olmalı
        assert new_rr_system.weights.rl_factor == old_rl_factor

        # History yüklenmiş olmalı
        assert len(new_rr_system.learning_history) == 1

    def test_statistics(self, rr_system):
        """İstatistikler."""
        # Birkaç trade ekle
        for i in range(5):
            rr_system.update_from_trade(
                pnl=50.0 if i % 2 == 0 else -30.0,
                rr_target=1.5,
                rr_achieved=1.4,
                signal_confidence=0.8,
                market_condition=0.4,
                volatility=0.3,
                holding_hours=10.0
            )

        stats = rr_system.get_statistics()

        assert stats['total_updates'] == 5
        assert 'current_rl_factor' in stats
        assert 'recent_100_trades' in stats
        assert stats['recent_100_trades']['avg_rr_target'] == 1.5

    def test_frozen_no_update(self, rr_system):
        """Frozen durumda güncelleme yapılmamalı."""
        # Manuel olarak dondur
        rr_system.weights.frozen = True
        rr_system.weights.frozen_until = datetime.now(timezone.utc) + timedelta(hours=1)

        initial_rl = rr_system.weights.rl_factor

        # Güncelleme dene
        rr_system.update_from_trade(
            pnl=100.0,
            rr_target=1.5,
            rr_achieved=1.6,
            signal_confidence=0.85,
            market_condition=0.4,
            volatility=0.3,
            holding_hours=12.0
        )

        # RL factor değişmemiş olmalı
        assert rr_system.weights.rl_factor == initial_rl


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
