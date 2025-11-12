"""
Temel İndikatör Sınıfı (Base Indicator)
========================================

Tüm teknik indikatörler için soyut temel sınıf (abstract base class).
Ortak interface, validasyon ve hata yönetimi sağlar.

Özellikler:
- Soyut calculate() metodu (her indikatör kendi implementasyonunu yapar)
- Veri validasyonu ve boyut kontrolü
- Hata yönetimi (InsufficientDataError)
- Ortak yardımcı metodlar
- Type hints ve dokümantasyon

Yazar: Trading Bot Sistemi
Versiyon: 1.0.0
"""

from abc import ABC, abstractmethod
from typing import Optional, Union, Tuple, Dict, Any
import numpy as np


class InsufficientDataError(Exception):
    """Hesaplama için yetersiz veri hatası."""
    pass


class BaseIndicator(ABC):
    """
    Temel İndikatör Sınıfı.
    
    Tüm teknik indikatörler bu sınıftan türetilir ve calculate() metodunu
    implement etmek zorundadır.
    
    Örnek Kullanım:
    --------------
    ```python
    class MyIndicator(BaseIndicator):
        def calculate(self, close: np.ndarray) -> np.ndarray:
            # İndikatör hesaplaması
            return result
        
        def get_required_length(self) -> int:
            return 14  # Minimum veri ihtiyacı
    ```
    """
    
    def __init__(self, name: str = "BaseIndicator"):
        """
        Base indicator başlatıcı.
        
        Parametreler:
        ------------
        name : str
            İndikatör adı (log ve debug için)
        """
        self.name = name
        self._last_result = None
        self._last_input_length = 0
    
    @abstractmethod
    def calculate(self, *args, **kwargs) -> Union[np.ndarray, Tuple]:
        """
        İndikatör hesaplama metodu (abstract).
        
        Her indikatör bu metodu kendi mantığı ile implement etmelidir.
        
        Returns:
        --------
        Union[np.ndarray, Tuple]
            İndikatör değerleri veya tuple (birden fazla çıktı için)
        
        Raises:
        -------
        InsufficientDataError
            Yetersiz veri durumunda
        """
        raise NotImplementedError(f"{self.name}.calculate() metodu implement edilmemiş")
    
    @abstractmethod
    def get_required_length(self) -> int:
        """
        Minimum veri ihtiyacını döndür.
        
        Returns:
        --------
        int
            Hesaplama için minimum gerekli veri sayısı
        """
        raise NotImplementedError(f"{self.name}.get_required_length() metodu implement edilmemiş")
    
    def validate_data(
        self,
        data: Union[np.ndarray, list],
        min_length: Optional[int] = None,
        name: str = "data"
    ) -> np.ndarray:
        """
        Veri validasyonu ve dönüşüm.
        
        Parametreler:
        ------------
        data : Union[np.ndarray, list]
            Validasyon yapılacak veri
        min_length : Optional[int]
            Minimum veri uzunluğu (None ise get_required_length() kullanılır)
        name : str
            Veri adı (hata mesajları için)
        
        Returns:
        --------
        np.ndarray
            Validate edilmiş numpy array
        
        Raises:
        -------
        InsufficientDataError
            Veri yetersiz ise
        ValueError
            Veri geçersiz ise
        """
        # List ise numpy array'e çevir
        if not isinstance(data, np.ndarray):
            try:
                data = np.array(data, dtype=np.float64)
            except Exception as e:
                raise ValueError(f"{name} numpy array'e çevrilemedi: {e}")
        
        # Boş veri kontrolü
        if len(data) == 0:
            raise InsufficientDataError(f"{name} boş olamaz")
        
        # Minimum uzunluk kontrolü
        if min_length is None:
            min_length = self.get_required_length()
        
        if len(data) < min_length:
            raise InsufficientDataError(
                f"{self.name} için {name} en az {min_length} veri noktası gerektiriyor, "
                f"{len(data)} veri noktası sağlandı"
            )
        
        # NaN ve Inf kontrolü
        if np.any(np.isnan(data)):
            raise ValueError(f"{name} NaN değer içeriyor")
        
        if np.any(np.isinf(data)):
            raise ValueError(f"{name} sonsuz (inf) değer içeriyor")
        
        return data
    
    def validate_arrays_equal_length(self, *arrays: np.ndarray, names: Optional[list] = None):
        """
        Birden fazla array'in eşit uzunlukta olduğunu kontrol et.
        
        Parametreler:
        ------------
        *arrays : np.ndarray
            Kontrol edilecek array'ler
        names : Optional[list]
            Array isimleri (hata mesajı için)
        
        Raises:
        -------
        ValueError
            Array'ler farklı uzunlukta ise
        """
        if len(arrays) < 2:
            return
        
        first_length = len(arrays[0])
        
        for i, arr in enumerate(arrays[1:], 1):
            if len(arr) != first_length:
                if names and len(names) > i:
                    name1 = names[0]
                    name2 = names[i]
                else:
                    name1 = f"array[0]"
                    name2 = f"array[{i}]"
                
                raise ValueError(
                    f"{name1} ve {name2} eşit uzunlukta olmalı. "
                    f"{name1}={first_length}, {name2}={len(arr)}"
                )
    
    def validate_parameter(
        self,
        value: Union[int, float],
        min_value: Optional[Union[int, float]] = None,
        max_value: Optional[Union[int, float]] = None,
        name: str = "parametre"
    ):
        """
        Parametre değerini validasyon et.
        
        Parametreler:
        ------------
        value : Union[int, float]
            Kontrol edilecek değer
        min_value : Optional[Union[int, float]]
            Minimum değer (dahil)
        max_value : Optional[Union[int, float]]
            Maksimum değer (dahil)
        name : str
            Parametre adı (hata mesajı için)
        
        Raises:
        -------
        ValueError
            Değer geçersiz ise
        """
        if min_value is not None and value < min_value:
            raise ValueError(f"{name} en az {min_value} olmalı, {value} verildi")
        
        if max_value is not None and value > max_value:
            raise ValueError(f"{name} en fazla {max_value} olmalı, {value} verildi")
    
    def cache_result(self, result: Any, input_length: int):
        """
        Son hesaplama sonucunu önbelleğe al.
        
        Parametreler:
        ------------
        result : Any
            Önbelleğe alınacak sonuç
        input_length : int
            Girdi verisi uzunluğu
        """
        self._last_result = result
        self._last_input_length = input_length
    
    def get_cached_result(self) -> Tuple[Optional[Any], int]:
        """
        Önbellekteki son sonucu getir.
        
        Returns:
        --------
        Tuple[Optional[Any], int]
            (son_sonuç, girdi_uzunluğu)
        """
        return self._last_result, self._last_input_length
    
    def clear_cache(self):
        """Önbelleği temizle."""
        self._last_result = None
        self._last_input_length = 0
    
    def __repr__(self) -> str:
        """String temsili."""
        return f"{self.__class__.__name__}(name='{self.name}')"
    
    def __str__(self) -> str:
        """Kullanıcı dostu string."""
        return f"{self.name} İndikatörü"
    
    def get_info(self) -> Dict[str, Any]:
        """
        İndikatör bilgilerini döndür.
        
        Returns:
        --------
        Dict[str, Any]
            İndikatör bilgileri (isim, minimum uzunluk, vb.)
        """
        return {
            'name': self.name,
            'required_length': self.get_required_length(),
            'has_cached_result': self._last_result is not None,
            'last_input_length': self._last_input_length
        }


