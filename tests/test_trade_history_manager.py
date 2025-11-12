"""
Trading Bot - Trade History Manager Tests
==========================================

TradeHistoryManager için unit testler.
PostgreSQL ve Redis manager'ları mock edilerek test.

Test Kapsama:
    - Trade creation
    - Trade updates
    - Trade closing
    - Trade queries
    - Statistics calculation
    - Cache integration
    - Error handling

Author: Trading Bot Team
Version: 1.0
Python: 3.10+
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Parent dizini path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.trade_history_manager import TradeHistoryManager, TradeHistoryError


# ==================== Fixtures ====================

@pytest.fixture
def mock_postgres():
    """Mock PostgresManager."""
    postgres = Mock()
    postgres.execute = Mock()
    postgres.execute_transaction = Mock()
    return postgres


@pytest.fixture
def mock_redis():
    """Mock RedisManager."""
    redis = Mock()
    redis.set = Mock()
    redis.get = Mock()
    redis.delete = Mock()
    redis.TTL_HOT_STATE = 3600
    return redis


@pytest.fixture
def trade_manager(mock_postgres, mock_redis):
    """TradeHistoryManager instance."""
    return TradeHistoryManager(mock_postgres, mock_redis)


@pytest.fixture
def sample_trade_data():
    """Örnek trade verisi."""
    return {
        'symbol': 'BTCUSDT',
        'side': 'LONG',
        'entry_price': 50000.0,
        'quantity': 0.1,
        'stop_loss': 49000.0,
        'take_profit': 52000.0,
        'rr_ratio': 2.0,
        'leverage': 1,
        'signal_confidence': 0.85,
        'signal_type': 'SUPERTREND_CROSS',
        'timeframe': '15m',
        'notes': 'Test trade'
    }


# ==================== Trade Creation Tests ====================

def test_create_trade_success(trade_manager, mock_postgres, mock_redis, sample_trade_data):
    """Başarılı trade oluşturma testi."""
    mock_postgres.execute.return_value = None
    
    trade_id = trade_manager.create_trade(**sample_trade_data)
    
    # Trade ID UUID formatında mı?
    assert len(trade_id) == 36  # UUID string length
    assert '-' in trade_id
    
    # PostgreSQL'e yazıldı mı? (2 kez: trades + positions)
    assert mock_postgres.execute.call_count == 2
    
    # Redis'e cache'lendi mi?
    mock_redis.set.assert_called_once()
    redis_call_args = mock_redis.set.call_args
    assert trade_manager.REDIS_PREFIX_TRADE in redis_call_args[0][0]


def test_create_trade_db_error(trade_manager, mock_postgres, sample_trade_data):
    """Trade oluşturma DB hatası testi."""
    mock_postgres.execute.side_effect = Exception("DB error")
    
    with pytest.raises(TradeHistoryError) as exc_info:
        trade_manager.create_trade(**sample_trade_data)
    
    assert "oluşturulamadı" in str(exc_info.value).lower()


def test_create_trade_calculates_risk(trade_manager, mock_postgres, mock_redis):
    """Risk miktarı hesaplama testi."""
    mock_postgres.execute.return_value = None
    
    trade_id = trade_manager.create_trade(
        symbol='BTCUSDT',
        side='LONG',
        entry_price=50000,
        quantity=0.1,
        stop_loss=49000,
        take_profit=52000,
        rr_ratio=2.0
    )
    
    # PostgreSQL execute çağrısını kontrol et
    call_args = mock_postgres.execute.call_args_list[0][0]
    params = call_args[1]
    
    # Risk amount: |50000 - 49000| * 0.1 = 100
    assert params[10] == 100.0  # risk_amount parametresi


# ==================== Position Update Tests ====================

def test_update_position_long(trade_manager, mock_postgres, mock_redis):
    """Long pozisyon güncelleme testi."""
    trade_id = "test-trade-123"
    
    # Mock trade data
    mock_trade = {
        'trade_id': trade_id,
        'symbol': 'BTCUSDT',
        'side': 'LONG',
        'entry_price': 50000.0,
        'quantity': 0.1,
        'entry_time': datetime.now().isoformat()
    }
    
    # get_trade() return
    mock_postgres.execute.return_value = mock_trade
    mock_redis.get.return_value = mock_trade
    
    trade_manager.update_position(trade_id, current_price=51000)
    
    # UPDATE query çağrıldı mı kontrol et
    # İlk çağrı get_trade için, ikinci update için
    assert mock_postgres.execute.call_count >= 1


def test_update_position_short(trade_manager, mock_postgres, mock_redis):
    """Short pozisyon güncelleme testi."""
    trade_id = "test-trade-456"
    
    mock_trade = {
        'trade_id': trade_id,
        'symbol': 'BTCUSDT',
        'side': 'SHORT',
        'entry_price': 50000.0,
        'quantity': 0.1,
        'entry_time': datetime.now().isoformat()
    }
    
    # Redis'ten okuma için mock
    mock_redis.get.return_value = mock_trade
    mock_postgres.execute.return_value = None  # Update query için
    
    trade_manager.update_position(trade_id, current_price=49000)
    
    # Çağrıldı mı kontrol et
    assert mock_redis.get.called or mock_postgres.execute.called


def test_update_position_not_found(trade_manager, mock_postgres, mock_redis):
    """Pozisyon bulunamadı hatası."""
    mock_postgres.execute.return_value = None
    mock_redis.get.return_value = None
    
    with pytest.raises(TradeHistoryError):
        trade_manager.update_position("nonexistent", 50000)


# ==================== Trade Closing Tests ====================

def test_close_trade_success(trade_manager, mock_postgres, mock_redis):
    """Başarılı trade kapatma testi."""
    trade_id = "test-trade-789"
    entry_time = datetime.now() - timedelta(hours=2)
    
    # Mock trade data
    mock_trade = {
        'trade_id': trade_id,
        'symbol': 'BTCUSDT',
        'side': 'LONG',
        'entry_price': 50000.0,
        'quantity': 0.1,
        'stop_loss': 49000.0,
        'entry_time': entry_time.isoformat()
    }
    
    # get_trade mock
    mock_redis.get.return_value = mock_trade
    mock_postgres.execute.return_value = None
    
    result = trade_manager.close_trade(
        trade_id,
        exit_price=52000,
        exit_reason='TP_HIT',
        fees=5.0
    )
    
    # Sonuç kontrolü
    assert result['trade_id'] == trade_id
    assert result['symbol'] == 'BTCUSDT'
    assert result['pnl'] == 200.0  # (52000 - 50000) * 0.1
    assert result['net_pnl'] == 195.0  # 200 - 5
    assert result['actual_rr'] == 2.0  # 200 / 100 (risk)
    assert result['exit_reason'] == 'TP_HIT'
    
    # Redis cache temizlendi mi?
    mock_redis.delete.assert_called_once()


def test_close_trade_stop_loss(trade_manager, mock_postgres, mock_redis):
    """Stop loss ile kapatma testi."""
    trade_id = "test-trade-sl"
    
    mock_trade = {
        'trade_id': trade_id,
        'symbol': 'BTCUSDT',
        'side': 'LONG',
        'entry_price': 50000.0,
        'quantity': 0.1,
        'stop_loss': 49000.0,
        'entry_time': datetime.now().isoformat()
    }
    
    mock_redis.get.return_value = mock_trade
    mock_postgres.execute.return_value = None
    
    result = trade_manager.close_trade(
        trade_id,
        exit_price=49000,
        exit_reason='SL_HIT'
    )
    
    # Zarar: (49000 - 50000) * 0.1 = -100
    assert result['pnl'] == -100.0
    assert result['exit_reason'] == 'SL_HIT'


def test_close_trade_not_found(trade_manager, mock_postgres, mock_redis):
    """Trade bulunamadı hatası."""
    mock_postgres.execute.return_value = None
    mock_redis.get.return_value = None
    
    with pytest.raises(TradeHistoryError):
        trade_manager.close_trade("nonexistent", 50000, "MANUAL")


# ==================== Trade Query Tests ====================

def test_get_trade_from_cache(trade_manager, mock_redis):
    """Cache'den trade alma testi."""
    trade_id = "test-trade-cache"
    cached_data = {
        'trade_id': trade_id,
        'symbol': 'BTCUSDT',
        'status': 'OPEN'
    }
    
    mock_redis.get.return_value = cached_data
    
    result = trade_manager.get_trade(trade_id, from_cache=True)
    
    assert result == cached_data
    mock_redis.get.assert_called_once()


