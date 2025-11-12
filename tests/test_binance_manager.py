"""
Trading Bot - Binance Manager Tests
====================================

BinanceManager için unit ve integration testleri.

Test Kategorileri:
    - Initialization tests
    - Connection tests
    - Market data tests
    - Account tests
    - Trading tests
    - Rate limiting tests
    - Error handling tests

Not: Integration testler gerçek API key gerektirir (testnet).

Author: Trading Bot Team
Version: 1.0
Python: 3.10+
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from src.binance.binance_manager import BinanceManager, BinanceError
from src.binance.rate_limiter import RateLimiter
from src.core.config_manager import ConfigManager


# ==================== FIXTURES ====================

@pytest.fixture
def mock_config():
    """Mock ConfigManager fixture."""
    config = Mock(spec=ConfigManager)
    config.get.side_effect = lambda key, default=None: {
        'binance.api_key': 'test_api_key_123',
        'binance.api_secret': 'test_api_secret_456',
        'binance.testnet': True,
        'binance.timeout': 10,
        'binance.rate_limit': 1200
    }.get(key, default)
    return config


@pytest.fixture
def manager(mock_config):
    """BinanceManager fixture."""
    return BinanceManager(mock_config)


@pytest.fixture
def mock_response():
    """Mock API response fixture."""
    response = Mock()
    response.status_code = 200
    response.json.return_value = {'success': True}
    return response


# ==================== INITIALIZATION TESTS ====================

class TestInitialization:
    """Initialization testleri."""
    
    def test_init_with_config(self, mock_config):
        """Config ile initialization testi."""
        manager = BinanceManager(mock_config)
        
        assert manager.api_key == 'test_api_key_123'
        assert manager.api_secret == 'test_api_secret_456'
        assert manager.testnet is True
        assert manager.base_url == BinanceManager.TESTNET_URL
        assert isinstance(manager.rate_limiter, RateLimiter)
        assert manager._connected is False
    
    def test_init_without_config(self):
        """Config olmadan initialization testi."""
        manager = BinanceManager(
            api_key='manual_key',
            api_secret='manual_secret',
            testnet=False
        )
        
        assert manager.api_key == 'manual_key'
        assert manager.api_secret == 'manual_secret'
        assert manager.testnet is False
        assert manager.base_url == BinanceManager.MAINNET_URL
    
    def test_init_missing_credentials(self):
        """Credentials eksik ise hata testi."""
        with pytest.raises(BinanceError) as exc_info:
            BinanceManager()
        
        assert "API key ve secret gerekli" in str(exc_info.value)
    
    def test_session_creation(self, manager):
        """HTTP session oluşturma testi."""
        assert manager.session is not None
        assert 'X-MBX-APIKEY' in manager.session.headers
        assert manager.session.headers['X-MBX-APIKEY'] == 'test_api_key_123'


# ==================== SIGNATURE TESTS ====================

class TestSignature:
    """Signature generation testleri."""
    
    def test_generate_signature(self, manager):
        """Signature oluşturma testi."""
        params = {
            'symbol': 'BTCUSDT',
            'timestamp': 1234567890
        }
        
        signature = manager._generate_signature(params)
        
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex = 64 chars
    
    def test_signature_consistency(self, manager):
        """Aynı parametreler için aynı signature testi."""
        params = {'test': 'value', 'timestamp': 12345}
        
        sig1 = manager._generate_signature(params)
        sig2 = manager._generate_signature(params)
        
        assert sig1 == sig2
    
    def test_signature_different_params(self, manager):
        """Farklı parametreler için farklı signature testi."""
        params1 = {'test': 'value1'}
        params2 = {'test': 'value2'}
        
        sig1 = manager._generate_signature(params1)
        sig2 = manager._generate_signature(params2)
        
        assert sig1 != sig2


# ==================== REQUEST TESTS ====================

class TestRequests:
    """Request testleri."""
    
    @patch('src.binance.binance_manager.requests.Session.get')
    def test_request_success(self, mock_get, manager, mock_response):
        """Başarılı request testi."""
        mock_get.return_value = mock_response
        
        result = manager._request('GET', '/test', weight=1)
        
        assert result == {'success': True}
        assert mock_get.called
    
    @patch('src.binance.binance_manager.requests.Session.get')
    def test_request_with_signed(self, mock_get, manager, mock_response):
        """Signed request testi."""
        mock_get.return_value = mock_response
        
        result = manager._request('GET', '/test', signed=True, weight=1)
        
        assert result == {'success': True}
        call_args = mock_get.call_args
        params = call_args.kwargs.get('params', {})
        
        assert 'timestamp' in params
        assert 'signature' in params
    
    @patch('src.binance.binance_manager.requests.Session.get')
    def test_request_error(self, mock_get, manager):
        """Request error testi."""
        error_response = Mock()
        error_response.status_code = 400
        error_response.json.return_value = {
            'code': -1001,
            'msg': 'Invalid symbol'
        }
        mock_get.return_value = error_response
        
        with pytest.raises(BinanceError) as exc_info:
            manager._request('GET', '/test', weight=1)
        
        assert "Invalid symbol" in str(exc_info.value)
        assert exc_info.value.code == -1001
    
    @patch('src.binance.binance_manager.requests.Session.get')
    def test_request_timeout(self, mock_get, manager):
        """Request timeout testi."""
        mock_get.side_effect = Exception("Timeout")
        
        with pytest.raises(BinanceError):
            manager._request('GET', '/test', weight=1)
    
    @patch('src.binance.binance_manager.requests.Session.post')
    def test_post_request(self, mock_post, manager, mock_response):
        """POST request testi."""
        mock_post.return_value = mock_response
        
        result = manager._request('POST', '/test', weight=1)
        
        assert result == {'success': True}
        assert mock_post.called
    
    @patch('src.binance.binance_manager.requests.Session.delete')
    def test_delete_request(self, mock_delete, manager, mock_response):
        """DELETE request testi."""
        mock_delete.return_value = mock_response
        
        result = manager._request('DELETE', '/test', weight=1)
        
        assert result == {'success': True}
        assert mock_delete.called


# ==================== RATE LIMITING TESTS ====================

class TestRateLimiting:
    """Rate limiting testleri."""
    
    @patch('src.binance.binance_manager.requests.Session.get')
    def test_rate_limiter_integration(self, mock_get, manager, mock_response):
        """Rate limiter entegrasyon testi."""
        mock_get.return_value = mock_response
        
        # İlk request
        usage_before = manager.rate_limiter.get_current_usage()
        manager._request('GET', '/test', weight=10)
        usage_after = manager.rate_limiter.get_current_usage()
        
        assert usage_after['current_weight'] == usage_before['current_weight'] + 10
    
    def test_get_rate_limit_status(self, manager):
        """Rate limit status testi."""
        status = manager.get_rate_limit_status()
        
        assert 'current_weight' in status
        assert 'max_weight' in status
        assert 'total_requests' in status


# ==================== CONNECTION TESTS ====================

class TestConnection:
    """Connection testleri."""
    
    @patch.object(BinanceManager, '_request')
    def test_connect_success(self, mock_request, manager):
        """Başarılı connection testi."""
        mock_request.side_effect = [
            {'serverTime': 1234567890},  # time request
            {'assets': [{'asset': 'USDT'}]}  # account request
        ]
        
        result = manager.connect()
        
        assert result is True
        assert manager.is_connected() is True
    
    @patch.object(BinanceManager, '_request')
    def test_connect_failure(self, mock_request, manager):
        """Connection failure testi."""
        mock_request.side_effect = BinanceError("Connection failed")
        
        with pytest.raises(BinanceError):
            manager.connect()
        
        assert manager.is_connected() is False
    
    def test_is_connected_initial(self, manager):
        """Initial connection durumu testi."""
        assert manager.is_connected() is False


# ==================== MARKET DATA TESTS ====================

class TestMarketData:
    """Market data testleri."""
    
    @patch.object(BinanceManager, '_request')
    def test_get_klines(self, mock_request, manager):
        """get_klines testi."""
        mock_klines = [
            [1234567890, '50000', '51000', '49000', '50500', '100']
        ]
        mock_request.return_value = mock_klines
        
        result = manager.get_klines('BTCUSDT', '1h', limit=100)
        
        assert result == mock_klines
        call_args = mock_request.call_args
        assert call_args[1]['params']['symbol'] == 'BTCUSDT'
        assert call_args[1]['params']['interval'] == '1h'
    
    @patch.object(BinanceManager, '_request')
    def test_get_ticker(self, mock_request, manager):
        """get_ticker testi."""
        mock_ticker = {
            'symbol': 'BTCUSDT',
            'lastPrice': '50000',
            'volume': '1000'
        }
        mock_request.return_value = mock_ticker
        
        result = manager.get_ticker('BTCUSDT')
        
        assert result == mock_ticker
        assert mock_request.called
    
    @patch.object(BinanceManager, '_request')
    def test_get_order_book(self, mock_request, manager):
        """get_order_book testi."""
        mock_book = {
            'bids': [['50000', '1.5']],
            'asks': [['50100', '2.0']]
        }
        mock_request.return_value = mock_book
        
        result = manager.get_order_book('BTCUSDT', limit=100)
        
        assert result == mock_book


# ==================== ACCOUNT TESTS ====================

class TestAccount:
    """Account testleri."""
    
    @patch.object(BinanceManager, '_request')
    def test_get_balance(self, mock_request, manager):
        """get_balance testi."""
        mock_account = {
            'assets': [
                {'asset': 'USDT', 'walletBalance': '10000.00'},
                {'asset': 'BTC', 'walletBalance': '0.5'}
            ]
        }
        mock_request.return_value = mock_account
        
        result = manager.get_balance()
        
        assert len(result) == 2
        assert result[0]['asset'] == 'USDT'
    
    @patch.object(BinanceManager, '_request')
    def test_get_positions(self, mock_request, manager):
        """get_positions testi."""
        mock_positions = [
            {
                'symbol': 'BTCUSDT',
                'positionAmt': '0.001',
                'unrealizedProfit': '10.00'
            }
        ]
        mock_request.return_value = mock_positions
        
        result = manager.get_positions('BTCUSDT')
        
        assert len(result) == 1
        assert result[0]['symbol'] == 'BTCUSDT'
    
    @patch.object(BinanceManager, '_request')
    def test_get_open_orders(self, mock_request, manager):
        """get_open_orders testi."""
        mock_orders = [
            {
                'symbol': 'BTCUSDT',
                'orderId': 123456,
                'status': 'NEW'
            }
        ]
        mock_request.return_value = mock_orders
        
        result = manager.get_open_orders('BTCUSDT')
        
        assert len(result) == 1
        assert result[0]['orderId'] == 123456


# ==================== TRADING TESTS ====================

class TestTrading:
    """Trading testleri."""
    
    @patch.object(BinanceManager, '_request')
    def test_place_market_order(self, mock_request, manager):
        """Market order testi."""
        mock_order = {
            'orderId': 123456,
            'symbol': 'BTCUSDT',
            'status': 'FILLED'
        }
        mock_request.return_value = mock_order
        
        result = manager.place_order(
            symbol='BTCUSDT',
            side='BUY',
            order_type='MARKET',
            quantity=0.001
        )
        
        assert result['orderId'] == 123456
        call_args = mock_request.call_args
        params = call_args[1]['params']
        assert params['type'] == 'MARKET'
        assert params['side'] == 'BUY'
    
    @patch.object(BinanceManager, '_request')
    def test_place_limit_order(self, mock_request, manager):
        """Limit order testi."""
        mock_order = {
            'orderId': 123457,
            'symbol': 'BTCUSDT',
            'status': 'NEW'
        }
        mock_request.return_value = mock_order
        
        result = manager.place_order(
            symbol='BTCUSDT',
            side='SELL',
            order_type='LIMIT',
            quantity=0.001,
            price=51000.0,
            time_in_force='GTC'
        )
        
        assert result['orderId'] == 123457
        call_args = mock_request.call_args
        params = call_args[1]['params']
        assert params['type'] == 'LIMIT'
        assert params['price'] == 51000.0
    
    @patch.object(BinanceManager, '_request')
    def test_cancel_order(self, mock_request, manager):
        """Cancel order testi."""
        mock_response = {
            'orderId': 123456,
            'status': 'CANCELED'
        }
        mock_request.return_value = mock_response
        
        result = manager.cancel_order('BTCUSDT', order_id=123456)
        
        assert result['status'] == 'CANCELED'
    
    @patch.object(BinanceManager, '_request')
    def test_cancel_all_orders(self, mock_request, manager):
        """Cancel all orders testi."""
        mock_response = {'code': 200, 'msg': 'All orders canceled'}
        mock_request.return_value = mock_response
        
        result = manager.cancel_all_orders('BTCUSDT')
        
        assert result['code'] == 200
    
    def test_cancel_order_missing_id(self, manager):
        """Cancel order ID eksik testi."""
        with pytest.raises(BinanceError) as exc_info:
            manager.cancel_order('BTCUSDT')
        
        assert "order_id veya client_order_id gerekli" in str(exc_info.value)


# ==================== UTILITY TESTS ====================

class TestUtility:
    """Utility testleri."""
    
    @patch.object(BinanceManager, '_request')
    def test_get_exchange_info(self, mock_request, manager):
        """get_exchange_info testi."""
        mock_info = {
            'symbols': [
                {'symbol': 'BTCUSDT', 'status': 'TRADING'}
            ]
        }
        mock_request.return_value = mock_info
        
        result = manager.get_exchange_info('BTCUSDT')
        
        assert 'symbols' in result
    
    def test_close(self, manager):
        """Close testi."""
        manager._connected = True
        manager.close()
        
        assert manager.is_connected() is False
    
    def test_repr(self, manager):
        """Repr testi."""
        repr_str = repr(manager)
        
        assert 'BinanceManager' in repr_str
        assert 'testnet=' in repr_str


# ==================== CONTEXT MANAGER TESTS ====================

class TestContextManager:
    """Context manager testleri."""
    
    @patch.object(BinanceManager, 'connect')
    @patch.object(BinanceManager, 'close')
    def test_context_manager(self, mock_close, mock_connect, manager):
        """Context manager testi."""
        mock_connect.return_value = True
        
        with manager as m:
            assert m is manager
            assert mock_connect.called
        
        assert mock_close.called


# ==================== INTEGRATION TESTS ====================

@pytest.mark.integration
class TestIntegration:
    """Integration testler (gerçek API gerektirir)."""
    
    @pytest.fixture
    def real_manager(self):
        """Gerçek API key ile manager (testnet)."""
        import os
        
        api_key = os.getenv('CONFIG_BINANCE_API_KEY')
        api_secret = os.getenv('CONFIG_BINANCE_API_SECRET')
        
        if not api_key or not api_secret:
            pytest.skip("API credentials not found")
        
        return BinanceManager(
            api_key=api_key,
            api_secret=api_secret,
            testnet=True
        )
    
    def test_real_connection(self, real_manager):
        """Gerçek bağlantı testi."""
        result = real_manager.connect()
        assert result is True
        assert real_manager.is_connected() is True
        real_manager.close()
    
    def test_real_klines(self, real_manager):
        """Gerçek klines testi."""
        real_manager.connect()
        
        klines = real_manager.get_klines('BTCUSDT', '1h', limit=10)
        
        assert isinstance(klines, list)
        assert len(klines) > 0
        assert len(klines[0]) >= 6  # [time, open, high, low, close, volume, ...]
        
        real_manager.close()
    
    def test_real_ticker(self, real_manager):
        """Gerçek ticker testi."""
        real_manager.connect()
        
        ticker = real_manager.get_ticker('BTCUSDT')
        
        assert 'symbol' in ticker
        assert ticker['symbol'] == 'BTCUSDT'
        assert 'lastPrice' in ticker
        
        real_manager.close()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, '-v', '--tb=short'])