class MultiOutputIndicator(BaseIndicator):
    """
    Birden fazla çıktı üreten indikatörler için base class.
    
    Örneğin: SuperTrend (trend_line + direction), 
             QQE (fast_line + slow_line + signal)
    """
    
    def __init__(self, name: str = "MultiOutputIndicator", output_names: Optional[list] = None):
        """
        Multi-output indicator başlatıcı.
        
        Parametreler:
        ------------
        name : str
            İndikatör adı
        output_names : Optional[list]
            Çıktı isimleri (örn: ['line', 'direction'])
        """
        super().__init__(name)
        self.output_names = output_names or []
    
    def validate_output_count(self, outputs: Tuple, expected_count: int):
        """
        Çıktı sayısını kontrol et.
        
        Parametreler:
        ------------
        outputs : Tuple
            Çıktı tuple'ı
        expected_count : int
            Beklenen çıktı sayısı
        
        Raises:
        -------
        ValueError
            Çıktı sayısı yanlış ise
        """
        if len(outputs) != expected_count:
            raise ValueError(
                f"{self.name} {expected_count} çıktı üretmeli, "
                f"{len(outputs)} çıktı üretildi"
            )
    
    def get_info(self) -> Dict[str, Any]:
        """Multi-output indikatör bilgileri."""
        info = super().get_info()
        info['output_names'] = self.output_names
        info['output_count'] = len(self.output_names)
        return info


# Kullanım örnekleri
if __name__ == "__main__":
    print("BaseIndicator - Temel İndikatör Sınıfı")
    print("=" * 50)
    
    # Örnek basit indikatör
    class SimpleMA(BaseIndicator):
        """Basit Moving Average örneği."""
        
        def __init__(self, period: int = 14):
            super().__init__(name=f"SMA({period})")
            self.period = period
        
        def calculate(self, close: np.ndarray) -> np.ndarray:
            # Veri validasyonu
            close = self.validate_data(close, name="close")
            
            # SMA hesaplama
            sma = np.zeros_like(close)
            for i in range(self.period - 1, len(close)):
                sma[i] = np.mean(close[i-self.period+1:i+1])
            
            # İlk değerleri doldur
            sma[:self.period-1] = sma[self.period-1]
            
            # Sonucu önbelleğe al
            self.cache_result(sma, len(close))
            
            return sma
        
        def get_required_length(self) -> int:
            return self.period
    
    # Test
    try:
        # SMA oluştur
        sma = SimpleMA(period=5)
        print(f"✅ İndikatör oluşturuldu: {sma}")
        print(f"   Bilgiler: {sma.get_info()}")
        
        # Test verisi
        data = np.array([10, 11, 12, 13, 14, 15, 16, 17, 18, 19])
        print(f"\n📊 Test verisi: {data}")
        
        # Hesapla
        result = sma.calculate(data)
        print(f"\n✅ SMA sonucu: {result}")
        
        # Önbellekten getir
        cached, length = sma.get_cached_result()
        print(f"\n💾 Önbellek: {length} veri noktası")
        
        # Yetersiz veri testi
        print("\n🧪 Yetersiz veri testi...")
        try:
            short_data = np.array([10, 11, 12])
            sma.calculate(short_data)
        except InsufficientDataError as e:
            print(f"   ✅ Hata yakalandı: {e}")
        
        print("\n" + "="*50)
        print("✅ Tüm testler başarılı!")
        
    except Exception as e:
        print(f"❌ Hata: {e}")