def test_get_trade_from_db(trade_manager, mock_postgres, mock_redis):
    """DB'den trade alma testi (cache miss)."""
    trade_id = "test-trade-db"
    mock_redis.get.return_value = None
    
    db_data = {
        'trade_id': trade_id,
        'symbol': 'ETHUSDT',
        'pnl': 50.0
    }
    
    mock_postgres.execute.return_value = db_data
    
    result = trade_manager.get_trade(trade_id, from_cache=True)
    
    # Önce Redis'e baktı
    mock_redis.get.assert_called_once()
    # Sonra PostgreSQL'e gitti
    mock_postgres.execute.assert_called_once()
    assert result == db_data


def test_get_open_positions(trade_manager, mock_postgres):
    """Açık pozisyonları alma testi."""
    positions = [
        {'position_id': '1', 'symbol': 'BTCUSDT'},
        {'position_id': '2', 'symbol': 'ETHUSDT'}
    ]
    
    mock_postgres.execute.return_value = positions
    
    result = trade_manager.get_open_positions()
    
    assert len(result) == 2
    assert result[0]['symbol'] == 'BTCUSDT'
    mock_postgres.execute.assert_called_once()


def test_get_recent_trades(trade_manager, mock_postgres):
    """Son trade'leri alma testi."""
    trades = [
        {'trade_id': '1', 'symbol': 'BTCUSDT'},
        {'trade_id': '2', 'symbol': 'ETHUSDT'}
    ]
    
    mock_postgres.execute.return_value = trades
    
    result = trade_manager.get_recent_trades(limit=2)
    
    assert len(result) == 2
    
    # Query parametrelerini kontrol et
    call_args = mock_postgres.execute.call_args
    assert 'LIMIT' in call_args[0][0]


