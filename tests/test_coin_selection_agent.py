"""
Trading Bot - Coin Selection Agent Tests
=========================================

CoinSelectionAgent için unit testler.

Çalıştırma:
    pytest tests/test_coin_selection_agent.py -v
    
Author: Trading Bot Team
Version: 1.0 (Faz 4)
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import numpy as np

# Path setup
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.coin_selection_agent import CoinSelectionAgent, CoinMetrics
from src.utils.scoring import CoinScorer, CoinScores
from src.utils.filters import CoinFilter, FilterConfig
from src.agents.market_regime_detector import MarketRegimeDetector, MarketRegime


class TestCoinMetrics:
    """CoinMetrics dataclass testleri."""
    
    def test_coin_metrics_creation(self):
        """CoinMetrics oluşturma."""
        metrics = CoinMetrics(
            symbol="BTCUSDT",
            price=50000.0,
            volume_24h=1_000_000_000,
            volume_7d_avg=900_000_000,
            spread=0.001,
            volatility=0.03,
            atr=1500.0,
            adx=35.0,
            trend_direction=1,
            price_position=0.6,
            rsi=55.0,
            macd_histogram=100.0,
            price_change_24h=2.5,
            volume_trend='increasing'
        )
        
        assert metrics.symbol == "BTCUSDT"
        assert metrics.price == 50000.0
        assert metrics.trend_direction == 1
    
    def test_coin_metrics_to_dict(self):
        """to_dict metodu."""
        metrics = CoinMetrics(
            symbol="ETHUSDT",
            price=3000.0,
            volume_24h=500_000_000,
            volume_7d_avg=480_000_000,
            spread=0.0015,
            volatility=0.04,
            atr=120.0,
            adx=28.0,
            trend_direction=0,
            price_position=0.5,
            rsi=50.0,
            macd_histogram=0.0,
            price_change_24h=0.5,
            volume_trend='stable'
        )
        
        metrics_dict = metrics.to_dict()
        
        assert isinstance(metrics_dict, dict)
        assert metrics_dict['symbol'] == "ETHUSDT"
        assert 'price' in metrics_dict
        assert 'volatility' in metrics_dict


class TestCoinSelectionAgent:
    """CoinSelectionAgent testleri."""
    
    @pytest.fixture
    def mock_config(self):
        """Mock ConfigManager."""
        config = Mock()
        config.get = Mock(side_effect=lambda key, default=None: {
            'coin_selection.phase_1_count': 5,
            'coin_selection.phase_2_count': 10,
            'coin_selection.phase_3_count': 20,
            'coin_selection.min_volume': 10_000_000,
            'coin_selection.max_spread': 0.002,
            'coin_selection.min_volatility': 0.015,
            'coin_selection.max_volatility': 0.20,
            'coin_selection.update_interval_hours': 4,
            'coin_selection.weights': None,
        }.get(key, default))
        return config
    
    @pytest.fixture
    def mock_binance(self):
        """Mock BinanceManager."""
        binance = Mock()
        binance.testnet = True
        return binance
    
    @pytest.fixture
    def mock_postgres(self):
        """Mock PostgresManager."""
        postgres = Mock()
        postgres.execute = Mock(return_value=None)
        return postgres
    
    @pytest.fixture
    def mock_redis(self):
        """Mock RedisManager."""
        redis = Mock()
        redis.get = Mock(return_value=None)
        redis.set = Mock(return_value=True)
        return redis
    
    @pytest.fixture
    def agent(self, mock_config, mock_binance, mock_postgres, mock_redis):
        """CoinSelectionAgent instance."""
        return CoinSelectionAgent(
            config=mock_config,
            binance_manager=mock_binance,
            postgres_manager=mock_postgres,
            redis_manager=mock_redis,
            phase=1
        )
    
    def test_agent_initialization(self, agent):
        """Agent başlatma."""
        assert agent.phase == 1
        assert agent.coin_count == 5
        assert isinstance(agent.coin_filter, CoinFilter)
        assert isinstance(agent.scorer, CoinScorer)
        assert isinstance(agent.regime_detector, MarketRegimeDetector)
    
    def test_phase_coin_counts(self, mock_config, mock_binance, mock_postgres, mock_redis):
        """Fazlara göre coin sayıları."""
        # Phase 1
        agent1 = CoinSelectionAgent(
            mock_config, mock_binance, mock_postgres, mock_redis, phase=1
        )
        assert agent1.coin_count == 5
        
        # Phase 2
        agent2 = CoinSelectionAgent(
            mock_config, mock_binance, mock_postgres, mock_redis, phase=2
        )
        assert agent2.coin_count == 10
        
        # Phase 3
        agent3 = CoinSelectionAgent(
            mock_config, mock_binance, mock_postgres, mock_redis, phase=3
        )
        assert agent3.coin_count == 20
    
    def test_calculate_rsi(self, agent):
        """RSI hesaplama."""
        # Artan fiyatlar (oversold)
        prices_up = [100 + i for i in range(20)]
        rsi = agent._calculate_rsi(prices_up, 14)
        assert rsi is not None
        assert 0 <= rsi <= 100
        assert rsi > 50  # Uptrend = RSI > 50
        
        # Azalan fiyatlar (overbought)
        prices_down = [100 - i for i in range(20)]
        rsi = agent._calculate_rsi(prices_down, 14)
        assert rsi is not None
        assert rsi < 50  # Downtrend = RSI < 50
    
    def test_calculate_ema(self, agent):
        """EMA hesaplama."""
        prices = [100, 102, 104, 103, 105, 107, 106, 108, 110]
        ema = agent._calculate_ema(prices, 5)
        
        assert ema is not None
        assert ema > 100
        assert ema < 110
    
    def test_get_orderbook_spread(self, agent, mock_binance):
        """Orderbook spread hesaplama."""
        # Mock orderbook
        mock_binance.get_order_book = Mock(return_value={
            'bids': [['50000', '1.5'], ['49990', '2.0']],
            'asks': [['50010', '1.8'], ['50020', '2.2']]
        })
        
        spread = agent.get_orderbook_spread('BTCUSDT')
        
        assert spread is not None
        assert spread > 0
        assert spread < 1  # Should be small percentage
    
    def test_cache_operations(self, agent, mock_redis):
        """Cache operasyonları."""
        # Test symbols
        test_symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        
        # Mock cache response
        import json
        mock_redis.get = Mock(return_value=json.dumps(test_symbols))
        
        # Get from cache
        cached = agent.get_selected_coins_from_cache()
        
        assert cached == test_symbols
        mock_redis.get.assert_called_once()
    
    def test_get_statistics(self, agent):
        """İstatistik alma."""
        stats = agent.get_statistics()
        
        assert isinstance(stats, dict)
        assert 'phase' in stats
        assert 'target_coin_count' in stats
        assert 'cache_ttl_hours' in stats
        assert stats['phase'] == 1
        assert stats['target_coin_count'] == 5
    
    def test_repr(self, agent):
        """String representation."""
        repr_str = repr(agent)
        assert 'CoinSelectionAgent' in repr_str
        assert 'phase=1' in repr_str
        assert 'coins=5' in repr_str


class TestIntegration:
    """Integration testleri (mocked)."""
    
    @pytest.fixture
    def full_mock_setup(self):
        """Tam mock setup."""
        config = Mock()
        config.get = Mock(side_effect=lambda key, default=None: {
            'coin_selection.phase_1_count': 5,
            'coin_selection.min_volume': 10_000_000,
            'coin_selection.max_spread': 0.002,
            'coin_selection.min_volatility': 0.015,
            'coin_selection.max_volatility': 0.20,
            'coin_selection.update_interval_hours': 4,
            'coin_selection.weights': None,
        }.get(key, default))
        
        binance = Mock()
        binance.testnet = True
        binance.get_exchange_info = Mock(return_value={
            'symbols': [
                {'symbol': 'BTCUSDT', 'contractType': 'PERPETUAL', 'status': 'TRADING'},
                {'symbol': 'ETHUSDT', 'contractType': 'PERPETUAL', 'status': 'TRADING'},
            ]
        })
        binance.client = Mock()
        binance.client.futures_ticker = Mock(return_value=[
            {'symbol': 'BTCUSDT', 'lastPrice': '50000', 'quoteVolume': '1000000000', 'priceChangePercent': '2.5'},
            {'symbol': 'ETHUSDT', 'lastPrice': '3000', 'quoteVolume': '500000000', 'priceChangePercent': '1.5'},
        ])
        
        postgres = Mock()
        postgres.execute = Mock(return_value=None)
        
        redis = Mock()
        redis.get = Mock(return_value=None)
        redis.set = Mock(return_value=True)
        
        return config, binance, postgres, redis
    
    def test_scan_market_integration(self, full_mock_setup):
        """Market scan integration test."""
        config, binance, postgres, redis = full_mock_setup
        
        agent = CoinSelectionAgent(config, binance, postgres, redis, phase=1)
        
        # Scan market
        coins = agent.scan_market()
        
        assert isinstance(coins, list)
        assert len(coins) == 2
        assert coins[0]['symbol'] == 'BTCUSDT'
        assert 'price' in coins[0]
        assert 'volume_24h' in coins[0]


if __name__ == "__main__":
    pytest.main([__file__, '-v'])