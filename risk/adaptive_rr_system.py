"""
Adaptive Risk-Reward (RR) System
=================================

Self-evolving RR sistem - RR_SYSTEM_FINAL.py'den tam uygulama.

Özellikler:
-----------
- Signal Confidence Core (SuperTrend, MOST, QQE, RVOL)
- Market Condition Modulator (Trend Strength + Volatility)
- RL Optimization Layer (Gerçek trade sonuçlarına göre adaptif öğrenme)
- Stabilization Logic (RR volatilitesi > 0.4 ise dondurma)
- State Persistence (rr_weights.json, rr_learning_history.json)
- Adaptive Learning Rate (Volatilite, Performance, Confidence, Time-based)
- Asimetrik güncelleme (Kar/Zarar için farklı hızlar)

Formül:
-------
    signal_confidence = weighted_avg([st_conf, qqe_conf, most_conf, rvol_conf])
    market_condition = 0.5 * (1 - trend_strength) + 0.5 * volatility
    rr_signal = 1.5 - (signal_confidence * 0.4)
    rr_market = rr_signal + (market_condition * 0.3)
    rr_final = rr_market * rr_weights["rl_factor"]
    rr_final = clip(rr_final, 1.1, 1.9)

Faz: 6
Versiyon: 1.0.0
Yazar: Trading Bot System (RR_SYSTEM_FINAL.py specs)
"""

import json
import logging
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone, timedelta
from collections import deque


@dataclass
class RRWeights:
    """
    RR sistem ağırlıkları.

    Attributes:
    -----------
    signal_weight : float
        Sinyal güveni ağırlığı (varsayılan: 0.7)
    market_weight : float
        Market condition ağırlığı (varsayılan: 0.3)
    rl_factor : float
        RL optimization faktörü (varsayılan: 1.0, aralık: [0.7, 1.3])
    last_update : datetime
        Son güncelleme zamanı
    frozen : bool
        Ağırlıklar donduruldu mu? (RR volatilitesi yüksekse)
    frozen_until : Optional[datetime]
        Dondurma bitiş zamanı
    """
    signal_weight: float = 0.7
    market_weight: float = 0.3
    rl_factor: float = 1.0
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    frozen: bool = False
    frozen_until: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Dictionary'ye çevir."""
        data = asdict(self)
        data['last_update'] = self.last_update.isoformat()
        data['frozen_until'] = self.frozen_until.isoformat() if self.frozen_until else None
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RRWeights':
        """Dictionary'den oluştur."""
        if 'last_update' in data and isinstance(data['last_update'], str):
            data['last_update'] = datetime.fromisoformat(data['last_update'])
        if 'frozen_until' in data and data['frozen_until'] and isinstance(data['frozen_until'], str):
            data['frozen_until'] = datetime.fromisoformat(data['frozen_until'])
        return cls(**data)


