"""
Config Manager Unit Tests
==========================

pytest ile ConfigManager için kapsamlı testler.

Çalıştırma:
    pytest test_config_manager.py -v
    pytest test_config_manager.py -v --cov=config_manager

Author: Trading Bot Team
"""

import pytest
import os
from pathlib import Path
import tempfile
import yaml

# Config manager'ı import et (aynı dizinde olduğunu varsayıyoruz)
try:
    from src.core.config_manager import ConfigManager, ConfigurationError, config
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.core.config_manager import ConfigManager, ConfigurationError, config


@pytest.fixture
def sample_config():
    """Test için örnek config içeriği."""
    return {
        'binance': {
            'api_key': 'test_key_123',
            'api_secret': 'test_secret_456',
            'testnet': True
        },
        'postgres': {
            'host': 'localhost',
            'port': 5432,
            'database': 'trading_bot',
            'user': 'trader'
        },
        'api': {
            'timeout': 30,
            'retry_count': 3,
            'rate_limit': 10
        },
        'risk': {
            'max_position_size': 0.03,
            'stop_loss_multiplier': 2.0,
            'daily_loss_limit': 0.05
        }
    }


@pytest.fixture
def temp_config_file(sample_config):
    """Geçici config dosyası oluştur."""
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.yaml',
        delete=False,
        encoding='utf-8'
    ) as f:
        yaml.dump(sample_config, f)
        temp_path = f.name
    
    yield Path(temp_path)
    
    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def config_manager():
    """Her test için temiz ConfigManager instance."""
    # Singleton'ı reset et
    ConfigManager._instance = None
    return ConfigManager()


class TestConfigManagerBasics:
    """Temel ConfigManager fonksiyonalite testleri."""
    
    def test_singleton_pattern(self):
        """Singleton pattern doğru çalışıyor mu."""
        cm1 = ConfigManager()
        cm2 = ConfigManager()
        assert cm1 is cm2
    
    def test_load_valid_config(self, config_manager, temp_config_file):
        """Geçerli config dosyası yükleme."""
        config_manager.load(temp_config_file)
        assert config_manager.config_path == temp_config_file
        assert config_manager.get('binance.api_key') == 'test_key_123'
    
    def test_load_nonexistent_file(self, config_manager):
        """Olmayan dosya yükleme - hata vermeli."""
        with pytest.raises(ConfigurationError) as exc_info:
            config_manager.load('nonexistent.yaml')
        assert "bulunamadı" in str(exc_info.value)
    
    def test_load_invalid_yaml(self, config_manager):
        """Geçersiz YAML - parse hatası vermeli."""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.yaml',
            delete=False
        ) as f:
            f.write("invalid: yaml: content: {{}}")
            temp_path = f.name
        
        try:
            with pytest.raises(ConfigurationError) as exc_info:
                config_manager.load(temp_path)
            assert "parse" in str(exc_info.value).lower()
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestConfigGetters:
    """Config değeri alma testleri."""
    
    def test_get_simple_key(self, config_manager, temp_config_file):
        """Basit key okuma."""
        config_manager.load(temp_config_file)
        timeout = config_manager.get('api.timeout')
        assert timeout == 30
    
    def test_get_nested_key(self, config_manager, temp_config_file):
        """İç içe key okuma."""
        config_manager.load(temp_config_file)
        api_key = config_manager.get('binance.api_key')
        assert api_key == 'test_key_123'
    
    def test_get_with_default(self, config_manager, temp_config_file):
        """Default değer ile okuma."""
        config_manager.load(temp_config_file)
        value = config_manager.get('nonexistent.key', 'default_value')
        assert value == 'default_value'
    
    def test_get_nested_method(self, config_manager, temp_config_file):
        """get_nested metodu."""
        config_manager.load(temp_config_file)
        host = config_manager.get_nested('postgres', 'host')
        assert host == 'localhost'
    
    def test_get_all(self, config_manager, temp_config_file, sample_config):
        """Tüm config'i al."""
        config_manager.load(temp_config_file)
        all_config = config_manager.get_all()
        assert all_config == sample_config
        # Deep copy kontrolü
        all_config['new_key'] = 'value'
        assert 'new_key' not in config_manager.get_all()


class TestConfigSetters:
    """Config değeri set etme testleri."""
    
    def test_set_simple_value(self, config_manager, temp_config_file):
        """Basit değer set etme."""
        config_manager.load(temp_config_file)
        config_manager.set('api.timeout', 60)
        assert config_manager.get('api.timeout') == 60
    
    def test_set_nested_value(self, config_manager, temp_config_file):
        """İç içe değer set etme."""
        config_manager.load(temp_config_file)
        config_manager.set('binance.new_key', 'new_value')
        assert config_manager.get('binance.new_key') == 'new_value'
    
    def test_set_creates_nested_structure(self, config_manager, temp_config_file):
        """Set yeni nested yapı oluşturur."""
        config_manager.load(temp_config_file)
        config_manager.set('new.section.key', 'value')
        assert config_manager.get('new.section.key') == 'value'


