"""
Logger Unit Tests
=================

pytest ile Logger sistemi için kapsamlı testler.

Çalıştırma:
    pytest test_logger.py -v
    pytest test_logger.py -v --cov=logger

Author: Trading Bot Team
"""

import pytest
import logging
import tempfile
import time
import json
from pathlib import Path

# Logger'ı import et
try:
    from src.core.logger import (
        LoggerManager, setup_logger, get_logger,
        get_trading_logger, get_error_logger,
        get_performance_logger, get_rr_logger,
        log_performance
    )
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.core.logger import (
        LoggerManager, setup_logger, get_logger,
        get_trading_logger, get_error_logger,
        get_performance_logger, get_rr_logger,
        log_performance
    )


@pytest.fixture
def temp_log_dir():
    """Her test için geçici log dizini."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture(autouse=True)
def reset_logger_manager():
    """Her testten önce LoggerManager'ı reset et."""
    LoggerManager._loggers = {}
    LoggerManager._initialized = False
    yield
    # Cleanup
    LoggerManager.shutdown()


class TestLoggerManagerInitialization:
    """LoggerManager başlatma testleri."""
    
    def test_initialization(self, temp_log_dir):
        """Temel başlatma."""
        LoggerManager.initialize(log_dir=temp_log_dir)
        assert LoggerManager._initialized
        assert LoggerManager._log_dir == Path(temp_log_dir)
    
    def test_log_dir_creation(self, temp_log_dir):
        """Log dizini otomatik oluşturulur."""
        log_dir = Path(temp_log_dir) / "nested" / "log" / "dir"
        LoggerManager.initialize(log_dir=str(log_dir))
        assert log_dir.exists()
    
    def test_custom_parameters(self, temp_log_dir):
        """Özel parametrelerle başlatma."""
        LoggerManager.initialize(
            log_dir=temp_log_dir,
            level=logging.DEBUG,
            max_bytes=5 * 1024 * 1024,
            backup_count=3
        )
        assert LoggerManager._level == logging.DEBUG
        assert LoggerManager._max_bytes == 5 * 1024 * 1024
        assert LoggerManager._backup_count == 3


class TestLoggerCreation:
    """Logger oluşturma testleri."""
    
    def test_get_logger_basic(self, temp_log_dir):
        """Temel logger oluşturma."""
        LoggerManager.initialize(log_dir=temp_log_dir)
        logger = LoggerManager.get_logger('test')
        assert isinstance(logger, logging.Logger)
        assert logger.name == 'test'
    
    def test_logger_singleton(self, temp_log_dir):
        """Aynı isimli logger singleton."""
        LoggerManager.initialize(log_dir=temp_log_dir)
        logger1 = LoggerManager.get_logger('test')
        logger2 = LoggerManager.get_logger('test')
        assert logger1 is logger2
    
    def test_multiple_loggers(self, temp_log_dir):
        """Birden fazla farklı logger."""
        LoggerManager.initialize(log_dir=temp_log_dir)
        logger1 = LoggerManager.get_logger('test1')
        logger2 = LoggerManager.get_logger('test2')
        assert logger1 is not logger2
        assert logger1.name != logger2.name
    
    def test_logger_without_file_handler(self, temp_log_dir):
        """Sadece console handler ile logger."""
        LoggerManager.initialize(log_dir=temp_log_dir)
        logger = LoggerManager.get_logger('test', log_to_file=False)
        
        # Sadece StreamHandler olmalı
        handlers = logger.handlers
        assert len(handlers) == 1
        assert isinstance(handlers[0], logging.StreamHandler)
    
    def test_logger_without_console_handler(self, temp_log_dir):
        """Sadece file handler ile logger."""
        LoggerManager.initialize(log_dir=temp_log_dir)
        logger = LoggerManager.get_logger('test', log_to_console=False)
        
        # Sadece FileHandler olmalı
        handlers = logger.handlers
        assert len(handlers) == 1
        from logging.handlers import RotatingFileHandler
        assert isinstance(handlers[0], RotatingFileHandler)