def test_get_recent_trades_with_filters(trade_manager, mock_postgres):
    """Filtreli trade sorgusu testi."""
    mock_postgres.execute.return_value = []
    
    trade_manager.get_recent_trades(
        limit=10,
        symbol='BTCUSDT',
        days=7
    )
    
    call_args = mock_postgres.execute.call_args
    query = call_args[0][0]
    params = call_args[0][1]
    
    # Symbol filtresi var mı?
    assert 'symbol' in query.lower()
    assert 'BTCUSDT' in params
    
    # Days filtresi var mı?
    assert 'interval' in query.lower()
    assert 7 in params


# ==================== Statistics Tests ====================

def test_get_stats_success(trade_manager, mock_postgres):
    """İstatistik hesaplama başarı testi."""
    # Mock stats query result
    def mock_execute_side_effect(*args, **kwargs):
        query = args[0] if args else ''
        
        # Genel stats query
        if 'COUNT(*)' in query and 'SUM(net_pnl)' in query:
            return {
                'total_trades': 100,
                'winning_trades': 60,
                'losing_trades': 40,
                'total_pnl': 1000.0,
                'avg_pnl': 10.0,
                'avg_pnl_percentage': 2.5,
                'avg_actual_rr': 1.5,
                'max_win': 200.0,
                'min_loss': -100.0,
                'avg_duration_seconds': 3600.0
            }
        # SUM winning PnL
        elif 'SUM(net_pnl)' in query and 'net_pnl > 0' in query:
            return (2000.0,)  # Tuple
        # SUM losing PnL
        elif 'SUM(net_pnl)' in query and 'net_pnl <= 0' in query:
            return (-1000.0,)  # Tuple
        # Streaks query
        elif 'ORDER BY exit_time ASC' in query and 'COUNT' not in query:
            return [(10.0,), (20.0,), (-5.0,), (15.0,), (-8.0,), (-3.0,)]
        else:
            return []
    
    mock_postgres.execute.side_effect = mock_execute_side_effect
    
    stats = trade_manager.get_stats(days=30)
    
    # Temel istatistikler
    assert stats['total_trades'] == 100
    assert stats['winning_trades'] == 60
    assert stats['win_rate'] == 60.0  # 60/100 * 100
    
    # Profit factor: 2000 / 1000 = 2.0
    assert stats['profit_factor'] == 2.0


def test_get_stats_no_trades(trade_manager, mock_postgres):
    """Trade yoksa istatistik testi."""
    mock_postgres.execute.return_value = {
        'total_trades': 0
    }
    
    stats = trade_manager.get_stats()
    
    # Boş stats döndürülmeli
    assert stats['total_trades'] == 0
    assert stats['win_rate'] == 0
    assert stats['profit_factor'] == 0


