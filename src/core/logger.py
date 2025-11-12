"""
Trading Bot - Logger System
============================

Çoklu seviye, rotating file handler destekli loglama sistemi.

Özellikler:
    - Rotating file handler (günlük/boyut bazlı)
    - Ayrı dosyalar (trading, errors, performance, rr_system)
    - Renkli console output
    - Structured logging desteği
    - Performance tracking

Log Seviyeleri:
    - DEBUG: Detaylı debug bilgisi
    - INFO: Genel bilgi mesajları
    - WARNING: Uyarı mesajları
    - ERROR: Hata mesajları
    - CRITICAL: Kritik hatalar

Örnek Kullanım:
    >>> logger = setup_logger('trading')
    >>> logger.info("Trade başarıyla tamamlandı")
    >>> logger.error("API bağlantı hatası", extra={'symbol': 'BTCUSDT'})

Author: Trading Bot Team
Version: 1.0
Python: 3.10+
"""

from __future__ import annotations
import logging
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime
import json


# ANSI renk kodları (terminal için)
class LogColors:
    """Terminal için ANSI renk kodları."""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    # Seviye renkleri
    DEBUG = '\033[36m'      # Cyan
    INFO = '\033[32m'       # Green
    WARNING = '\033[33m'    # Yellow
    ERROR = '\033[31m'      # Red
    CRITICAL = '\033[35m'   # Magenta
    
    # Özel renkler
    TIMESTAMP = '\033[90m'  # Gray
    NAME = '\033[94m'       # Blue


class ColoredFormatter(logging.Formatter):
    """
    Renkli console output için özel formatter.
    
    Terminal destekliyorsa renk kodları ekler.
    """
    
    COLORS = {
        'DEBUG': LogColors.DEBUG,
        'INFO': LogColors.INFO,
        'WARNING': LogColors.WARNING,
        'ERROR': LogColors.ERROR,
        'CRITICAL': LogColors.CRITICAL,
    }
    
    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None, use_colors: bool = True):
        """
        Args:
            fmt: Log format string
            datefmt: Date format string
            use_colors: Renk kullanılsın mı
        """
        super().__init__(fmt, datefmt=datefmt)
        self.use_colors = use_colors and sys.stdout.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        """Log kaydını formatla."""
        if self.use_colors:
            # Seviye rengini al
            levelname = record.levelname
            levelcolor = self.COLORS.get(levelname, '')
            
            # Renkli format
            record.levelname = f"{levelcolor}{levelname}{LogColors.RESET}"
            record.name = f"{LogColors.NAME}{record.name}{LogColors.RESET}"
            
        return super().format(record)


class StructuredFormatter(logging.Formatter):
    """
    JSON formatında structured logging için formatter.
    
    Her log kaydını JSON objesi olarak çıktılar.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Log kaydını JSON olarak formatla."""
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Extra alanları ekle (varsa)
        if hasattr(record, 'extra_data'):
            log_data.update(record.extra_data)
        
        # Exception bilgisi ekle (varsa)
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


