"""
Sinyal Üretici (Signal Generator)
==================================

Multi-timeframe teknik analiz kullanarak trading sinyalleri üretir.

Strateji:
--------
1h Timeframe:
  - SuperTrend: Genel trend yönü

15m Timeframe:
  - MOST: Entry/exit timing
  - QQE MOD: Momentum onayı
  - RVOL: Volume onayı

Sinyal Mantığı:
--------------
STRONG_BUY:
  - 1h SuperTrend: Uptrend
  - 15m MOST: Uptrend
  - 15m QQE MOD: Long signal
  - 15m RVOL: High volume (>1.5x)

STRONG_SELL:
  - 1h SuperTrend: Downtrend
  - 15m MOST: Downtrend
  - 15m QQE MOD: Short signal
  - 15m RVOL: High volume (>1.5x)

WAIT/NEUTRAL:
  - Tüm indikatörler uyuşmuyorsa

Yazar: Trading Bot Sistemi
Versiyon: 1.0.0
Faz: 5
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import logging


class SignalType(Enum):
    """Sinyal tipleri."""
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    NEUTRAL = "NEUTRAL"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


class ConfidenceLevel(Enum):
    """Güven seviyeleri."""
    VERY_HIGH = "VERY_HIGH"  # 4/4 indikatör uyuşuyor
    HIGH = "HIGH"            # 3/4 indikatör uyuşuyor
    MEDIUM = "MEDIUM"        # 2/4 indikatör uyuşuyor
    LOW = "LOW"              # 1/4 indikatör uyuşuyor
    VERY_LOW = "VERY_LOW"    # 0/4 indikatör uyuşuyor


@dataclass
class IndicatorSignal:
    """Tek bir indikatör sinyali."""
    name: str
    value: Any
    signal: str  # "BUY", "SELL", "NEUTRAL"
    timeframe: str
    reason: str
    
    def to_dict(self) -> Dict:
        """Dictionary'ye çevir."""
        return {
            'name': self.name,
            'value': self.value,
            'signal': self.signal,
            'timeframe': self.timeframe,
            'reason': self.reason
        }


@dataclass
class TradingSignal:
    """Final trading sinyali."""
    signal_type: SignalType
    confidence: ConfidenceLevel
    confidence_score: float  # 0-1 arası
    entry_price: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    indicators: List[IndicatorSignal]
    reasons: List[str]
    timestamp: str
    
    def to_dict(self) -> Dict:
        """Dictionary'ye çevir."""
        return {
            'signal_type': self.signal_type.value,
            'confidence': self.confidence.value,
            'confidence_score': self.confidence_score,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'indicators': [ind.to_dict() for ind in self.indicators],
            'reasons': self.reasons,
            'timestamp': self.timestamp
        }


