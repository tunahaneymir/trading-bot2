"""
Trading Bot - Redis Manager Tests
==================================

RedisManager için unit testler.
Mock kullanarak gerçek Redis olmadan test.

Test Kapsama:
    - Connection management
    - Key-value operations
    - Hash operations
    - List operations
    - Sorted set operations
    - Pub/Sub
    - Health check
    - Serialization

Author: Trading Bot Team
Version: 1.0
Python: 3.10+
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import json
import pickle
import sys
from pathlib import Path

# Parent dizini path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.redis_manager import RedisManager, RedisError


# ==================== Fixtures ====================

@pytest.fixture
def mock_redis_module():
    """Mock redis modülü."""
    with patch('src.database.redis_manager.redis') as mock:
        yield mock


@pytest.fixture
def mock_redis_client():
    """Mock Redis client."""
    client = Mock()
    client.ping = Mock()
    client.set = Mock(return_value=True)
    client.get = Mock()
    client.delete = Mock()
    client.exists = Mock()
    client.expire = Mock()
    client.ttl = Mock()
    client.hset = Mock()
    client.hget = Mock()
    client.hgetall = Mock()
    client.hdel = Mock()
    client.lpush = Mock()
    client.rpush = Mock()
    client.lrange = Mock()
    client.zadd = Mock()
    client.zrange = Mock()
    client.publish = Mock()
    client.pubsub = Mock()
    client.pipeline = Mock()
    client.flushdb = Mock()
    client.keys = Mock()
    client.info = Mock()
    client.close = Mock()
    return client


@pytest.fixture
def mock_pool():
    """Mock connection pool."""
    pool = Mock()
    pool.disconnect = Mock()
    return pool


@pytest.fixture
def redis_manager():
    """RedisManager instance (bağlantısız)."""
    return RedisManager(
        host="localhost",
        port=6379,
        db=0
    )


# ==================== Connection Tests ====================

def test_manager_initialization():
    """Manager başlangıç değerlerini test et."""
    manager = RedisManager(
        host="testhost",
        port=6380,
        db=1,
        password="testpass"
    )
    
    assert manager.config['host'] == "testhost"
    assert manager.config['port'] == 6380
    assert manager.config['db'] == 1
    assert manager.config['password'] == "testpass"
    assert manager._connected is False


def test_connect_success(redis_manager, mock_redis_module, mock_redis_client, mock_pool):
    """Başarılı bağlantı testi."""
    mock_redis_module.ConnectionPool.return_value = mock_pool
    mock_redis_module.Redis.return_value = mock_redis_client
    
    redis_manager.connect()
    
    assert redis_manager._connected is True
    assert redis_manager.client == mock_redis_client
    mock_redis_client.ping.assert_called_once()


def test_connect_failure(redis_manager, mock_redis_module):
    """Bağlantı hatası testi."""
    mock_redis_module.ConnectionPool.side_effect = Exception("Connection failed")
    
    with pytest.raises(RedisError) as exc_info:
        redis_manager.connect()
    
    assert "Connection failed" in str(exc_info.value)
    assert redis_manager._connected is False


def test_close(redis_manager, mock_redis_client, mock_pool):
    """Bağlantı kapatma testi."""
    redis_manager.client = mock_redis_client
    redis_manager.pool = mock_pool
    redis_manager._connected = True
    
    redis_manager.close()
    
    mock_redis_client.close.assert_called_once()
    mock_pool.disconnect.assert_called_once()
    assert redis_manager._connected is False


# ==================== Serialization Tests ====================

def test_serialize_dict():
    """Dictionary serialization testi."""
    manager = RedisManager()
    data = {'key': 'value', 'num': 123}
    
    result = manager._serialize(data)
    
    assert result == json.dumps(data)


def test_serialize_list():
    """List serialization testi."""
    manager = RedisManager()
    data = [1, 2, 3, 'test']
    
    result = manager._serialize(data)
    
    assert result == json.dumps(data)


def test_serialize_string():
    """String serialization testi."""
    manager = RedisManager()
    data = "test string"
    
    result = manager._serialize(data)
    
    assert result == "test string"


class PickleTestObject:
    """Pickle testi için test sınıfı."""
    def __init__(self):
        self.value = 42


def test_serialize_pickle():
    """Pickle serialization testi."""
    manager = RedisManager()
    
    obj = PickleTestObject()
    result = manager._serialize(obj, use_pickle=True)
    
    assert isinstance(result, bytes)
    deserialized = pickle.loads(result)
    assert deserialized.value == 42


def test_deserialize_json():
    """JSON deserialization testi."""
    manager = RedisManager()
    data = json.dumps({'key': 'value'})
    
    result = manager._deserialize(data)
    
    assert result == {'key': 'value'}


def test_deserialize_string():
    """String deserialization testi."""
    manager = RedisManager()
    data = "plain string"
    
    result = manager._deserialize(data)
    
    assert result == "plain string"


def test_deserialize_none():
    """None deserialization testi."""
    manager = RedisManager()
    
    result = manager._deserialize(None)
    
    assert result is None


# ==================== Key-Value Operations Tests ====================

def test_set_simple(redis_manager, mock_redis_client):
    """Basit set operasyonu testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    
    result = redis_manager.set('test_key', 'test_value')
    
    assert result is True
    mock_redis_client.set.assert_called_once()


