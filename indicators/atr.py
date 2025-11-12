"""
ATR (Average True Range) İndikatörü
====================================

J. Welles Wilder Jr. tarafından geliştirilen volatilite indikatörü.
True Range'in hareketli ortalamasıdır ve piyasa volatilitesini ölçer.

Özellikler:
- True Range hesaplama
- Çoklu yumuşatma metodu: RMA (Wilder's), SMA, EMA, WMA
- Stop loss seviyeleri hesaplama
- BaseIndicator'dan türetilmiş
- Type hints ve Türkçe dokümantasyon

Kullanım Alanları:
- Volatilite ölçümü
- Stop loss seviyesi belirleme
- Position sizing
- Trend güç analizi

Yazar: Trading Bot Sistemi
Versiyon: 1.0.0
"""

import numpy as np
from typing import Union, Tuple, Optional
from base_indicator import BaseIndicator, InsufficientDataError


class ATR(BaseIndicator):
    """
    Average True Range (ATR) İndikatörü.
    
    Piyasa volatilitesini ölçen klasik teknik indikatör.
    """
    
    def __init__(
        self,
        period: int = 14,
        smoothing: str = "RMA",
        multiplier: float = 1.0
    ):
        """
        ATR indikatörü başlatıcı.
        
        Parametreler:
        ------------
        period : int, default=14
            ATR periyodu
        smoothing : str, default="RMA"
            Yumuşatma metodu: "RMA", "SMA", "EMA", "WMA"
        multiplier : float, default=1.0
            ATR çarpanı (stop loss için)
        """
        super().__init__(name=f"ATR({period})")
        
        self.period = period
        self.smoothing = smoothing.upper()
        self.multiplier = multiplier
        
        # Validasyon
        self.validate_parameter(period, min_value=1, name="period")
        self.validate_parameter(multiplier, min_value=0, name="multiplier")
        
        if self.smoothing not in ["RMA", "SMA", "EMA", "WMA"]:
            raise ValueError(
                f"Geçersiz smoothing metodu: {smoothing}. "
                f"Geçerli değerler: RMA, SMA, EMA, WMA"
            )
    
    def calculate_true_range(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray
    ) -> np.ndarray:
        """
        True Range hesapla.
        
        True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
        
        Parametreler:
        ------------
        high : np.ndarray
            Yüksek fiyatlar
        low : np.ndarray
            Düşük fiyatlar
        close : np.ndarray
            Kapanış fiyatları
        
        Returns:
        --------
        np.ndarray
            True Range değerleri
        """
        # High - Low
        hl = high - low
        
        # |High - Prev Close|
        hc = np.abs(high - np.roll(close, 1))
        
        # |Low - Prev Close|
        lc = np.abs(low - np.roll(close, 1))
        
        # İlk bar için önceki close yok
        hc[0] = 0
        lc[0] = 0
        
        # True Range = max(hl, hc, lc)
        tr = np.maximum(hl, np.maximum(hc, lc))
        
        return tr
    
    def smooth_rma(self, data: np.ndarray, period: int) -> np.ndarray:
        """
        Wilder's Smoothing (RMA - Running Moving Average).
        
        RMA[i] = (RMA[i-1] * (period-1) + data[i]) / period
        
        Parametreler:
        ------------
        data : np.ndarray
            Yumuşatılacak veri
        period : int
            Periyot
        
        Returns:
        --------
        np.ndarray
            RMA değerleri
        """
        alpha = 1.0 / period
        rma = np.zeros_like(data)
        
        # İlk değer: SMA
        rma[period-1] = np.mean(data[:period])
        
        # RMA hesaplama
        for i in range(period, len(data)):
            rma[i] = alpha * data[i] + (1 - alpha) * rma[i-1]
        
        # İlk değerleri doldur
        rma[:period-1] = rma[period-1]
        
        return rma
    
    def smooth_sma(self, data: np.ndarray, period: int) -> np.ndarray:
        """
        Simple Moving Average (SMA).
        
        Parametreler:
        ------------
        data : np.ndarray
            Yumuşatılacak veri
        period : int
            Periyot
        
        Returns:
        --------
        np.ndarray
            SMA değerleri
        """
        sma = np.zeros_like(data)
        
        for i in range(period - 1, len(data)):
            sma[i] = np.mean(data[i-period+1:i+1])
        
        # İlk değerleri doldur
        sma[:period-1] = sma[period-1]
        
        return sma
    
    def smooth_ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """
        Exponential Moving Average (EMA).
        
        Parametreler:
        ------------
        data : np.ndarray
            Yumuşatılacak veri
        period : int
            Periyot
        
        Returns:
        --------
        np.ndarray
            EMA değerleri
        """
        alpha = 2.0 / (period + 1)
        ema = np.zeros_like(data)
        ema[0] = data[0]
        
        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i-1]
        
        return ema
    
    def smooth_wma(self, data: np.ndarray, period: int) -> np.ndarray:
        """
        Weighted Moving Average (WMA).
        
        Parametreler:
        ------------
        data : np.ndarray
            Yumuşatılacak veri
        period : int
            Periyot
        
        Returns:
        --------
        np.ndarray
            WMA değerleri
        """
        weights = np.arange(1, period + 1)
        wma = np.zeros_like(data)
        
        for i in range(period - 1, len(data)):
            wma[i] = np.sum(data[i-period+1:i+1] * weights) / np.sum(weights)
        
        # İlk değerleri doldur
        wma[:period-1] = wma[period-1]
        
        return wma
    
    def calculate(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray
    ) -> np.ndarray:
        """
        ATR hesapla.
        
        Parametreler:
        ------------
        high : np.ndarray
            Yüksek fiyatlar
        low : np.ndarray
            Düşük fiyatlar
        close : np.ndarray
            Kapanış fiyatları
        
        Returns:
        --------
        np.ndarray
            ATR değerleri
        
        Raises:
        -------
        InsufficientDataError
            Yetersiz veri
        ValueError
            Geçersiz veri
        """
        # Validasyon
        high = self.validate_data(high, name="high")
        low = self.validate_data(low, name="low")
        close = self.validate_data(close, name="close")
        
        self.validate_arrays_equal_length(high, low, close, names=["high", "low", "close"])
        
        # True Range hesapla
        tr = self.calculate_true_range(high, low, close)
        
        # Yumuşatma uygula
        if self.smoothing == "RMA":
            atr = self.smooth_rma(tr, self.period)
        elif self.smoothing == "SMA":
            atr = self.smooth_sma(tr, self.period)
        elif self.smoothing == "EMA":
            atr = self.smooth_ema(tr, self.period)
        else:  # WMA
            atr = self.smooth_wma(tr, self.period)
        
        # Önbelleğe al
        self.cache_result(atr, len(close))
        
        return atr
    
    def calculate_stop_loss(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        multiplier: Optional[float] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        ATR bazlı stop loss seviyeleri hesapla.
        
        Parametreler:
        ------------
        high : np.ndarray
            Yüksek fiyatlar
        low : np.ndarray
            Düşük fiyatlar
        close : np.ndarray
            Kapanış fiyatları
        multiplier : Optional[float]
            ATR çarpanı (None ise self.multiplier kullanılır)
        
        Returns:
        --------
        Tuple[np.ndarray, np.ndarray]
            (long_stop, short_stop)
            - long_stop: Long pozisyon için stop loss (close - ATR*multiplier)
            - short_stop: Short pozisyon için stop loss (close + ATR*multiplier)
        """
        # ATR hesapla
        atr = self.calculate(high, low, close)
        
        # Multiplier
        mult = multiplier if multiplier is not None else self.multiplier
        
        # Stop loss seviyeleri
        long_stop = close - (atr * mult)
        short_stop = close + (atr * mult)
        
        return long_stop, short_stop
    
    def get_required_length(self) -> int:
        """Minimum veri ihtiyacı."""
        return self.period
    
    def get_info(self) -> dict:
        """İndikatör bilgileri."""
        info = super().get_info()
        info.update({
            'period': self.period,
            'smoothing': self.smoothing,
            'multiplier': self.multiplier
        })
        return info


# Kolay kullanım fonksiyonları
def calculate_atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 14,
    smoothing: str = "RMA"
) -> np.ndarray:
    """
    ATR hesaplama (fonksiyonel interface).
    
    Parametreler:
    ------------
    high, low, close : np.ndarray
        OHLC verisi
    period : int, default=14
        ATR periyodu
    smoothing : str, default="RMA"
        Yumuşatma metodu
    
    Returns:
    --------
    np.ndarray
        ATR değerleri
    
    Örnek:
    ------
    >>> import numpy as np
    >>> high = np.array([102, 104, 103, 105, 107])
    >>> low = np.array([98, 100, 99, 101, 103])
    >>> close = np.array([100, 102, 101, 103, 105])
    >>> atr = calculate_atr(high, low, close, period=3)
    >>> print(atr[-1])
    """
    indicator = ATR(period=period, smoothing=smoothing)
    return indicator.calculate(high, low, close)


def calculate_atr_stop_loss(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 14,
    multiplier: float = 1.5,
    smoothing: str = "RMA"
) -> Tuple[np.ndarray, np.ndarray]:
    """
    ATR bazlı stop loss seviyeleri (fonksiyonel interface).
    
    Parametreler:
    ------------
    high, low, close : np.ndarray
        OHLC verisi
    period : int, default=14
        ATR periyodu
    multiplier : float, default=1.5
        ATR çarpanı
    smoothing : str, default="RMA"
        Yumuşatma metodu
    
    Returns:
    --------
    Tuple[np.ndarray, np.ndarray]
        (long_stop, short_stop) seviyeleri
    
    Örnek:
    ------
    >>> long_stop, short_stop = calculate_atr_stop_loss(high, low, close)
    >>> print(f"Long stop: {long_stop[-1]:.2f}")
    >>> print(f"Short stop: {short_stop[-1]:.2f}")
    """
    indicator = ATR(period=period, smoothing=smoothing, multiplier=multiplier)
    return indicator.calculate_stop_loss(high, low, close)


if __name__ == "__main__":
    print("ATR İndikatörü - Test")
    print("=" * 60)
    
    # Test verisi oluştur
    np.random.seed(42)
    n = 50
    base_price = 100
    
    # OHLC verisi
    close = np.cumsum(np.random.randn(n) * 0.5) + base_price
    high = close + np.random.rand(n) * 2
    low = close - np.random.rand(n) * 2
    
    try:
        # Test 1: Temel ATR hesaplama
        print("\n📊 Test 1: Temel ATR (RMA)")
        print("-" * 60)
        atr_rma = ATR(period=14, smoothing="RMA")
        result = atr_rma.calculate(high, low, close)
        
        print(f"✅ ATR hesaplandı")
        print(f"   Son 5 değer: {result[-5:]}")
        print(f"   Ortalama ATR: {np.mean(result):.2f}")
        print(f"   İndikatör bilgileri: {atr_rma.get_info()}")
        
        # Test 2: Farklı smoothing metodları
        print("\n📊 Test 2: Farklı Yumuşatma Metodları")
        print("-" * 60)
        
        methods = ["RMA", "SMA", "EMA", "WMA"]
        for method in methods:
            atr = ATR(period=14, smoothing=method)
            result = atr.calculate(high, low, close)
            print(f"   {method:4s}: Son değer = {result[-1]:.2f}")
        
        # Test 3: Stop loss seviyeleri
        print("\n📊 Test 3: Stop Loss Seviyeleri")
        print("-" * 60)
        
        atr = ATR(period=14, multiplier=1.5)
        long_stop, short_stop = atr.calculate_stop_loss(high, low, close)
        
        print(f"✅ Stop loss seviyeleri hesaplandı")
        print(f"   Güncel fiyat: {close[-1]:.2f}")
        print(f"   Long stop:    {long_stop[-1]:.2f} (-%{((close[-1]-long_stop[-1])/close[-1]*100):.2f})")
        print(f"   Short stop:   {short_stop[-1]:.2f} (+%{((short_stop[-1]-close[-1])/close[-1]*100):.2f})")
        
        # Test 4: Fonksiyonel interface
        print("\n📊 Test 4: Fonksiyonel Interface")
        print("-" * 60)
        
        atr_values = calculate_atr(high, low, close, period=10)
        long, short = calculate_atr_stop_loss(high, low, close, period=10, multiplier=2.0)
        
        print(f"✅ Fonksiyonel interface çalıştı")
        print(f"   ATR(10): {atr_values[-1]:.2f}")
        print(f"   Long stop (2x): {long[-1]:.2f}")
        print(f"   Short stop (2x): {short[-1]:.2f}")
        
        # Test 5: Hata yönetimi
        print("\n📊 Test 5: Hata Yönetimi")
        print("-" * 60)
        
        try:
            short_data = np.array([100, 101, 102])
            atr_rma.calculate(short_data, short_data, short_data)
        except InsufficientDataError as e:
            print(f"   ✅ Yetersiz veri hatası yakalandı: {e}")
        
        try:
            atr_invalid = ATR(period=14, smoothing="INVALID")
        except ValueError as e:
            print(f"   ✅ Geçersiz parametre hatası yakalandı")
        
        print("\n" + "=" * 60)
        print("✅ Tüm testler başarılı!")
        
    except Exception as e:
        print(f"\n❌ Hata: {e}")
        import traceback
        traceback.print_exc()