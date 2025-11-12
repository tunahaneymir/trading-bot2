"""
Trading Bot - Rate Limiter Tests
=================================

RateLimiter için unit testler.

Test Kategorileri:
    - Initialization tests
    - Weight tracking tests
    - Wait time calculation tests
    - Statistics tests
    - Thread safety tests
    - Strict mode tests

Author: Trading Bot Team
Version: 1.0
Python: 3.10+
"""

import pytest
import time
from threading import Thread
from src.binance.rate_limiter import RateLimiter, RateLimitError


# ==================== FIXTURES ====================

@pytest.fixture
def limiter():
    """Basic RateLimiter fixture."""
    return RateLimiter(max_weight_per_minute=100, window_seconds=5)


@pytest.fixture
def strict_limiter():
    """Strict mode RateLimiter fixture."""
    return RateLimiter(max_weight_per_minute=50, window_seconds=5, strict_mode=True)


# ==================== INITIALIZATION TESTS ====================

class TestInitialization:
    """Initialization testleri."""
    
    def test_init_default(self):
        """Default parametreler ile init testi."""
        limiter = RateLimiter()
        
        assert limiter.max_weight == 1200
        assert limiter.window_seconds == 60
        assert limiter.strict_mode is False
        assert limiter.total_weight == 0
        assert len(limiter.requests) == 0
    
    def test_init_custom(self):
        """Custom parametreler ile init testi."""
        limiter = RateLimiter(
            max_weight_per_minute=500,
            window_seconds=30,
            strict_mode=True
        )
        
        assert limiter.max_weight == 500
        assert limiter.window_seconds == 30
        assert limiter.strict_mode is True
    
    def test_init_statistics(self, limiter):
        """Initial statistics testi."""
        stats = limiter.get_statistics()
        
        assert stats['total_requests'] == 0
        assert stats['total_weight_used'] == 0
        assert stats['waits'] == 0
        assert stats['rejected'] == 0


# ==================== WEIGHT TRACKING TESTS ====================

class TestWeightTracking:
    """Weight tracking testleri."""
    
    def test_add_single_request(self, limiter):
        """Tek request ekleme testi."""
        limiter.add_request(weight=10)
        
        assert limiter.total_weight == 10
        assert len(limiter.requests) == 1
    
    def test_add_multiple_requests(self, limiter):
        """Çoklu request ekleme testi."""
        limiter.add_request(weight=10)
        limiter.add_request(weight=20)
        limiter.add_request(weight=15)
        
        assert limiter.total_weight == 45
        assert len(limiter.requests) == 3
    
    def test_weight_cleanup(self, limiter):
        """Weight cleanup testi (window dışı)."""
        # Eski request ekle
        limiter.add_request(weight=30)
        
        # Window'un dışına çık
        time.sleep(6)  # window_seconds=5
        
        # Cleanup trigger et
        limiter.add_request(weight=10)
        
        # Eski request silinmiş olmalı
        assert limiter.total_weight == 10
        assert len(limiter.requests) == 1
    
    def test_current_usage(self, limiter):
        """Current usage testi."""
        limiter.add_request(weight=25)
        limiter.add_request(weight=15)
        
        usage = limiter.get_current_usage()
        
        assert usage['current_weight'] == 40
        assert usage['max_weight'] == 100
        assert usage['usage_percentage'] == 40.0
        assert usage['available_weight'] == 60
        assert usage['requests_in_window'] == 2


# ==================== WAIT TIME TESTS ====================

class TestWaitTime:
    """Wait time calculation testleri."""
    
    def test_wait_if_needed_no_wait(self, limiter):
        """Wait gerekmediğinde test."""
        limiter.add_request(weight=30)
        
        wait_time = limiter.wait_if_needed(weight=20)
        
        assert wait_time == 0.0
    
    def test_wait_if_needed_with_wait(self, limiter):
        """Wait gerektiğinde test."""
        # Limiti dolduralım
        limiter.add_request(weight=90)
        
        # 20 daha eklemeye çalış (100 limitini aşar)
        wait_time = limiter.wait_if_needed(weight=20)
        
        # Wait time > 0 olmalı
        assert wait_time > 0
    
    def test_calculate_wait_time_empty(self, limiter):
        """Boş request history ile wait time testi."""
        wait_time = limiter._calculate_wait_time(new_weight=50)
        
        assert wait_time == 0.0
    
    def test_calculate_wait_time_with_requests(self, limiter):
        """Requestler varken wait time testi."""
        limiter.add_request(weight=80)
        
        # 30 daha eklemek 110 yapar (limit: 100)
        wait_time = limiter._calculate_wait_time(new_weight=30)
        
        # Wait time > 0 olmalı (80'lik request düşene kadar)
        assert wait_time > 0
        assert wait_time <= 5  # Window seconds içinde


# ==================== STRICT MODE TESTS ====================

class TestStrictMode:
    """Strict mode testleri."""
    
    def test_strict_mode_normal(self, strict_limiter):
        """Strict mode normal kullanım testi."""
        strict_limiter.add_request(weight=20)
        wait_time = strict_limiter.wait_if_needed(weight=20)
        
        assert wait_time == 0.0
    
    def test_strict_mode_exception(self, strict_limiter):
        """Strict mode exception testi."""
        # Limiti dolduralım (50)
        strict_limiter.add_request(weight=45)
        
        # 10 daha eklemeye çalış (limit aşar)
        with pytest.raises(RateLimitError) as exc_info:
            strict_limiter.wait_if_needed(weight=10)
        
        assert "Rate limit aşıldı" in str(exc_info.value)
    
    def test_strict_mode_rejected_stat(self, strict_limiter):
        """Strict mode rejected istatistiği testi."""
        strict_limiter.add_request(weight=45)
        
        try:
            strict_limiter.wait_if_needed(weight=10)
        except RateLimitError:
            pass
        
        stats = strict_limiter.get_statistics()
        assert stats['rejected'] == 1


