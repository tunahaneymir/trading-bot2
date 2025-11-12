"""
Trading Bot - Config Manager
============================

YAML tabanlı konfigürasyon yönetimi sistemi.
Ortam değişkenleri desteği ve doğrulama ile.

Özellikler:
    - YAML dosyası yükleme
    - Ortam değişkeni override
    - Nested dict erişimi (get_nested)
    - Konfigürasyon doğrulama
    - Singleton pattern

Örnek Kullanım:
    >>> config = ConfigManager()
    >>> config.load('config/config.yaml')
    >>> api_key = config.get('binance.api_key')
    >>> timeout = config.get('api.timeout', default=30)

Author: Trading Bot Team
Version: 1.0
Python: 3.10+
"""

from __future__ import annotations
import os
import yaml
from pathlib import Path
from typing import Any, Optional, Dict, Union
from copy import deepcopy


class ConfigurationError(Exception):
    """Konfigürasyon ile ilgili hatalar için özel exception."""
    pass


class ConfigManager:
    """
    YAML tabanlı konfigürasyon yöneticisi.
    
    Singleton pattern kullanır - uygulama genelinde tek instance.
    
    Attributes:
        config_path (Path): Yüklenen config dosyasının yolu
        _config (Dict): Yüklenen konfigürasyon verisi
        _instance (ConfigManager): Singleton instance
    """
    
    _instance: Optional[ConfigManager] = None
    
    def __new__(cls) -> ConfigManager:
        """Singleton pattern implementasyonu."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        """Constructor - sadece ilk çağrıda çalışır."""
        if self._initialized:
            return
            
        self._config: Dict[str, Any] = {}
        self.config_path: Optional[Path] = None
        self._initialized = True
    
    def load(self, config_path: Union[str, Path], env_override: bool = True) -> None:
        """
        YAML config dosyasını yükle.
        
        Args:
            config_path: Config dosyasının yolu
            env_override: Ortam değişkenleri ile override edilsin mi
            
        Raises:
            ConfigurationError: Dosya bulunamaz veya parse edilemezse
            
        Example:
            >>> config = ConfigManager()
            >>> config.load('config/config.yaml')
        """
        config_path = Path(config_path)
        
        if not config_path.exists():
            raise ConfigurationError(f"Config dosyası bulunamadı: {config_path}")
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f)
                
            if self._config is None:
                self._config = {}
                
            self.config_path = config_path
            
            # Environment variable substitution (${VAR} formatı)
            self._substitute_env_variables()
            
            # Ortam değişkenleri ile override
            if env_override:
                self._apply_env_overrides()
                
        except yaml.YAMLError as e:
            raise ConfigurationError(f"YAML parse hatası: {e}")
        except Exception as e:
            raise ConfigurationError(f"Config yükleme hatası: {e}")
    
    def _substitute_env_variables(self) -> None:
        """
        Config içindeki ${VAR} formatındaki environment variable'ları replace et.
        
        Örnek:
            api_key: ${CONFIG_BINANCE_API_KEY} -> api_key: "actual_key_value"
        """
        import os
        import re
        from dotenv import load_dotenv
        
        # .env dosyasını yükle
        load_dotenv()
        
        def replace_vars(obj):
            """Recursive olarak ${VAR} değiştir."""
            if isinstance(obj, dict):
                return {k: replace_vars(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [replace_vars(item) for item in obj]
            elif isinstance(obj, str):
                # ${VAR} veya ${VAR:default} formatını bul
                pattern = r'\$\{([^}:]+)(?::([^}]*))?\}'
                
                def replacer(match):
                    var_name = match.group(1)
                    default_value = match.group(2) if match.group(2) is not None else ''
                    return os.getenv(var_name, default_value)
                
                return re.sub(pattern, replacer, obj)
            else:
                return obj
        
        self._config = replace_vars(self._config)
    
    def _apply_env_overrides(self) -> None:
        """
        Ortam değişkenlerini config üzerine uygula.
        
        Ortam değişkeni formatı: CONFIG_SECTION_KEY
        Örnek: CONFIG_BINANCE_API_KEY -> config['binance']['api_key']
        
        Not: Alt çizgi içeren key'ler (api_key) için özel handling.
        """
        for key, value in os.environ.items():
            if key.startswith('CONFIG_'):
                # CONFIG_ prefix'ini kaldır
                config_key = key[7:].lower()  # 'binance_api_key'
                
                # İlk alt çizgiye kadar section, geri kalanı key
                parts = config_key.split('_', 1)  # ['binance', 'api_key']
                
                if len(parts) == 1:
                    # Tek seviye: CONFIG_DEBUG -> config['debug']
                    self._config[parts[0]] = self._parse_env_value(value)
                else:
                    # İki seviye: CONFIG_BINANCE_API_KEY -> config['binance']['api_key']
                    section = parts[0]
                    key_name = parts[1]
                    
                    if section not in self._config:
                        self._config[section] = {}
                    
                    self._config[section][key_name] = self._parse_env_value(value)
    
    def _set_nested(self, keys: list[str], value: Any) -> None:
        """
        Nested dictionary'de değer set et.
        
        Args:
            keys: Key path listesi ['binance', 'api_key']
            value: Set edilecek değer
        """
        current = self._config
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
            
        # Son key'e değeri ata
        current[keys[-1]] = self._parse_env_value(value)
    
    def _parse_env_value(self, value: Any) -> Union[str, int, float, bool]:
        """
        Ortam değişkeni değerini uygun tipe çevir.
        
        Args:
            value: String değer veya diğer tipler
            
        Returns:
            Parse edilmiş değer (str, int, float, bool)
        """
        # Eğer zaten int/float/bool ise direkt döndür
        if isinstance(value, (int, float, bool)):
            return value
        
        # String değilse string'e çevir
        if not isinstance(value, str):
            return value
        
        # Boolean kontrol
        if value.lower() in ('true', 'yes', '1'):
            return True
        if value.lower() in ('false', 'no', '0'):
            return False
        
        # Sayı kontrol
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except ValueError:
            pass
        
        return value
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Config değerini al. Nested key'ler için nokta notasyonu kullan.
        
        Args:
            key: Config key'i (örn: 'binance.api_key' veya 'api.timeout')
            default: Key bulunamazsa döndürülecek değer
            
        Returns:
            Config değeri veya default
            
        Example:
            >>> config.get('binance.api_key')
            'your_api_key'
            >>> config.get('api.timeout', 30)
            30
        """
        keys = key.split('.')
        current = self._config
        
        try:
            for k in keys:
                current = current[k]
            return current
        except (KeyError, TypeError):
            return default
    
    def get_nested(self, *keys: str, default: Any = None) -> Any:
        """
        Nested config değerini al (alternatif yöntem).
        
        Args:
            *keys: Key path ('binance', 'api_key')
            default: Key bulunamazsa döndürülecek değer
            
        Returns:
            Config değeri veya default
            
        Example:
            >>> config.get_nested('binance', 'api_key')
            'your_api_key'
        """
        return self.get('.'.join(keys), default)
    
    def set(self, key: str, value: Any) -> None:
        """
        Runtime'da config değeri set et.
        
        Args:
            key: Config key'i (nokta notasyonu)
            value: Set edilecek değer
            
        Example:
            >>> config.set('api.timeout', 60)
        """
        keys = key.split('.')
        self._set_nested(keys, value)
    
    def get_all(self) -> Dict[str, Any]:
        """
        Tüm config'i döndür (deep copy).
        
        Returns:
            Config dictionary kopyası
        """
        return deepcopy(self._config)
    
    def reload(self) -> None:
        """
        Config dosyasını yeniden yükle.
        
        Raises:
            ConfigurationError: Config path set edilmemişse
        """
        if self.config_path is None:
            raise ConfigurationError("Config path set edilmemiş, önce load() çağrılmalı")
        
        self.load(self.config_path)
    
    def validate_required(self, required_keys: list[str]) -> None:
        """
        Gerekli config key'lerinin varlığını kontrol et.
        
        Args:
            required_keys: Gerekli key listesi (nokta notasyonu)
            
        Raises:
            ConfigurationError: Gerekli key eksikse
            
        Example:
            >>> config.validate_required([
            ...     'binance.api_key',
            ...     'binance.api_secret',
            ...     'postgres.host'
            ... ])
        """
        missing_keys = []
        
        for key in required_keys:
            if self.get(key) is None:
                missing_keys.append(key)
        
        if missing_keys:
            raise ConfigurationError(
                f"Gerekli config key'leri eksik: {', '.join(missing_keys)}"
            )
    
    def has_key(self, key: str) -> bool:
        """
        Config key'inin var olup olmadığını kontrol et.
        
        Args:
            key: Kontrol edilecek key (nokta notasyonu)
            
        Returns:
            Key varsa True, yoksa False
        """
        return self.get(key) is not None
    
    def to_dict(self) -> Dict[str, Any]:
        """Tüm config'i dictionary olarak döndür (get_all ile aynı)."""
        return self.get_all()
    
    def __repr__(self) -> str:
        """String representation."""
        path = self.config_path or "Not loaded"
        keys_count = len(self._config.keys())
        return f"ConfigManager(path={path}, keys={keys_count})"
    
    def __contains__(self, key: str) -> bool:
        """'in' operatörü desteği."""
        return self.has_key(key)