class TestEnvironmentOverrides:
    """Ortam değişkeni override testleri."""
    
    def test_env_override_simple(self, config_manager, temp_config_file):
        """Basit ortam değişkeni override."""
        os.environ['CONFIG_API_TIMEOUT'] = '120'
        
        try:
            config_manager.load(temp_config_file, env_override=True)
            assert config_manager.get('api.timeout') == 120
        finally:
            del os.environ['CONFIG_API_TIMEOUT']
    
    def test_env_override_nested(self, config_manager, temp_config_file):
        """İç içe ortam değişkeni override."""
        os.environ['CONFIG_BINANCE_API_KEY'] = 'env_key'
        
        try:
            config_manager.load(temp_config_file, env_override=True)
            assert config_manager.get('binance.api_key') == 'env_key'
        finally:
            del os.environ['CONFIG_BINANCE_API_KEY']
    
    def test_env_override_boolean(self, config_manager, temp_config_file):
        """Boolean ortam değişkeni."""
        os.environ['CONFIG_BINANCE_TESTNET'] = 'false'
        
        try:
            config_manager.load(temp_config_file, env_override=True)
            assert config_manager.get('binance.testnet') is False
        finally:
            del os.environ['CONFIG_BINANCE_TESTNET']
    
    def test_env_override_disabled(self, config_manager, temp_config_file):
        """Ortam değişkeni override devre dışı."""
        os.environ['CONFIG_API_TIMEOUT'] = '120'
        
        try:
            config_manager.load(temp_config_file, env_override=False)
            assert config_manager.get('api.timeout') == 30  # Original değer
        finally:
            del os.environ['CONFIG_API_TIMEOUT']


class TestConfigValidation:
    """Config doğrulama testleri."""
    
    def test_validate_required_success(self, config_manager, temp_config_file):
        """Gerekli key'ler mevcut."""
        config_manager.load(temp_config_file)
        config_manager.validate_required([
            'binance.api_key',
            'postgres.host',
            'api.timeout'
        ])
        # Exception fırlatmamalı
    
    def test_validate_required_missing(self, config_manager, temp_config_file):
        """Gerekli key'ler eksik."""
        config_manager.load(temp_config_file)
        with pytest.raises(ConfigurationError) as exc_info:
            config_manager.validate_required([
                'binance.api_key',
                'nonexistent.key',
                'another.missing.key'
            ])
        error_msg = str(exc_info.value)
        assert 'nonexistent.key' in error_msg
        assert 'another.missing.key' in error_msg
    
    def test_has_key_exists(self, config_manager, temp_config_file):
        """Key var mı kontrolü - var."""
        config_manager.load(temp_config_file)
        assert config_manager.has_key('binance.api_key')
    
    def test_has_key_not_exists(self, config_manager, temp_config_file):
        """Key var mı kontrolü - yok."""
        config_manager.load(temp_config_file)
        assert not config_manager.has_key('nonexistent.key')
    
    def test_contains_operator(self, config_manager, temp_config_file):
        """'in' operatörü."""
        config_manager.load(temp_config_file)
        assert 'binance.api_key' in config_manager
        assert 'nonexistent.key' not in config_manager


class TestConfigReload:
    """Config yeniden yükleme testleri."""
    
    def test_reload_success(self, config_manager, temp_config_file):
        """Config yeniden yükleme."""
        config_manager.load(temp_config_file)
        config_manager.set('api.timeout', 999)
        config_manager.reload()
        assert config_manager.get('api.timeout') == 30  # Original değer
    
    def test_reload_without_load(self, config_manager):
        """Load edilmeden reload - hata vermeli."""
        with pytest.raises(ConfigurationError) as exc_info:
            config_manager.reload()
        assert "path set edilmemiş" in str(exc_info.value)


class TestGlobalConfigInstance:
    """Global config instance testleri."""
    
    def test_global_instance(self):
        """Global config instance kullanımı."""
        from src.core.config_manager import config
        assert isinstance(config, ConfigManager)


class TestEdgeCases:
    """Edge case testleri."""
    
    def test_empty_config_file(self, config_manager):
        """Boş config dosyası."""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.yaml',
            delete=False
        ) as f:
            f.write("")
            temp_path = f.name
        
        try:
            config_manager.load(temp_path)
            assert config_manager.get_all() == {}
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def test_deep_nested_get(self, config_manager):
        """Çok derin nested yapı."""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.yaml',
            delete=False
        ) as f:
            yaml.dump({
                'level1': {
                    'level2': {
                        'level3': {
                            'level4': 'deep_value'
                        }
                    }
                }
            }, f)
            temp_path = f.name
        
        try:
            config_manager.load(temp_path)
            value = config_manager.get('level1.level2.level3.level4')
            assert value == 'deep_value'
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def test_repr(self, config_manager, temp_config_file):
        """String representation."""
        config_manager.load(temp_config_file)
        repr_str = repr(config_manager)
        assert 'ConfigManager' in repr_str
        assert str(temp_config_file) in repr_str


if __name__ == "__main__":
    # Testleri çalıştır
    pytest.main([__file__, '-v', '--tb=short'])