class TestLogging:
    """Loglama fonksiyonalite testleri."""
    
    def test_log_to_file(self, temp_log_dir):
        """Dosyaya loglama."""
        LoggerManager.initialize(log_dir=temp_log_dir)
        logger = LoggerManager.get_logger('test', log_to_console=False)
        
        test_message = "Test log mesajı"
        logger.info(test_message)
        
        # Log dosyası oluşturuldu mu?
        log_file = Path(temp_log_dir) / "test.log"
        assert log_file.exists()
        
        # İçerik doğru mu?
        content = log_file.read_text()
        assert test_message in content
    
    def test_log_levels(self, temp_log_dir):
        """Farklı log seviyeleri."""
        LoggerManager.initialize(log_dir=temp_log_dir, level=logging.DEBUG)
        logger = LoggerManager.get_logger('test', log_to_console=False)
        
        logger.debug("Debug mesajı")
        logger.info("Info mesajı")
        logger.warning("Warning mesajı")
        logger.error("Error mesajı")
        logger.critical("Critical mesajı")
        
        log_file = Path(temp_log_dir) / "test.log"
        content = log_file.read_text()
        
        assert "Debug mesajı" in content
        assert "Info mesajı" in content
        assert "Warning mesajı" in content
        assert "Error mesajı" in content
        assert "Critical mesajı" in content
    
    def test_log_with_exception(self, temp_log_dir):
        """Exception ile loglama."""
        LoggerManager.initialize(log_dir=temp_log_dir)
        logger = LoggerManager.get_logger('test', log_to_console=False)
        
        try:
            raise ValueError("Test hatası")
        except ValueError:
            logger.error("Hata yakalandı", exc_info=True)
        
        log_file = Path(temp_log_dir) / "test.log"
        content = log_file.read_text()
        
        assert "Hata yakalandı" in content
        assert "ValueError: Test hatası" in content
        assert "Traceback" in content


class TestStructuredLogging:
    """Structured (JSON) logging testleri."""
    
    def test_structured_format(self, temp_log_dir):
        """JSON formatında loglama."""
        LoggerManager.initialize(log_dir=temp_log_dir)
        logger = LoggerManager.get_logger(
            'test',
            structured=True,
            log_to_console=False
        )
        
        logger.info("Test mesajı", extra={
            'extra_data': {'key': 'value', 'number': 123}
        })
        
        log_file = Path(temp_log_dir) / "test.log"
        content = log_file.read_text()
        
        # JSON parse edebiliyor muyuz?
        log_entry = json.loads(content.strip())
        
        assert log_entry['message'] == "Test mesajı"
        assert log_entry['level'] == "INFO"
        assert log_entry['key'] == 'value'
        assert log_entry['number'] == 123


class TestConvenienceFunctions:
    """Convenience fonksiyon testleri."""
    
    def test_setup_logger(self, temp_log_dir):
        """setup_logger fonksiyonu."""
        LoggerManager.initialize(log_dir=temp_log_dir)
        logger = setup_logger('test')
        assert isinstance(logger, logging.Logger)
        assert logger.name == 'test'
    
    def test_get_logger_func(self, temp_log_dir):
        """get_logger fonksiyonu."""
        LoggerManager.initialize(log_dir=temp_log_dir)
        logger = get_logger('test')
        assert isinstance(logger, logging.Logger)
    
    def test_predefined_loggers(self, temp_log_dir):
        """Önceden tanımlı logger'lar."""
        LoggerManager.initialize(log_dir=temp_log_dir)
        
        trading_logger = get_trading_logger()
        error_logger = get_error_logger()
        performance_logger = get_performance_logger()
        rr_logger = get_rr_logger()
        
        assert trading_logger.name == 'trading'
        assert error_logger.name == 'errors'
        assert performance_logger.name == 'performance'
        assert rr_logger.name == 'rr_system'