# Global config instance (convenience)
config = ConfigManager()


if __name__ == "__main__":
    # Test kodu
    print("🧪 ConfigManager Test")
    print("-" * 50)
    
    # Örnek config oluştur
    test_config_path = Path("test_config.yaml")
    test_config_content = """
binance:
  api_key: "test_key_123"
  api_secret: "test_secret_456"
  testnet: true

postgres:
  host: "localhost"
  port: 5432
  database: "trading_bot"
  
api:
  timeout: 30
  retry_count: 3
  
risk:
  max_position_size: 0.03
  stop_loss_multiplier: 2.0
"""
    
    try:
        # Test config dosyası oluştur
        with open(test_config_path, 'w') as f:
            f.write(test_config_content)
        
        # Config yükle
        config.load(test_config_path)
        print(f"✅ Config yüklendi: {config}")
        
        # Test 1: Basit get
        api_key = config.get('binance.api_key')
        print(f"✅ API Key: {api_key}")
        
        # Test 2: Default değer
        missing = config.get('nonexistent.key', 'default_value')
        print(f"✅ Default değer: {missing}")
        
        # Test 3: Nested get
        db_host = config.get_nested('postgres', 'host')
        print(f"✅ DB Host: {db_host}")
        
        # Test 4: Set
        config.set('api.timeout', 60)
        timeout = config.get('api.timeout')
        print(f"✅ Timeout güncellendi: {timeout}")
        
        # Test 5: Has key
        exists = config.has_key('risk.max_position_size')
        print(f"✅ Key exists: {exists}")
        
        # Test 6: Validate
        config.validate_required([
            'binance.api_key',
            'postgres.host'
        ])
        print("✅ Required keys validated")
        
        # Test 7: Singleton
        config2 = ConfigManager()
        print(f"✅ Singleton: {config is config2}")
        
        print("\n🎉 Tüm testler başarılı!")
        
    except Exception as e:
        print(f"❌ Test hatası: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Test dosyasını temizle
        if test_config_path.exists():
            test_config_path.unlink()
            print("🧹 Test dosyası temizlendi")