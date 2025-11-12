"""
Trading Bot - Rate Limiter
===========================

Binance API rate limiting ve request throttling yönetimi.

Binance rate limit: 1200 req/min (weight-based)
Her endpoint farklı weight değerine sahip.

Özellikler:
    - Weight-based rate limiting
    - Request queue management
    - Auto wait on limit
    - Statistics tracking

Örnek Kullanım:
    >>> limiter = RateLimiter(max_weight_per_minute=1200)
    >>> limiter.wait_if_needed(weight=10)
    >>> # Request yap
    >>> limiter.add_request(weight=10)

Author: Trading Bot Team
Version: 1.0
Python: 3.10+
"""

from __future__ import annotations
import time
from typing import Optional, Dict, Any
from collections import deque
from threading import Lock
from datetime import datetime, timedelta


class RateLimitError(Exception):
    """Rate limit aşıldığında fırlatılan exception."""
    pass


class RateLimiter:
    """
    Weight-based rate limiter.
    
    Binance API için tasarlanmış, dakika bazında weight limiti uygular.
    Thread-safe implementasyon.
    
    Attributes:
        max_weight_per_minute (int): Dakikada maksimum weight
        window_seconds (int): Rolling window süresi (saniye)
        requests (deque): Son requestlerin geçmişi
        total_weight (int): Pencere içindeki toplam weight
    """
    
    def __init__(
        self,
        max_weight_per_minute: int = 1200,
        window_seconds: int = 60,
        strict_mode: bool = False
    ):
        """
        Initialize rate limiter.
        
        Args:
            max_weight_per_minute: Dakikada maksimum weight (default: 1200)
            window_seconds: Rolling window süresi (default: 60)
            strict_mode: True ise limit aşımında exception fırlat
        """
        self.max_weight = max_weight_per_minute
        self.window_seconds = window_seconds
        self.strict_mode = strict_mode
        
        # Request history (timestamp, weight)
        self.requests: deque = deque()
        self.total_weight = 0
        
        # Thread safety
        self._lock = Lock()
        
        # Statistics
        self._stats = {
            'total_requests': 0,
            'total_weight_used': 0,
            'waits': 0,
            'rejected': 0
        }
    
    def wait_if_needed(self, weight: int = 1) -> float:
        """
        Gerekirse rate limit için bekle.
        
        Args:
            weight: Request weight değeri
            
        Returns:
            Beklenen süre (saniye), 0 ise beklenmedi
            
        Raises:
            RateLimitError: Strict mode'da ve limit aşıldıysa
        """
        with self._lock:
            # Eski requestleri temizle
            self._cleanup_old_requests()
            
            # Limit kontrolü
            if self.total_weight + weight > self.max_weight:
                if self.strict_mode:
                    self._stats['rejected'] += 1
                    raise RateLimitError(
                        f"Rate limit aşıldı: {self.total_weight + weight}/{self.max_weight}"
                    )
                
                # En eski request'in silinmesini bekle
                wait_time = self._calculate_wait_time(weight)
                
                if wait_time > 0:
                    self._stats['waits'] += 1
                    return wait_time
            
            return 0.0
    
    def add_request(self, weight: int = 1) -> None:
        """
        Request'i kaydet ve weight'i ekle.
        
        Args:
            weight: Request weight değeri
        """
        with self._lock:
            now = time.time()
            
            # Request'i ekle
            self.requests.append((now, weight))
            self.total_weight += weight
            
            # İstatistikleri güncelle
            self._stats['total_requests'] += 1
            self._stats['total_weight_used'] += weight
            
            # Eski requestleri temizle
            self._cleanup_old_requests()
    
    def _cleanup_old_requests(self) -> None:
        """Window dışındaki eski requestleri temizle."""
        now = time.time()
        cutoff_time = now - self.window_seconds
        
        while self.requests and self.requests[0][0] < cutoff_time:
            _, weight = self.requests.popleft()
            self.total_weight -= weight
    
    def _calculate_wait_time(self, new_weight: int) -> float:
        """
        Yeni request için gereken bekleme süresini hesapla.
        
        Args:
            new_weight: Eklenecek weight
            
        Returns:
            Bekleme süresi (saniye)
        """
        if not self.requests:
            return 0.0
        
        # Kaç weight'in düşmesi gerekiyor
        needed_weight = (self.total_weight + new_weight) - self.max_weight
        
        if needed_weight <= 0:
            return 0.0
        
        # Weight düşene kadar bekle
        removed_weight = 0
        oldest_timestamp = None
        
        for timestamp, weight in self.requests:
            removed_weight += weight
            if removed_weight >= needed_weight:
                oldest_timestamp = timestamp
                break
        
        if oldest_timestamp is None:
            # Tüm requestler düşse bile yetmez
            oldest_timestamp = self.requests[-1][0]
        
        # Bekleme süresi hesapla
        wait_until = oldest_timestamp + self.window_seconds
        wait_time = max(0, wait_until - time.time())
        
        return wait_time
    
    def get_current_usage(self) -> Dict[str, Any]:
        """
        Mevcut kullanım bilgilerini al.
        
        Returns:
            Kullanım istatistikleri
        """
        with self._lock:
            self._cleanup_old_requests()
            
            return {
                'current_weight': self.total_weight,
                'max_weight': self.max_weight,
                'usage_percentage': (self.total_weight / self.max_weight * 100),
                'requests_in_window': len(self.requests),
                'available_weight': self.max_weight - self.total_weight
            }
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Toplam istatistikleri al.
        
        Returns:
            İstatistik bilgileri
        """
        with self._lock:
            return {
                **self._stats,
                **self.get_current_usage()
            }
    
    def reset_statistics(self) -> None:
        """İstatistikleri sıfırla (history değil)."""
        with self._lock:
            self._stats = {
                'total_requests': 0,
                'total_weight_used': 0,
                'waits': 0,
                'rejected': 0
            }
    
    def reset(self) -> None:
        """Rate limiter'ı tamamen sıfırla (history dahil)."""
        with self._lock:
            self.requests.clear()
            self.total_weight = 0
            self.reset_statistics()
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"RateLimiter(max={self.max_weight}, "
            f"current={self.total_weight}, "
            f"usage={self.total_weight/self.max_weight*100:.1f}%)"
        )