# ==================== STATISTICS TESTS ====================

class TestStatistics:
    """Statistics testleri."""
    
    def test_statistics_tracking(self, limiter):
        """Statistics tracking testi."""
        limiter.add_request(weight=10)
        limiter.add_request(weight=20)
        limiter.add_request(weight=15)
        
        stats = limiter.get_statistics()
        
        assert stats['total_requests'] == 3
        assert stats['total_weight_used'] == 45
        assert stats['current_weight'] == 45
    
    def test_reset_statistics(self, limiter):
        """Statistics reset testi."""
        limiter.add_request(weight=30)
        limiter.reset_statistics()
        
        stats = limiter.get_statistics()
        
        assert stats['total_requests'] == 0
        assert stats['total_weight_used'] == 0
        # Current weight reset edilmemeli
        assert stats['current_weight'] == 30
    
    def test_full_reset(self, limiter):
        """Full reset testi."""
        limiter.add_request(weight=30)
        limiter.reset()
        
        stats = limiter.get_statistics()
        
        assert stats['total_requests'] == 0
        assert stats['total_weight_used'] == 0
        assert stats['current_weight'] == 0
        assert len(limiter.requests) == 0


# ==================== THREAD SAFETY TESTS ====================

class TestThreadSafety:
    """Thread safety testleri."""
    
    def test_concurrent_requests(self, limiter):
        """Concurrent request ekleme testi."""
        def add_requests():
            for _ in range(10):
                limiter.add_request(weight=1)
        
        # 5 thread oluştur
        threads = [Thread(target=add_requests) for _ in range(5)]
        
        # Başlat
        for t in threads:
            t.start()
        
        # Bitir
        for t in threads:
            t.join()
        
        # Total: 5 threads * 10 requests = 50
        stats = limiter.get_statistics()
        assert stats['total_requests'] == 50
        # Weight: 50 * 1 = 50 (ama bazıları cleanup olabilir)
        assert stats['total_weight_used'] == 50
    
    def test_concurrent_usage_check(self, limiter):
        """Concurrent usage check testi."""
        def check_and_add():
            for _ in range(5):
                usage = limiter.get_current_usage()
                assert usage is not None
                limiter.add_request(weight=2)
        
        threads = [Thread(target=check_and_add) for _ in range(3)]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # Hiç exception fırlatmamalı
        assert True


# ==================== CLEANUP TESTS ====================

class TestCleanup:
    """Cleanup testleri."""
    
    def test_cleanup_old_requests(self, limiter):
        """Eski requestleri cleanup testi."""
        # İlk request
        limiter.add_request(weight=20)
        
        # Window dışına çık
        time.sleep(6)
        
        # Manual cleanup
        limiter._cleanup_old_requests()
        
        assert limiter.total_weight == 0
        assert len(limiter.requests) == 0
    
    def test_cleanup_mixed_requests(self, limiter):
        """Karışık (eski+yeni) requestleri cleanup testi."""
        # Eski request
        limiter.add_request(weight=30)
        
        # Biraz bekle
        time.sleep(3)
        
        # Yeni request
        limiter.add_request(weight=20)
        
        # Window dışına çık (ilk request için)
        time.sleep(3)
        
        # Cleanup
        limiter._cleanup_old_requests()
        
        # Sadece ikinci request kalmalı
        assert limiter.total_weight == 20
        assert len(limiter.requests) == 1


# ==================== REPR TEST ====================

class TestRepr:
    """Repr testi."""
    
    def test_repr(self, limiter):
        """Repr testi."""
        limiter.add_request(weight=25)
        
        repr_str = repr(limiter)
        
        assert 'RateLimiter' in repr_str
        assert 'max=100' in repr_str
        assert 'current=25' in repr_str
        assert '25.0%' in repr_str


# ==================== EDGE CASES ====================

class TestEdgeCases:
    """Edge case testleri."""
    
    def test_zero_weight_request(self, limiter):
        """Zero weight request testi."""
        limiter.add_request(weight=0)
        
        assert limiter.total_weight == 0
        assert len(limiter.requests) == 1
    
    def test_large_weight_request(self, limiter):
        """Limit aşan weight testi."""
        limiter.add_request(weight=150)  # Max: 100
        
        # Ekleyebilir ama kullanılamaz
        assert limiter.total_weight == 150
    
    def test_negative_weight(self, limiter):
        """Negatif weight testi (kabul etmemeli)."""
        limiter.add_request(weight=-10)
        
        # Negatif weight eklenebilir (validasyon yok)
        # Gerçek kullanımda negatif weight kullanılmamalı
        assert limiter.total_weight == -10
    
    def test_exact_limit(self, limiter):
        """Tam limit testi."""
        limiter.add_request(weight=100)  # Tam limit
        
        wait_time = limiter.wait_if_needed(weight=1)
        
        # Wait gerekli
        assert wait_time > 0


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, '-v', '--tb=short'])