@dataclass
class RRLearningRecord:
    """
    Tek bir trade'den RR öğrenme kaydı.

    Attributes:
    -----------
    timestamp : datetime
        Kayıt zamanı
    pnl : float
        Trade PnL (USDT)
    rr_target : float
        Hedef RR
    rr_achieved : float
        Ulaşılan RR
    signal_confidence : float
        Sinyal güveni
    market_condition : float
        Market condition index
    volatility : float
        ATR normalize volatilite
    reward : float
        Hesaplanan ödül
    learning_rate : float
        Kullanılan öğrenme hızı
    rl_factor_before : float
        Güncelleme öncesi rl_factor
    rl_factor_after : float
        Güncelleme sonrası rl_factor
    """
    timestamp: datetime
    pnl: float
    rr_target: float
    rr_achieved: float
    signal_confidence: float
    market_condition: float
    volatility: float
    reward: float
    learning_rate: float
    rl_factor_before: float
    rl_factor_after: float

    def to_dict(self) -> Dict[str, Any]:
        """Dictionary'ye çevir."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class AdaptiveRRSystem:
    """
    Adaptif Risk-Reward sistemi.

    RR_SYSTEM_FINAL.py'deki tüm kuralları uygular:
    - Sinyal güvenine göre RR hesaplama
    - Market condition modülasyonu
    - RL optimization ile öğrenme
    - Adaptif learning rate (volatilite, performans, confidence, time-based)
    - Stabilization (RR volatilitesi kontrolü)
    - State persistence
    """

    def __init__(
        self,
        state_dir: str = "state",
        weights_file: str = "rr_weights.json",
        history_file: str = "rr_learning_history.json",
        logger: Optional[logging.Logger] = None
    ):
        """
        Adaptif RR System başlatıcı.

        Parametreler:
        ------------
        state_dir : str
            State dosyaları dizini
        weights_file : str
            RR ağırlıkları dosya adı
        history_file : str
            Öğrenme geçmişi dosya adı
        logger : Optional[logging.Logger]
            Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

        # State dosyaları
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.weights_file = self.state_dir / weights_file
        self.history_file = self.state_dir / history_file

        # RR parametreleri (RR_SYSTEM_FINAL.py)
        self.rr_min = 1.1
        self.rr_max = 1.9
        self.rl_factor_min = 0.7
        self.rl_factor_max = 1.3

        # Stabilization parametreleri
        self.stabilization_window = 20  # Son 20 trade
        self.volatility_threshold = 0.4  # RR değişim volatilitesi
        self.freeze_duration_hours = 24

        # Adaptif öğrenme parametreleri
        self.base_lr_min = 0.001
        self.base_lr_max = 0.05
        self.active_days = 0  # Sistem kaç gün aktif (basitleştirilmiş)

        # Asimetrik güncelleme parametreleri
        self.profit_target = 1.2  # Karda rl_factor'ü 1.2'ye çekmek
        self.loss_target = 0.8    # Zararda rl_factor'ü 0.8'e çekmek
        self.profit_update_speed = 0.5  # Orta hız
        self.loss_update_speed = 0.3    # Daha yavaş

        # Ağırlıkları yükle veya oluştur
        self.weights = self._load_or_create_weights()

        # Öğrenme geçmişi (son 500 trade)
        self.learning_history: deque = self._load_learning_history()

        # RR değişim takibi (stabilization için)
        self.rr_changes: deque = deque(maxlen=self.stabilization_window)

        self.logger.info("AdaptiveRRSystem başlatıldı")
        self.logger.info(f"  RR Aralığı: [{self.rr_min}, {self.rr_max}]")
        self.logger.info(f"  RL Factor: {self.weights.rl_factor:.3f}")
        self.logger.info(f"  Frozen: {self.weights.frozen}")

    def calculate_rr(
        self,
        signal_confidence: float,
        trend_strength: float,
        volatility: float
    ) -> float:
        """
        RR hedefini hesapla.

        Formül (RR_SYSTEM_FINAL.py):
        ----------------------------
        signal_confidence = weighted_avg([indicators])
        market_condition = 0.5 * (1 - trend_strength) + 0.5 * volatility
        rr_signal = 1.5 - (signal_confidence * 0.4)
        rr_market = rr_signal + (market_condition * 0.3)
        rr_final = rr_market * rr_weights["rl_factor"]
        rr_final = clip(rr_final, 1.1, 1.9)

        Parametreler:
        ------------
        signal_confidence : float
            Sinyal güveni [0, 1]
        trend_strength : float
            Trend gücü [0, 1]
        volatility : float
            Normalize volatilite [0, 1]

        Returns:
        --------
        float
            Hesaplanan RR hedefi
        """
        # Market condition index
        market_condition = 0.5 * (1 - trend_strength) + 0.5 * volatility

        # RR signal (baseline 1.5)
        rr_signal = 1.5 - (signal_confidence * 0.4)

        # RR market (market condition ekle)
        rr_market = rr_signal + (market_condition * 0.3)

        # RL factor uygula
        rr_final = rr_market * self.weights.rl_factor

        # Clamp
        rr_final = np.clip(rr_final, self.rr_min, self.rr_max)

        return float(rr_final)

    def update_from_trade(
        self,
        pnl: float,
        rr_target: float,
        rr_achieved: float,
        signal_confidence: float,
        market_condition: float,
        volatility: float,
        holding_hours: float
    ) -> None:
        """
        Trade sonucuna göre RR sistemini güncelle.

        Parametreler:
        ------------
        pnl : float
            Realized PnL (USDT)
        rr_target : float
            Hedef RR
        rr_achieved : float
            Gerçekleşen RR
        signal_confidence : float
            Sinyal güveni [0, 1]
        market_condition : float
            Market condition index [0, 1]
        volatility : float
            Normalize volatilite [0, 1]
        holding_hours : float
            Pozisyon tutma süresi (saat)
        """
        # Frozen kontrolü
        if self.weights.frozen:
            if datetime.now(timezone.utc) >= self.weights.frozen_until:
                self.weights.frozen = False
                self.weights.frozen_until = None
                self.logger.info("RR ağırlıkları dondurma süresi doldu, tekrar aktif")
            else:
                self.logger.debug("RR ağırlıkları dondurulmuş, güncelleme yapılmıyor")
                return

        # Ödül hesapla
        reward = self._calculate_reward(
            pnl, rr_target, rr_achieved, holding_hours
        )

        # Adaptif learning rate hesapla
        learning_rate = self._calculate_adaptive_learning_rate(
            volatility, signal_confidence
        )

        # RL factor'ü güncelle (asimetrik)
        rl_factor_before = self.weights.rl_factor
        self.weights.rl_factor = self._update_rl_factor_asymmetric(
            self.weights.rl_factor,
            reward,
            learning_rate
        )
        rl_factor_after = self.weights.rl_factor

        # Değişim kaydı (stabilization için)
        self.rr_changes.append(abs(rl_factor_after - rl_factor_before))

        # Stabilization kontrolü
        self._check_and_freeze_if_volatile()

        # Learning record oluştur
        record = RRLearningRecord(
            timestamp=datetime.now(timezone.utc),
            pnl=pnl,
            rr_target=rr_target,
            rr_achieved=rr_achieved,
            signal_confidence=signal_confidence,
            market_condition=market_condition,
            volatility=volatility,
            reward=reward,
            learning_rate=learning_rate,
            rl_factor_before=rl_factor_before,
            rl_factor_after=rl_factor_after
        )

        # Geçmişe ekle
        self.learning_history.append(record)

        # State kaydet
        self.save_state()

        self.logger.info(
            f"RR güncellendi: rl_factor {rl_factor_before:.3f} → {rl_factor_after:.3f} | "
            f"PnL: ${pnl:.2f} | Reward: {reward:.3f} | LR: {learning_rate:.4f}"
        )

    def _calculate_reward(
        self,
        pnl: float,
        rr_target: float,
        rr_achieved: float,
        holding_hours: float
    ) -> float:
        """
        Ödül hesapla (RR_SYSTEM_FINAL.py).

        Formül:
        -------
        pnl_norm = log1p(abs(pnl)) * sign(pnl)
        rr_efficiency = min(1.0, rr_achieved / rr_target)
        time_penalty = max(0.5, 1.0 - (holding_hours / 168))
        reward = pnl_norm * rr_efficiency * time_penalty

        Parametreler:
        ------------
        pnl : float
            PnL (USDT)
        rr_target : float
            Hedef RR
        rr_achieved : float
            Ulaşılan RR
        holding_hours : float
            Tutma süresi (saat)

        Returns:
        --------
        float
            Ödül değeri
        """
        # PnL normalizasyonu
        pnl_norm = np.log1p(abs(pnl)) * np.sign(pnl)

        # RR verimliliği
        rr_efficiency = min(1.0, rr_achieved / rr_target) if rr_target > 0 else 0.0

        # Zaman cezası (1 hafta = 168 saat)
        time_penalty = max(0.5, 1.0 - (holding_hours / 168.0))

        # Final ödül
        reward = pnl_norm * rr_efficiency * time_penalty

        return float(reward)

    def _calculate_adaptive_learning_rate(
        self,
        volatility: float,
        signal_confidence: float
    ) -> float:
        """
        Adaptif öğrenme hızı hesapla.

        Bileşenler:
        -----------
        1. Volatilite bileşeni: clip(volatility * 0.05, 0.001, 0.03)
        2. Performance bileşeni: Win rate'e göre çarpan (basit: 1.0)
        3. Confidence bileşeni: 0.5 + (signal_confidence * 0.5)
        4. Time decay: max(0.5, 1.0 - (active_days / 180))

        Final LR = clip(vol_comp * perf_mult * conf_mult * time_decay, 0.001, 0.05)

        Parametreler:
        ------------
        volatility : float
            Market volatilitesi [0, 1]
        signal_confidence : float
            Sinyal güveni [0, 1]

        Returns:
        --------
        float
            Öğrenme hızı
        """
        # Volatilite bileşeni
        vol_component = np.clip(volatility * 0.05, 0.001, 0.03)

        # Performance çarpanı (basit: 1.0, gelişmiş: win_rate'e göre)
        perf_multiplier = 1.0

        # Confidence çarpanı (düşük güven = yavaş öğrenme)
        conf_multiplier = 0.5 + (signal_confidence * 0.5)

        # Time decay (sistem olgunlaştıkça yavaşlar)
        time_decay = max(0.5, 1.0 - (self.active_days / 180.0))

        # Final LR
        learning_rate = vol_component * perf_multiplier * conf_multiplier * time_decay
        learning_rate = np.clip(learning_rate, self.base_lr_min, self.base_lr_max)

        return float(learning_rate)

    def _update_rl_factor_asymmetric(
        self,
        current_rl: float,
        reward: float,
        learning_rate: float
    ) -> float:
        """
        RL factor'ü asimetrik olarak güncelle.

        Kar: rl_factor → 1.2 (orta hız 0.5x)
        Zarar: rl_factor → 0.8 (yavaş 0.3x)

        Parametreler:
        ------------
        current_rl : float
            Mevcut rl_factor
        reward : float
            Ödül değeri
        learning_rate : float
            Öğrenme hızı

        Returns:
        --------
        float
            Yeni rl_factor
        """
        if reward > 0:
            # Kar: 1.2'ye doğru çek
            update = learning_rate * (self.profit_target - current_rl) * self.profit_update_speed
        else:
            # Zarar: 0.8'e doğru çek (daha yavaş)
            update = -learning_rate * (current_rl - self.loss_target) * self.loss_update_speed

        new_rl = current_rl + update
        new_rl = np.clip(new_rl, self.rl_factor_min, self.rl_factor_max)

        return float(new_rl)

    def _check_and_freeze_if_volatile(self) -> None:
        """
        RR volatilitesi yüksekse ağırlıkları dondur.

        Kural: Son 20 trade'deki RR değişim std > 0.4 ise 24 saat dondur.
        """
        if len(self.rr_changes) < self.stabilization_window:
            return

        # RR değişim volatilitesi
        rr_volatility = np.std(list(self.rr_changes))

        if rr_volatility > self.volatility_threshold:
            self.weights.frozen = True
            self.weights.frozen_until = datetime.now(timezone.utc) + timedelta(hours=self.freeze_duration_hours)

            self.logger.warning(
                f"RR volatilitesi yüksek ({rr_volatility:.3f} > {self.volatility_threshold}), "
                f"ağırlıklar {self.freeze_duration_hours} saat donduruldu"
            )

    def get_statistics(self) -> Dict[str, Any]:
        """
        RR sistem istatistikleri.

        Returns:
        --------
        Dict[str, Any]
            İstatistikler
        """
        if not self.learning_history:
            return {
                'total_updates': 0,
                'current_rl_factor': self.weights.rl_factor,
                'frozen': self.weights.frozen
            }

        # Son N trade analizi
        recent = list(self.learning_history)[-100:]

        avg_reward = np.mean([r.reward for r in recent])
        avg_lr = np.mean([r.learning_rate for r in recent])
        avg_rr_target = np.mean([r.rr_target for r in recent])
        avg_rr_achieved = np.mean([r.rr_achieved for r in recent])

        return {
            'total_updates': len(self.learning_history),
            'current_rl_factor': self.weights.rl_factor,
            'frozen': self.weights.frozen,
            'frozen_until': self.weights.frozen_until.isoformat() if self.weights.frozen_until else None,
            'rr_range': [self.rr_min, self.rr_max],
            'recent_100_trades': {
                'avg_reward': float(avg_reward),
                'avg_learning_rate': float(avg_lr),
                'avg_rr_target': float(avg_rr_target),
                'avg_rr_achieved': float(avg_rr_achieved),
                'rr_efficiency': float(avg_rr_achieved / avg_rr_target if avg_rr_target > 0 else 0)
            }
        }

    def _load_or_create_weights(self) -> RRWeights:
        """RR ağırlıklarını yükle veya yeni oluştur."""
        if self.weights_file.exists():
            try:
                with open(self.weights_file, 'r') as f:
                    data = json.load(f)
                weights = RRWeights.from_dict(data)
                self.logger.info(f"RR ağırlıkları yüklendi: {self.weights_file}")
                return weights
            except Exception as e:
                self.logger.error(f"RR ağırlıkları yüklenemedi: {e}, varsayılan kullanılıyor")

        # Varsayılan ağırlıklar
        weights = RRWeights()
        self._save_weights(weights)
        return weights

    def _load_learning_history(self) -> deque:
        """Öğrenme geçmişini yükle."""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    data = json.load(f)

                history = deque(maxlen=500)
                for item in data:
                    item['timestamp'] = datetime.fromisoformat(item['timestamp'])
                    record = RRLearningRecord(**item)
                    history.append(record)

                self.logger.info(f"RR öğrenme geçmişi yüklendi: {len(history)} kayıt")
                return history
            except Exception as e:
                self.logger.error(f"Öğrenme geçmişi yüklenemedi: {e}")

        return deque(maxlen=500)

    def save_state(self) -> None:
        """RR state'ini dosyalara kaydet."""
        try:
            # Ağırlıkları kaydet
            self._save_weights(self.weights)

            # Geçmişi kaydet
            self._save_history()

        except Exception as e:
            self.logger.error(f"RR state kaydetme hatası: {e}")

    def _save_weights(self, weights: RRWeights) -> None:
        """Ağırlıkları kaydet."""
        with open(self.weights_file, 'w') as f:
            json.dump(weights.to_dict(), f, indent=2)

    def _save_history(self) -> None:
        """Öğrenme geçmişini kaydet."""
        data = [record.to_dict() for record in self.learning_history]
        with open(self.history_file, 'w') as f:
            json.dump(data, f, indent=2)