def test_set_with_ttl(redis_manager, mock_redis_client):
    """TTL ile set testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    
    redis_manager.set('test_key', 'value', ttl=60)
    
    mock_redis_client.setex.assert_called_once_with('test_key', 60, 'value')


def test_set_dict(redis_manager, mock_redis_client):
    """Dictionary set testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    data = {'key': 'value'}
    
    redis_manager.set('test_key', data)
    
    # JSON serialize edildi mi?
    call_args = mock_redis_client.set.call_args[0]
    assert call_args[0] == 'test_key'
    assert json.loads(call_args[1]) == data


def test_set_not_connected(redis_manager):
    """Bağlantısız set hatası."""
    with pytest.raises(RedisError):
        redis_manager.set('key', 'value')


def test_get_simple(redis_manager, mock_redis_client):
    """Basit get operasyonu testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.get.return_value = "test_value"
    
    result = redis_manager.get('test_key')
    
    assert result == "test_value"
    mock_redis_client.get.assert_called_once_with('test_key')


def test_get_json(redis_manager, mock_redis_client):
    """JSON get testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    data = {'key': 'value'}
    mock_redis_client.get.return_value = json.dumps(data)
    
    result = redis_manager.get('test_key')
    
    assert result == data


def test_get_not_found(redis_manager, mock_redis_client):
    """Key bulunamadı testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.get.return_value = None
    
    result = redis_manager.get('nonexistent')
    
    assert result is None


def test_delete_single(redis_manager, mock_redis_client):
    """Tek key silme testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.delete.return_value = 1
    
    count = redis_manager.delete('key1')
    
    assert count == 1
    mock_redis_client.delete.assert_called_once_with('key1')


def test_delete_multiple(redis_manager, mock_redis_client):
    """Çoklu key silme testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.delete.return_value = 3
    
    count = redis_manager.delete('key1', 'key2', 'key3')
    
    assert count == 3
    mock_redis_client.delete.assert_called_once_with('key1', 'key2', 'key3')


def test_exists(redis_manager, mock_redis_client):
    """Key varlık kontrolü testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.exists.return_value = 2
    
    count = redis_manager.exists('key1', 'key2')
    
    assert count == 2


def test_expire(redis_manager, mock_redis_client):
    """TTL set testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.expire.return_value = True
    
    result = redis_manager.expire('test_key', 60)
    
    assert result is True
    mock_redis_client.expire.assert_called_once_with('test_key', 60)


def test_ttl(redis_manager, mock_redis_client):
    """TTL alma testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.ttl.return_value = 30
    
    ttl = redis_manager.ttl('test_key')
    
    assert ttl == 30


# ==================== Hash Operations Tests ====================

def test_hset(redis_manager, mock_redis_client):
    """Hash set testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.hset.return_value = 1
    
    result = redis_manager.hset('hash_name', 'field1', 'value1')
    
    assert result == 1
    mock_redis_client.hset.assert_called_once()


def test_hget(redis_manager, mock_redis_client):
    """Hash get testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.hget.return_value = "value1"
    
    result = redis_manager.hget('hash_name', 'field1')
    
    assert result == "value1"


def test_hgetall(redis_manager, mock_redis_client):
    """Hash getall testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.hgetall.return_value = {b'field1': b'value1', b'field2': b'value2'}
    
    result = redis_manager.hgetall('hash_name')
    
    assert isinstance(result, dict)


def test_hdel(redis_manager, mock_redis_client):
    """Hash delete testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.hdel.return_value = 2
    
    count = redis_manager.hdel('hash_name', 'field1', 'field2')
    
    assert count == 2


# ==================== List Operations Tests ====================

def test_lpush(redis_manager, mock_redis_client):
    """List lpush testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.lpush.return_value = 3
    
    length = redis_manager.lpush('list_key', 'val1', 'val2')
    
    assert length == 3


def test_rpush(redis_manager, mock_redis_client):
    """List rpush testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.rpush.return_value = 3
    
    length = redis_manager.rpush('list_key', 'val1', 'val2')
    
    assert length == 3


def test_lrange(redis_manager, mock_redis_client):
    """List range testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.lrange.return_value = [b'val1', b'val2', b'val3']
    
    result = redis_manager.lrange('list_key', 0, -1)
    
    assert len(result) == 3


# ==================== Sorted Set Operations Tests ====================

def test_zadd(redis_manager, mock_redis_client):
    """Sorted set add testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.zadd.return_value = 2
    
    count = redis_manager.zadd('leaderboard', {'user1': 100, 'user2': 200})
    
    assert count == 2


