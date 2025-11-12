"""
Trading Bot - Core Layer
========================

Çekirdek yapı:
    - config_manager: Genel yapılandırma ve ortam yönetimi
    - logger: Log sistemi (setup_logger)
"""

from .config_manager import ConfigManager
from .logger import setup_logger

__all__ = [
    'ConfigManager',
    'setup_logger',
]