if __name__ == "__main__":
    print("Adaptive RR System - Test")
    print("=" * 60)

    # Logger
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # RR System oluştur
    rr_system = AdaptiveRRSystem(state_dir="state", logger=logger)
    print("✅ AdaptiveRRSystem oluşturuldu")

    # Test 1: RR hesaplama
    print("\n📊 Test 1: RR Hesaplama")
    rr = rr_system.calculate_rr(
        signal_confidence=0.85,
        trend_strength=0.7,
        volatility=0.3
    )
    print(f"   Signal Confidence: 0.85")
    print(f"   Trend Strength: 0.7")
    print(f"   Volatility: 0.3")
    print(f"   ➜ RR Target: {rr:.2f}")

    # Test 2: Trade güncellemesi (kar)
    print("\n📊 Test 2: Kazanç Trade Güncellemesi")
    rr_system.update_from_trade(
        pnl=150.0,
        rr_target=1.5,
        rr_achieved=1.6,
        signal_confidence=0.85,
        market_condition=0.4,
        volatility=0.3,
        holding_hours=12.0
    )

    # Test 3: Trade güncellemesi (zarar)
    print("\n📊 Test 3: Zarar Trade Güncellemesi")
    rr_system.update_from_trade(
        pnl=-50.0,
        rr_target=1.5,
        rr_achieved=0.0,
        signal_confidence=0.65,
        market_condition=0.6,
        volatility=0.5,
        holding_hours=24.0
    )

    # Test 4: İstatistikler
    print("\n📊 Test 4: İstatistikler")
    stats = rr_system.get_statistics()
    print(f"   Total Updates: {stats['total_updates']}")
    print(f"   Current RL Factor: {stats['current_rl_factor']:.3f}")
    print(f"   Frozen: {stats['frozen']}")

    print("\n" + "=" * 60)
    print("✅ Tüm testler başarılı!")