if __name__ == "__main__":
    # Test kodu
    print("🧪 RateLimiter Test")
    print("-" * 50)
    
    try:
        # Test 1: Normal kullanım
        limiter = RateLimiter(max_weight_per_minute=100, window_seconds=5)
        print(f"✅ Limiter oluşturuldu: {limiter}")
        
        # Test 2: Request ekleme
        for i in range(5):
            wait_time = limiter.wait_if_needed(weight=10)
            if wait_time > 0:
                print(f"⏳ Bekleniyor: {wait_time:.2f}s")
                time.sleep(wait_time)
            
            limiter.add_request(weight=10)
            usage = limiter.get_current_usage()
            print(f"  Request #{i+1}: {usage['current_weight']}/{usage['max_weight']} "
                  f"({usage['usage_percentage']:.1f}%)")
        
        # Test 3: İstatistikler
        stats = limiter.get_statistics()
        print(f"\n📊 İstatistikler:")
        print(f"  Total requests: {stats['total_requests']}")
        print(f"  Total weight: {stats['total_weight_used']}")
        print(f"  Waits: {stats['waits']}")
        
        # Test 4: Limit aşımı
        print(f"\n🔥 Limit aşımı testi...")
        for i in range(10):
            wait_time = limiter.wait_if_needed(weight=20)
            if wait_time > 0:
                print(f"⏳ Bekleme gerekli: {wait_time:.2f}s")
                # Gerçek senaryoda time.sleep(wait_time) yapılır
                break
            limiter.add_request(weight=20)
        
        # Test 5: Strict mode
        print(f"\n🚨 Strict mode testi...")
        strict_limiter = RateLimiter(max_weight_per_minute=50, strict_mode=True)
        try:
            for i in range(10):
                strict_limiter.wait_if_needed(weight=20)
                strict_limiter.add_request(weight=20)
        except RateLimitError as e:
            print(f"✅ Rate limit exception yakalandı: {e}")
        
        # Test 6: Reset
        limiter.reset()
        usage = limiter.get_current_usage()
        print(f"\n♻️ Reset sonrası: {usage['current_weight']}/{usage['max_weight']}")
        
        print("\n🎉 Tüm testler başarılı!")
        
    except Exception as e:
        print(f"❌ Test hatası: {e}")
        import traceback
        traceback.print_exc()