class TestPerformanceTracking:
    """Performance tracking decorator testleri."""
    
    def test_performance_decorator_success(self, temp_log_dir):
        """Başarılı fonksiyon performance tracking."""
        LoggerManager.initialize(log_dir=temp_log_dir)
        
        @log_performance()
        def test_function():
            time.sleep(0.1)
            return "Success"
        
        result = test_function()
        assert result == "Success"
        
        # Log dosyasını kontrol et
        log_file = Path(temp_log_dir) / "performance.log"
        content = log_file.read_text()
        
        assert "test_function tamamlandı" in content
        assert "duration_ms" in content
    
    def test_performance_decorator_error(self, temp_log_dir):
        """Hata veren fonksiyon performance tracking."""
        LoggerManager.initialize(log_dir=temp_log_dir)
        
        @log_performance()
        def failing_function():
            time.sleep(0.05)
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            failing_function()
        
        # Log dosyasını kontrol et
        log_file = Path(temp_log_dir) / "performance.log"
        content = log_file.read_text()
        
        assert "failing_function hata verdi" in content
        assert "duration_ms" in content
        assert "success" in content.lower()


class TestFileRotation:
    """Dosya rotasyonu testleri."""
    
    def test_rotation_by_size(self, temp_log_dir):
        """Boyut bazlı rotasyon."""
        # Çok küçük max_bytes ile başlat
        LoggerManager.initialize(
            log_dir=temp_log_dir,
            max_bytes=1024,  # 1KB
            backup_count=3
        )
        
        logger = LoggerManager.get_logger('test', log_to_console=False)
        
        # Çok fazla log yaz (>1KB)
        for i in range(100):
            logger.info(f"Log mesajı {i}: " + "x" * 100)
        
        # Rotasyon oldu mu kontrol et
        log_files = list(Path(temp_log_dir).glob("test.log*"))
        assert len(log_files) > 1  # En az 2 dosya (ana + backup)


class TestLoggerShutdown:
    """Logger kapatma testleri."""
    
    def test_shutdown(self, temp_log_dir):
        """Logger'ları temiz kapat."""
        LoggerManager.initialize(log_dir=temp_log_dir)
        logger = LoggerManager.get_logger('test')
        logger.info("Test mesajı")
        
        # Shutdown
        LoggerManager.shutdown()
        
        # Handler'lar kapatıldı mı?
        assert len(logger.handlers) > 0  # Handler'lar hala var ama kapalı


class TestEdgeCases:
    """Edge case testleri."""
    
    def test_auto_initialization(self, temp_log_dir):
        """Otomatik başlatma."""
        # Initialize çağrılmadan logger al
        logger = setup_logger('test')
        assert isinstance(logger, logging.Logger)
        assert LoggerManager._initialized
    
    def test_unicode_logging(self, temp_log_dir):
        """Unicode karakter loglama."""
        LoggerManager.initialize(log_dir=temp_log_dir)
        logger = LoggerManager.get_logger('test', log_to_console=False)
        
        logger.info("Türkçe karakterler: ğüşıöçĞÜŞİÖÇ")
        logger.info("Emoji: 🚀 💰 📊")
        
        log_file = Path(temp_log_dir) / "test.log"
        content = log_file.read_text(encoding='utf-8')
        
        assert "Türkçe karakterler" in content
        assert "Emoji" in content
    
    def test_get_all_loggers(self, temp_log_dir):
        """Tüm logger'ları al."""
        LoggerManager.initialize(log_dir=temp_log_dir)
        
        logger1 = LoggerManager.get_logger('test1')
        logger2 = LoggerManager.get_logger('test2')
        
        all_loggers = LoggerManager.get_all_loggers()
        
        assert 'test1' in all_loggers
        assert 'test2' in all_loggers
        assert all_loggers['test1'] is logger1
        assert all_loggers['test2'] is logger2


if __name__ == "__main__":
    # Testleri çalıştır
    pytest.main([__file__, '-v', '--tb=short'])