def test_get_stats_with_filters(trade_manager, mock_postgres):
    """Filtreli istatistik testi."""
    mock_postgres.execute.return_value = {
        'total_trades': 0
    }
    
    trade_manager.get_stats(days=7, symbol='BTCUSDT')
    
    # WHERE clause kontrol
    call_args = mock_postgres.execute.call_args_list[0]
    query = call_args[0][0]
    params = call_args[0][1]
    
    assert 'interval' in query.lower()
    assert 7 in params
    assert 'BTCUSDT' in params


def test_empty_stats():
    """Boş stats dict testi."""
    manager = TradeHistoryManager(Mock(), Mock())
    
    stats = manager._empty_stats()
    
    assert stats['total_trades'] == 0
    assert stats['win_rate'] == 0
    assert stats['profit_factor'] == 0
    assert stats['max_win_streak'] == 0


def test_calculate_streaks(trade_manager, mock_postgres):
    """Seri hesaplama testi."""
    # Win-win-loss-win-loss-loss pattern
    mock_postgres.execute.return_value = [
        (10.0,), (20.0,), (-5.0,), (15.0,), (-8.0,), (-3.0,)
    ]
    
    streaks = trade_manager._calculate_streaks("", [])
    
    # Max win streak: 2 (ilk iki trade)
    # Max loss streak: 2 (son iki trade)
    assert streaks['max_win_streak'] == 2
    assert streaks['max_loss_streak'] == 2


def test_calculate_max_drawdown(trade_manager, mock_postgres):
    """Drawdown hesaplama testi."""
    # Cumulative: 10, 30, 25, 40, 30
    # Peak:       10, 30, 30, 40, 40
    # DD:         0,  0,  5,  0,  10 -> Max DD = 10
    mock_postgres.execute.return_value = [
        (10.0,), (20.0,), (-5.0,), (15.0,), (-10.0,)
    ]
    
    max_dd = trade_manager._calculate_max_drawdown("", [])
    
    assert max_dd == 10.0


# ==================== Integration Tests ====================

def test_full_trade_lifecycle(trade_manager, mock_postgres, mock_redis):
    """Tam trade yaşam döngüsü testi."""
    # 1. Trade oluştur
    mock_postgres.execute.return_value = None
    
    trade_id = trade_manager.create_trade(
        symbol='BTCUSDT',
        side='LONG',
        entry_price=50000,
        quantity=0.1,
        stop_loss=49000,
        take_profit=52000,
        rr_ratio=2.0
    )
    
    assert trade_id is not None
    
    # 2. Pozisyon güncelle
    mock_trade = {
        'trade_id': trade_id,
        'symbol': 'BTCUSDT',
        'side': 'LONG',
        'entry_price': 50000.0,
        'quantity': 0.1,
        'entry_time': datetime.now().isoformat()
    }
    mock_redis.get.return_value = mock_trade
    
    trade_manager.update_position(trade_id, 51000)
    
    # 3. Trade kapat
    mock_trade['stop_loss'] = 49000.0
    mock_redis.get.return_value = mock_trade
    
    result = trade_manager.close_trade(trade_id, 52000, 'TP_HIT')
    
    assert result['pnl'] > 0
    assert result['exit_reason'] == 'TP_HIT'


# ==================== String Representation Tests ====================

def test_repr(trade_manager, mock_postgres, mock_redis):
    """String representation testi."""
    repr_str = repr(trade_manager)
    
    assert 'TradeHistoryManager' in repr_str
    assert 'postgres' in repr_str
    assert 'redis' in repr_str


# ==================== Parametreli Testler ====================

@pytest.mark.parametrize("side,entry,exit,expected_pnl", [
    ('LONG', 50000, 52000, 200.0),   # Kar
    ('LONG', 50000, 49000, -100.0),  # Zarar
    ('SHORT', 50000, 48000, 200.0),  # Kar
    ('SHORT', 50000, 51000, -100.0), # Zarar
])
def test_pnl_calculation(trade_manager, mock_postgres, mock_redis, side, entry, exit, expected_pnl):
    """Çeşitli senaryolar için PnL hesaplama testi."""
    trade_id = "test-pnl"
    
    mock_trade = {
        'trade_id': trade_id,
        'symbol': 'BTCUSDT',
        'side': side,
        'entry_price': float(entry),
        'quantity': 0.1,
        'stop_loss': 49000.0,
        'entry_time': datetime.now().isoformat()
    }
    
    mock_redis.get.return_value = mock_trade
    mock_postgres.execute.return_value = None
    
    result = trade_manager.close_trade(trade_id, exit, 'MANUAL')
    
    assert result['pnl'] == expected_pnl


# ==================== Test Runner ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])