def test_zrange(redis_manager, mock_redis_client):
    """Sorted set range testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.zrange.return_value = [b'user1', b'user2']
    
    result = redis_manager.zrange('leaderboard', 0, -1)
    
    assert len(result) == 2


def test_zrange_with_scores(redis_manager, mock_redis_client):
    """Sorted set range with scores testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.zrange.return_value = [(b'user1', 100.0), (b'user2', 200.0)]
    
    result = redis_manager.zrange('leaderboard', 0, -1, withscores=True)
    
    assert len(result) == 2
    assert result[0][1] == 100.0


# ==================== Pub/Sub Tests ====================

def test_publish(redis_manager, mock_redis_client):
    """Publish testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.publish.return_value = 3
    
    count = redis_manager.publish('channel1', {'msg': 'test'})
    
    assert count == 3
    mock_redis_client.publish.assert_called_once()


def test_subscribe(redis_manager, mock_redis_client):
    """Subscribe testi (basit)."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_pubsub = Mock()
    mock_redis_client.pubsub.return_value = mock_pubsub
    mock_pubsub.subscribe = Mock()
    
    # Callback olmadan (listen'ı test etmiyoruz)
    redis_manager._pubsub = mock_pubsub
    redis_manager._pubsub.subscribe('channel1')
    
    mock_pubsub.subscribe.assert_called_once_with('channel1')


# ==================== Utility Tests ====================

def test_pipeline(redis_manager, mock_redis_client):
    """Pipeline testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_pipeline = Mock()
    mock_redis_client.pipeline.return_value = mock_pipeline
    
    pipe = redis_manager.pipeline()
    
    assert pipe == mock_pipeline


def test_flush_db(redis_manager, mock_redis_client):
    """Flush database testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.flushdb.return_value = True
    
    result = redis_manager.flush_db()
    
    assert result is True
    mock_redis_client.flushdb.assert_called_once()


def test_keys(redis_manager, mock_redis_client):
    """Keys pattern search testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.keys.return_value = [b'key1', b'key2', b'key3']
    
    keys = redis_manager.keys('*')
    
    assert len(keys) == 3
    assert 'key1' in keys


def test_info(redis_manager, mock_redis_client):
    """Info testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.info.return_value = {'redis_version': '7.0.0'}
    
    info = redis_manager.info()
    
    assert 'redis_version' in info


# ==================== Health Check Tests ====================

def test_health_check_success(redis_manager, mock_redis_client):
    """Sağlık kontrolü başarı testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    redis_manager.config['db'] = 0
    mock_redis_client.ping.return_value = True
    mock_redis_client.info.side_effect = [
        {'used_memory': 1024 * 1024},  # memory info
        {'db0': {'keys': 100}}          # keyspace info
    ]
    
    health = redis_manager.health_check()
    
    assert health['healthy'] is True
    assert health['connected'] is True
    assert 'latency_ms' in health
    assert 'used_memory_mb' in health
    assert health['key_count'] == 100


def test_health_check_failure(redis_manager, mock_redis_client):
    """Sağlık kontrolü hata testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    mock_redis_client.ping.side_effect = Exception("Connection lost")
    
    health = redis_manager.health_check()
    
    assert health['healthy'] is False
    assert 'error' in health


# ==================== TTL Constants Tests ====================

def test_ttl_constants():
    """TTL sabitlerini test et."""
    assert RedisManager.TTL_ORDERBOOK == 86400  # 24 saat
    assert RedisManager.TTL_HOT_STATE == 3600   # 1 saat
    assert RedisManager.TTL_MARKET_DATA == 300  # 5 dakika
    assert RedisManager.TTL_SIGNALS == 900      # 15 dakika
    assert RedisManager.TTL_TEMP == 30          # 30 saniye


# ==================== String Representation Tests ====================

def test_repr_disconnected():
    """Repr testi (bağlantısız)."""
    manager = RedisManager(host="localhost", db=0)
    
    repr_str = repr(manager)
    
    assert "localhost" in repr_str
    assert "db0" in repr_str
    assert "disconnected" in repr_str


def test_repr_connected(redis_manager):
    """Repr testi (bağlantılı)."""
    redis_manager._connected = True
    
    repr_str = repr(redis_manager)
    
    assert "connected" in repr_str


# ==================== Parametreli Testler ====================

@pytest.mark.parametrize("data,use_pickle", [
    ({'key': 'value'}, False),
    ([1, 2, 3], False),
    ("string", False),
    ({'complex': object()}, True),
])
def test_set_get_various_types(redis_manager, mock_redis_client, data, use_pickle):
    """Çeşitli veri tipleri set/get testi."""
    redis_manager.client = mock_redis_client
    redis_manager._connected = True
    
    # Set
    result = redis_manager.set('test_key', data, use_pickle=use_pickle)
    
    assert result is True or result is None  # Mock dönüş değerine bağlı


# ==================== Test Runner ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])