class SignalGenerator:
    """
    Multi-timeframe sinyal üreticisi.
    
    Tüm teknik indikatörleri birleştirerek trading sinyalleri üretir.
    """
    
    def __init__(
        self,
        config: Optional[Dict] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Signal Generator başlatıcı.
        
        Parametreler:
        ------------
        config : Optional[Dict]
            Konfigürasyon ayarları
        logger : Optional[logging.Logger]
            Logger instance
        """
        self.config = config or self._default_config()
        self.logger = logger or logging.getLogger(__name__)
        
        # İndikatör import
        try:
            from indicators import (
                calculate_most,
                calculate_supertrend,
                qqe_mod,
                rvol
            )
            self.calculate_most = calculate_most
            self.calculate_supertrend = calculate_supertrend
            self.qqe_mod = qqe_mod
            self.rvol = rvol
            
        except ImportError as e:
            self.logger.error(f"İndikatör import hatası: {e}")
            raise
        
        self.logger.info("SignalGenerator başlatıldı")
    
    def _default_config(self) -> Dict:
        """Varsayılan konfigürasyon."""
        return {
            # SuperTrend (1h)
            'supertrend': {
                'timeframe': '1h',
                'atr_period': 14,
                'multiplier': 3.0
            },
            # MOST (15m)
            'most': {
                'timeframe': '15m',
                'length': 9,
                'percent': 2.0,
                'ma_type': 'VAR'
            },
            # QQE MOD (15m)
            'qqe_mod': {
                'timeframe': '15m',
                'rsi_period': 6,
                'rsi_smoothing': 5,
                'qqe_factor': 3.0,
                'threshold': 3
            },
            # RVOL (15m)
            'rvol': {
                'timeframe': '15m',
                'period': 20,
                'threshold_high': 1.5,
                'threshold_low': 0.5
            },
            # Risk Management
            'risk': {
                'stop_loss_atr_multiplier': 2.0,
                'take_profit_ratio': 2.0  # RR ratio
            }
        }
    
    def analyze_supertrend(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray
    ) -> IndicatorSignal:
        """
        SuperTrend analizi (1h).
        
        Returns:
        --------
        IndicatorSignal
            SuperTrend sinyali
        """
        config = self.config['supertrend']
        
        try:
            st_line, trend = self.calculate_supertrend(
                high, low, close,
                atr_period=config['atr_period'],
                multiplier=config['multiplier']
            )
            
            current_trend = trend[-1]
            current_st = st_line[-1]
            current_price = close[-1]
            
            # Sinyal belirle
            if current_trend == 1:
                signal = "BUY"
                reason = f"SuperTrend uptrend (ST: {current_st:.2f})"
            else:
                signal = "SELL"
                reason = f"SuperTrend downtrend (ST: {current_st:.2f})"
            
            return IndicatorSignal(
                name="SuperTrend",
                value=current_st,
                signal=signal,
                timeframe=config['timeframe'],
                reason=reason
            )
            
        except Exception as e:
            self.logger.error(f"SuperTrend hatası: {e}")
            return IndicatorSignal(
                name="SuperTrend",
                value=None,
                signal="NEUTRAL",
                timeframe=config['timeframe'],
                reason=f"Hata: {str(e)}"
            )
    
    def analyze_most(self, close: np.ndarray) -> IndicatorSignal:
        """
        MOST analizi (15m).
        
        Returns:
        --------
        IndicatorSignal
            MOST sinyali
        """
        config = self.config['most']
        
        try:
            most_line, trend = self.calculate_most(
                close,
                length=config['length'],
                percent=config['percent'],
                ma_type=config['ma_type']
            )
            
            current_trend = trend[-1]
            current_most = most_line[-1]
            current_price = close[-1]
            
            # Sinyal belirle
            if current_trend == 1:
                signal = "BUY"
                reason = f"MOST uptrend (MOST: {current_most:.2f})"
            else:
                signal = "SELL"
                reason = f"MOST downtrend (MOST: {current_most:.2f})"
            
            return IndicatorSignal(
                name="MOST",
                value=current_most,
                signal=signal,
                timeframe=config['timeframe'],
                reason=reason
            )
            
        except Exception as e:
            self.logger.error(f"MOST hatası: {e}")
            return IndicatorSignal(
                name="MOST",
                value=None,
                signal="NEUTRAL",
                timeframe=config['timeframe'],
                reason=f"Hata: {str(e)}"
            )
    
    def analyze_qqe_mod(self, close: np.ndarray) -> IndicatorSignal:
        """
        QQE MOD analizi (15m).
        
        Returns:
        --------
        IndicatorSignal
            QQE MOD sinyali
        """
        config = self.config['qqe_mod']
        
        try:
            qqe_line, signal_line = self.qqe_mod(
                close,
                rsi_period=config['rsi_period'],
                rsi_smoothing=config['rsi_smoothing'],
                qqe_factor=config['qqe_factor'],
                threshold=config['threshold']
            )
            
            current_qqe = qqe_line[-1]
            current_signal = signal_line[-1]
            
            # Sinyal belirle
            if current_qqe > current_signal:
                signal = "BUY"
                reason = f"QQE MOD bullish (QQE: {current_qqe:.2f} > Signal: {current_signal:.2f})"
            elif current_qqe < current_signal:
                signal = "SELL"
                reason = f"QQE MOD bearish (QQE: {current_qqe:.2f} < Signal: {current_signal:.2f})"
            else:
                signal = "NEUTRAL"
                reason = "QQE MOD neutral"
            
            return IndicatorSignal(
                name="QQE_MOD",
                value=current_qqe,
                signal=signal,
                timeframe=config['timeframe'],
                reason=reason
            )
            
        except Exception as e:
            self.logger.error(f"QQE MOD hatası: {e}")
            return IndicatorSignal(
                name="QQE_MOD",
                value=None,
                signal="NEUTRAL",
                timeframe=config['timeframe'],
                reason=f"Hata: {str(e)}"
            )
    
    def analyze_rvol(
        self,
        volume: np.ndarray,
        close: np.ndarray
    ) -> IndicatorSignal:
        """
        RVOL analizi (15m).
        
        Returns:
        --------
        IndicatorSignal
            RVOL sinyali
        """
        config = self.config['rvol']
        
        try:
            rvol_values = self.rvol(
                volume,
                close,
                period=config['period']
            )
            
            current_rvol = rvol_values[-1]
            
            # Sinyal belirle
            if current_rvol > config['threshold_high']:
                signal = "BUY"  # Yüksek hacim = güçlü hareket
                reason = f"Yüksek hacim (RVOL: {current_rvol:.2f}x)"
            elif current_rvol < config['threshold_low']:
                signal = "NEUTRAL"
                reason = f"Düşük hacim (RVOL: {current_rvol:.2f}x)"
            else:
                signal = "NEUTRAL"
                reason = f"Normal hacim (RVOL: {current_rvol:.2f}x)"
            
            return IndicatorSignal(
                name="RVOL",
                value=current_rvol,
                signal=signal,
                timeframe=config['timeframe'],
                reason=reason
            )
            
        except Exception as e:
            self.logger.error(f"RVOL hatası: {e}")
            return IndicatorSignal(
                name="RVOL",
                value=None,
                signal="NEUTRAL",
                timeframe=config['timeframe'],
                reason=f"Hata: {str(e)}"
            )
    
    def generate_signal(
        self,
        data_1h: Dict[str, np.ndarray],
        data_15m: Dict[str, np.ndarray],
        timestamp: str
    ) -> TradingSignal:
        """
        Multi-timeframe analiz ile trading sinyali üret.
        
        Parametreler:
        ------------
        data_1h : Dict[str, np.ndarray]
            1 saatlik veri {'high', 'low', 'close'}
        data_15m : Dict[str, np.ndarray]
            15 dakikalık veri {'high', 'low', 'close', 'volume'}
        timestamp : str
            Zaman damgası
        
        Returns:
        --------
        TradingSignal
            Final trading sinyali
        """
        self.logger.info("Sinyal üretimi başlatıldı")
        
        # İndikatör analizleri
        indicators = []
        
        # 1. SuperTrend (1h)
        st_signal = self.analyze_supertrend(
            data_1h['high'],
            data_1h['low'],
            data_1h['close']
        )
        indicators.append(st_signal)
        
        # 2. MOST (15m)
        most_signal = self.analyze_most(data_15m['close'])
        indicators.append(most_signal)
        
        # 3. QQE MOD (15m)
        qqe_signal = self.analyze_qqe_mod(data_15m['close'])
        indicators.append(qqe_signal)
        
        # 4. RVOL (15m)
        rvol_signal = self.analyze_rvol(
            data_15m['volume'],
            data_15m['close']
        )
        indicators.append(rvol_signal)
        
        # Sinyal birleştirme
        final_signal = self._combine_signals(indicators, data_15m['close'][-1])
        final_signal.timestamp = timestamp
        
        self.logger.info(f"Sinyal üretildi: {final_signal.signal_type.value} "
                        f"(Güven: {final_signal.confidence.value})")
        
        return final_signal
    
    def _combine_signals(
        self,
        indicators: List[IndicatorSignal],
        current_price: float
    ) -> TradingSignal:
        """
        İndikatör sinyallerini birleştir.
        
        Parametreler:
        ------------
        indicators : List[IndicatorSignal]
            İndikatör sinyalleri
        current_price : float
            Güncel fiyat
        
        Returns:
        --------
        TradingSignal
            Birleştirilmiş sinyal
        """
        # BUY/SELL sayıları
        buy_count = sum(1 for ind in indicators if ind.signal == "BUY")
        sell_count = sum(1 for ind in indicators if ind.signal == "SELL")
        total_count = len(indicators)
        
        # Confidence score
        if buy_count > sell_count:
            confidence_score = buy_count / total_count
            dominant_signal = "BUY"
        elif sell_count > buy_count:
            confidence_score = sell_count / total_count
            dominant_signal = "SELL"
        else:
            confidence_score = 0.0
            dominant_signal = "NEUTRAL"
        
        # Signal type
        if dominant_signal == "BUY":
            if confidence_score >= 0.75:  # 3/4 veya 4/4
                signal_type = SignalType.STRONG_BUY
            else:
                signal_type = SignalType.BUY
        elif dominant_signal == "SELL":
            if confidence_score >= 0.75:
                signal_type = SignalType.STRONG_SELL
            else:
                signal_type = SignalType.SELL
        else:
            signal_type = SignalType.NEUTRAL
        
        # Confidence level
        if confidence_score >= 0.9:
            confidence_level = ConfidenceLevel.VERY_HIGH
        elif confidence_score >= 0.75:
            confidence_level = ConfidenceLevel.HIGH
        elif confidence_score >= 0.5:
            confidence_level = ConfidenceLevel.MEDIUM
        elif confidence_score >= 0.25:
            confidence_level = ConfidenceLevel.LOW
        else:
            confidence_level = ConfidenceLevel.VERY_LOW
        
        # Stop loss ve take profit hesapla
        stop_loss, take_profit = self._calculate_risk_levels(
            indicators,
            current_price,
            signal_type
        )
        
        # Reasons
        reasons = [ind.reason for ind in indicators if ind.signal != "NEUTRAL"]
        
        return TradingSignal(
            signal_type=signal_type,
            confidence=confidence_level,
            confidence_score=confidence_score,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            indicators=indicators,
            reasons=reasons,
            timestamp=""  # Will be set by caller
        )
    
    def _calculate_risk_levels(
        self,
        indicators: List[IndicatorSignal],
        entry_price: float,
        signal_type: SignalType
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Stop loss ve take profit seviyelerini hesapla.
        
        Parametreler:
        ------------
        indicators : List[IndicatorSignal]
            İndikatör sinyalleri
        entry_price : float
            Giriş fiyatı
        signal_type : SignalType
            Sinyal tipi
        
        Returns:
        --------
        Tuple[Optional[float], Optional[float]]
            (stop_loss, take_profit)
        """
        if signal_type == SignalType.NEUTRAL:
            return None, None
        
        # SuperTrend'den stop loss al
        supertrend = next((ind for ind in indicators if ind.name == "SuperTrend"), None)
        
        if supertrend and supertrend.value:
            # SuperTrend line = natural stop loss
            if signal_type in [SignalType.BUY, SignalType.STRONG_BUY]:
                stop_loss = supertrend.value
                risk = entry_price - stop_loss
                take_profit = entry_price + (risk * self.config['risk']['take_profit_ratio'])
            else:  # SELL
                stop_loss = supertrend.value
                risk = stop_loss - entry_price
                take_profit = entry_price - (risk * self.config['risk']['take_profit_ratio'])
        else:
            # Fallback: % bazlı
            risk_percent = 0.02  # 2%
            if signal_type in [SignalType.BUY, SignalType.STRONG_BUY]:
                stop_loss = entry_price * (1 - risk_percent)
                take_profit = entry_price * (1 + risk_percent * self.config['risk']['take_profit_ratio'])
            else:
                stop_loss = entry_price * (1 + risk_percent)
                take_profit = entry_price * (1 - risk_percent * self.config['risk']['take_profit_ratio'])
        
        return stop_loss, take_profit


if __name__ == "__main__":
    print("Sinyal Üretici - Test")
    print("=" * 60)
    
    # Test için dummy data
    import datetime
    
    np.random.seed(42)
    n_1h = 100
    n_15m = 100
    
    # 1h data
    base_1h = np.cumsum(np.random.randn(n_1h)) + 100
    data_1h = {
        'high': base_1h + np.random.rand(n_1h) * 2,
        'low': base_1h - np.random.rand(n_1h) * 2,
        'close': base_1h
    }
    
    # 15m data
    base_15m = np.cumsum(np.random.randn(n_15m) * 0.5) + 100
    data_15m = {
        'high': base_15m + np.random.rand(n_15m),
        'low': base_15m - np.random.rand(n_15m),
        'close': base_15m,
        'volume': np.random.rand(n_15m) * 1000000
    }
    
    try:
        # SignalGenerator oluştur
        generator = SignalGenerator()
        print("✅ SignalGenerator oluşturuldu")
        
        # Sinyal üret
        signal = generator.generate_signal(
            data_1h=data_1h,
            data_15m=data_15m,
            timestamp=datetime.datetime.now().isoformat()
        )
        
        print(f"\n📊 Sinyal Sonucu:")
        print(f"   Sinyal: {signal.signal_type.value}")
        print(f"   Güven: {signal.confidence.value} ({signal.confidence_score:.2%})")
        print(f"   Entry: ${signal.entry_price:.2f}")
        print(f"   Stop Loss: ${signal.stop_loss:.2f}" if signal.stop_loss else "   Stop Loss: None")
        print(f"   Take Profit: ${signal.take_profit:.2f}" if signal.take_profit else "   Take Profit: None")
        
        print(f"\n📈 İndikatörler:")
        for ind in signal.indicators:
            print(f"   {ind.name:12s} ({ind.timeframe}): {ind.signal:8s} - {ind.reason}")
        
        print("\n" + "=" * 60)
        print("✅ Test başarılı!")
        
    except Exception as e:
        print(f"\n❌ Hata: {e}")
        import traceback
        traceback.print_exc()