class LoggerManager:
    """
    Merkezi logger yönetim sistemi.
    
    Farklı log tipleri için ayrı logger'lar oluşturur ve yönetir.
    """
    
    _loggers: Dict[str, logging.Logger] = {}
    _log_dir: Path = Path("logs")
    _initialized: bool = False
    
    @classmethod
    def initialize(
        cls,
        log_dir: str = "logs",
        level: int = logging.INFO,
        max_bytes: int = 10 * 1024 * 1024,  # 10 MB
        backup_count: int = 5
    ) -> None:
        """
        Logger sistemini başlat.
        
        Args:
            log_dir: Log dosyalarının kaydedileceği dizin
            level: Minimum log seviyesi
            max_bytes: Rotating handler için maksimum dosya boyutu
            backup_count: Saklanacak eski log dosyası sayısı
        """
        cls._log_dir = Path(log_dir)
        cls._log_dir.mkdir(parents=True, exist_ok=True)
        
        cls._level = level
        cls._max_bytes = max_bytes
        cls._backup_count = backup_count
        cls._initialized = True
    
    @classmethod
    def get_logger(
        cls,
        name: str,
        log_to_file: bool = True,
        log_to_console: bool = True,
        structured: bool = False
    ) -> logging.Logger:
        """
        Logger instance al veya oluştur.
        
        Args:
            name: Logger adı (örn: 'trading', 'errors')
            log_to_file: Dosyaya loglansın mı
            log_to_console: Console'a loglansın mı
            structured: JSON formatında mı (structured logging)
            
        Returns:
            Yapılandırılmış logger instance
        """
        if not cls._initialized:
            cls.initialize()
        
        # Mevcut logger'ı döndür
        if name in cls._loggers:
            return cls._loggers[name]
        
        # Yeni logger oluştur
        logger = logging.getLogger(name)
        logger.setLevel(cls._level)
        logger.propagate = False  # Parent logger'a propagate etme
        
        # Handler'lar ekle
        if log_to_file:
            cls._add_file_handler(logger, name, structured)
        
        if log_to_console:
            cls._add_console_handler(logger)
        
        # Logger'ı kaydet
        cls._loggers[name] = logger
        
        return logger
    
    @classmethod
    def _add_file_handler(
        cls,
        logger: logging.Logger,
        name: str,
        structured: bool
    ) -> None:
        """
        Dosya handler'ı ekle (rotating).
        
        Args:
            logger: Logger instance
            name: Logger adı (dosya adı için)
            structured: JSON formatı kullanılsın mı
        """
        log_file = cls._log_dir / f"{name}.log"
        
        # Log dizinini oluştur (yoksa)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Rotating file handler
        handler = RotatingFileHandler(
            log_file,
            maxBytes=cls._max_bytes,
            backupCount=cls._backup_count,
            encoding='utf-8'
        )
        
        # Formatter
        if structured:
            formatter = StructuredFormatter()
        else:
            formatter = logging.Formatter(
                fmt='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    @classmethod
    def _add_console_handler(cls, logger: logging.Logger) -> None:
        """
        Console handler ekle (renkli).
        
        Args:
            logger: Logger instance
        """
        handler = logging.StreamHandler(sys.stdout)
        
        # Renkli formatter
        formatter = ColoredFormatter(
            fmt='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    @classmethod
    def get_all_loggers(cls) -> Dict[str, logging.Logger]:
        """Tüm logger'ları döndür."""
        return cls._loggers.copy()
    
    @classmethod
    def shutdown(cls) -> None:
        """Tüm logger'ları kapat (handler'ları flush et)."""
        for logger in cls._loggers.values():
            for handler in logger.handlers:
                handler.flush()
                handler.close()
        
        logging.shutdown()


# Convenience fonksiyonlar
def setup_logger(
    name: str,
    level: int = logging.INFO,
    log_to_file: bool = True,
    log_to_console: bool = True
) -> logging.Logger:
    """
    Hızlı logger kurulumu için convenience fonksiyon.
    
    Args:
        name: Logger adı
        level: Log seviyesi
        log_to_file: Dosyaya logla
        log_to_console: Console'a logla
        
    Returns:
        Yapılandırılmış logger
        
    Example:
        >>> logger = setup_logger('trading')
        >>> logger.info("Trade başlatıldı")
    """
    if not LoggerManager._initialized:
        LoggerManager.initialize(level=level)
    
    return LoggerManager.get_logger(
        name,
        log_to_file=log_to_file,
        log_to_console=log_to_console
    )


def get_logger(name: str) -> logging.Logger:
    """
    Mevcut logger'ı al veya yeni oluştur.
    
    Args:
        name: Logger adı
        
    Returns:
        Logger instance
    """
    return LoggerManager.get_logger(name)


# Önceden tanımlı logger'lar
def get_trading_logger() -> logging.Logger:
    """Ana trading logger'ı al."""
    return setup_logger('trading')


def get_error_logger() -> logging.Logger:
    """Error logger'ı al."""
    return setup_logger('errors')


def get_performance_logger() -> logging.Logger:
    """Performance logger'ı al."""
    return setup_logger('performance')


def get_rr_logger() -> logging.Logger:
    """RR sistem logger'ı al."""
    return setup_logger('rr_system')


# Performance tracking decorator
def log_performance(logger: Optional[logging.Logger] = None):
    """
    Fonksiyon çalışma süresini logla (decorator).
    
    Args:
        logger: Kullanılacak logger (None ise performance logger)
        
    Example:
        >>> @log_performance()
        ... def expensive_function():
        ...     time.sleep(1)
    """
    import time
    from functools import wraps
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            _logger = logger or get_performance_logger()
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                _logger.info(
                    f"{func.__name__} tamamlandı",
                    extra={
                        'extra_data': {
                            'function': func.__name__,
                            'duration_ms': round(duration * 1000, 2),
                            'success': True
                        }
                    }
                )
                
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                
                _logger.error(
                    f"{func.__name__} hata verdi: {e}",
                    extra={
                        'extra_data': {
                            'function': func.__name__,
                            'duration_ms': round(duration * 1000, 2),
                            'success': False,
                            'error': str(e)
                        }
                    }
                )
                raise
        
        return wrapper
    return decorator


if __name__ == "__main__":
    # Test kodu
    print("🧪 Logger Test")
    print("-" * 50)
    
    try:
        # Logger sistemini başlat
        LoggerManager.initialize(log_dir="test_logs", level=logging.DEBUG)
        print("✅ Logger sistem başlatıldı")
        
        # Test 1: Trading logger
        trading_logger = get_trading_logger()
        trading_logger.debug("Debug mesajı")
        trading_logger.info("Trade başarıyla açıldı")
        trading_logger.warning("Yüksek volatilite tespit edildi")
        print("✅ Trading logger test")
        
        # Test 2: Error logger
        error_logger = get_error_logger()
        try:
            raise ValueError("Test hatası")
        except ValueError as e:
            error_logger.error("Hata yakalandı", exc_info=True)
        print("✅ Error logger test")
        
        # Test 3: Performance logger
        @log_performance()
        def test_function():
            import time
            time.sleep(0.1)
            return "Tamamlandı"
        
        result = test_function()
        print(f"✅ Performance tracking test: {result}")
        
        # Test 4: RR logger
        rr_logger = get_rr_logger()
        rr_logger.info("RR güncellendi", extra={
            'extra_data': {
                'old_rr': 1.5,
                'new_rr': 1.65,
                'learning_rate': 0.01
            }
        })
        print("✅ RR logger test")
        
        # Test 5: Structured logging
        structured_logger = LoggerManager.get_logger(
            'structured_test',
            structured=True,
            log_to_console=False
        )
        structured_logger.info("Structured log test", extra={
            'extra_data': {'test': True, 'value': 123}
        })
        print("✅ Structured logging test")
        
        # Test 6: Singleton
        logger1 = get_trading_logger()
        logger2 = get_trading_logger()
        print(f"✅ Singleton: {logger1 is logger2}")
        
        print("\n🎉 Tüm testler başarılı!")
        print(f"📁 Log dosyaları: test_logs/")
        
        # Log dosyalarını listele
        from pathlib import Path
        log_files = list(Path("test_logs").glob("*.log"))
        for log_file in log_files:
            size = log_file.stat().st_size
            print(f"  - {log_file.name} ({size} bytes)")
        
    except Exception as e:
        print(f"❌ Test hatası: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Logger'ları kapat
        LoggerManager.shutdown()
        print("🧹 Logger'lar kapatıldı")
        
        # Test klasörünü temizle (opsiyonel)
        import shutil
        if Path("test_logs").exists():
            shutil.rmtree("test_logs")
            print("🧹 Test dosyaları temizlendi")