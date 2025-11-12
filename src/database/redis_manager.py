"""
Trading Bot - Redis Manager
============================

Redis cache ve pub/sub yönetim sistemi.
Hot state caching, orderbook, real-time data için.

Özellikler:
    - Key-value caching (TTL support)
    - Pub/Sub mesajlaşma
    - Hash operasyonları
    - Sorted sets (orderbook için)
    - Pipeline işlemleri
    - Health check

Cache Kategorileri:
    - orderbook: Order book snapshots (24h)
    - hot_state: Sistem durumu (1h)
    - market_data: Piyasa verileri (5m)
    - signals: Trading sinyalleri (15m)
    - temp: Geçici veriler (30s)

Örnek Kullanım:
    >>> from redis_manager import RedisManager
    >>> redis = RedisManager()
    >>> redis.connect()
    >>> redis.set('key', 'value', ttl=60)
    >>> value = redis.get('key')
    >>> redis.close()

Author: Trading Bot Team
Version: 1.0
Python: 3.10+
"""

from __future__ import annotations
import redis
from redis.connection import ConnectionPool
from typing import Any, Optional, Dict, List, Union, Callable
import json
import pickle
import time
import logging
from datetime import datetime, timedelta


class RedisError(Exception):
    """Redis ile ilgili hatalar için özel exception."""
    pass


class RedisManager:
    """
    Redis cache ve pub/sub yönetim sistemi.
    
    Connection pooling ve otomatik serialization ile.
    
    Attributes:
        config (Dict): Redis konfigürasyonu
        client (redis.Redis): Redis client
        pool (redis.ConnectionPool): Connection pool
        logger (logging.Logger): Logger instance
    """
    
    # TTL sabitleri (saniye)
    TTL_ORDERBOOK = 86400      # 24 saat
    TTL_HOT_STATE = 3600       # 1 saat
    TTL_MARKET_DATA = 300      # 5 dakika
    TTL_SIGNALS = 900          # 15 dakika
    TTL_TEMP = 30              # 30 saniye
    TTL_DEFAULT = 3600         # 1 saat (default)
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        max_connections: int = 50,
        decode_responses: bool = False,
        logger: Optional[logging.Logger] = None
    ):
        """
        Redis Manager'ı başlat.
        
        Args:
            host: Redis host
            port: Redis port
            db: Database numarası (0-15)
            password: Redis şifresi
            max_connections: Maksimum bağlantı sayısı
            decode_responses: Otomatik decode (str dönüşümü)
            logger: Logger instance
        """
        self.config = {
            'host': host,
            'port': port,
            'db': db,
            'password': password,
            'decode_responses': decode_responses,
        }
        
        self.max_connections = max_connections
        self.pool: Optional[ConnectionPool] = None
        self.client: Optional[redis.Redis] = None
        self.logger = logger or logging.getLogger(__name__)
        self._connected = False
        self._pubsub = None
    
    def connect(self) -> None:
        """
        Redis'e bağlan ve connection pool oluştur.
        
        Raises:
            RedisError: Bağlantı başarısız olursa
        """
        try:
            # Connection pool oluştur
            self.pool = redis.ConnectionPool(
                host=self.config['host'],
                port=self.config['port'],
                db=self.config['db'],
                password=self.config['password'],
                decode_responses=self.config['decode_responses'],
                max_connections=self.max_connections
            )
            
            # Client oluştur
            self.client = redis.Redis(connection_pool=self.pool)
            
            # Bağlantıyı test et
            self.client.ping()
            
            self._connected = True
            self.logger.info(
                f"Redis bağlantısı başarılı: {self.config['host']}:{self.config['port']}/{self.config['db']}"
            )
            
        except (redis.RedisError, Exception) as e:
            self._connected = False
            raise RedisError(f"Redis bağlantı hatası: {e}")
    
    def close(self) -> None:
        """Redis bağlantısını kapat."""
        if self._pubsub:
            self._pubsub.close()
        
        if self.client:
            self.client.close()
        
        if self.pool:
            self.pool.disconnect()
        
        self._connected = False
        self.logger.info("Redis bağlantısı kapatıldı")
    
    def _serialize(self, value: Any, use_pickle: bool = False) -> Union[str, bytes]:
        """
        Değeri serialize et.
        
        Args:
            value: Serialize edilecek değer
            use_pickle: Pickle kullan (complex objeler için)
            
        Returns:
            Serialize edilmiş değer
        """
        if use_pickle:
            return pickle.dumps(value)
        
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        
        return str(value)
    
    def _deserialize(self, value: Union[str, bytes], use_pickle: bool = False) -> Any:
        """
        Değeri deserialize et.
        
        Args:
            value: Deserialize edilecek değer
            use_pickle: Pickle kullanıldı mı
            
        Returns:
            Deserialize edilmiş değer
        """
        if value is None:
            return None
        
        if use_pickle:
            return pickle.loads(value)
        
        # String ise JSON parse etmeyi dene
        if isinstance(value, (str, bytes)):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        
        return value
    
    # ==================== Key-Value Operations ====================
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        use_pickle: bool = False
    ) -> bool:
        """
        Key-value set et.
        
        Args:
            key: Cache key
            value: Değer (dict, list, str, int, custom object)
            ttl: Time-to-live (saniye)
            use_pickle: Complex objeler için pickle kullan
            
        Returns:
            Başarılı ise True
            
        Example:
            >>> redis.set('btc_price', 50000, ttl=60)
            >>> redis.set('orderbook:BTCUSDT', orderbook_data, ttl=RedisManager.TTL_ORDERBOOK)
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        try:
            serialized = self._serialize(value, use_pickle)
            
            if ttl:
                return self.client.setex(key, ttl, serialized)
            else:
                return self.client.set(key, serialized)
                
        except (redis.RedisError, Exception) as e:
            self.logger.error(f"Redis SET hatası: {e}")
            return False
    
    def get(self, key: str, use_pickle: bool = False) -> Any:
        """
        Key'den değer al.
        
        Args:
            key: Cache key
            use_pickle: Pickle kullanıldı mı
            
        Returns:
            Değer veya None (bulunamazsa)
            
        Example:
            >>> price = redis.get('btc_price')
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        try:
            value = self.client.get(key)
            return self._deserialize(value, use_pickle)
        except (redis.RedisError, Exception) as e:
            self.logger.error(f"Redis GET hatası: {e}")
            return None
    
    def delete(self, *keys: str) -> int:
        """
        Key(ler)i sil.
        
        Args:
            *keys: Silinecek key'ler
            
        Returns:
            Silinen key sayısı
            
        Example:
            >>> redis.delete('key1', 'key2', 'key3')
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        try:
            return self.client.delete(*keys)
        except (redis.RedisError, Exception) as e:
            self.logger.error(f"Redis DELETE hatası: {e}")
            return 0
    
    def exists(self, *keys: str) -> int:
        """
        Key(ler)in varlığını kontrol et.
        
        Args:
            *keys: Kontrol edilecek key'ler
            
        Returns:
            Var olan key sayısı
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        return self.client.exists(*keys)
    
    def expire(self, key: str, ttl: int) -> bool:
        """
        Key'e TTL ekle/güncelle.
        
        Args:
            key: Cache key
            ttl: Time-to-live (saniye)
            
        Returns:
            Başarılı ise True
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        return self.client.expire(key, ttl)
    
    def ttl(self, key: str) -> int:
        """
        Key'in kalan TTL'ini al.
        
        Args:
            key: Cache key
            
        Returns:
            Kalan süre (saniye), -1 (TTL yok), -2 (key yok)
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        return self.client.ttl(key)
    
    # ==================== Hash Operations ====================
    
    def hset(self, name: str, key: str, value: Any, use_pickle: bool = False) -> int:
        """
        Hash field set et.
        
        Args:
            name: Hash adı
            key: Field adı
            value: Değer
            use_pickle: Pickle kullan
            
        Returns:
            Eklenen field sayısı (0 veya 1)
            
        Example:
            >>> redis.hset('positions', 'BTCUSDT', position_data)
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        serialized = self._serialize(value, use_pickle)
        return self.client.hset(name, key, serialized)
    
    def hget(self, name: str, key: str, use_pickle: bool = False) -> Any:
        """
        Hash field al.
        
        Args:
            name: Hash adı
            key: Field adı
            use_pickle: Pickle kullanıldı mı
            
        Returns:
            Değer veya None
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        value = self.client.hget(name, key)
        return self._deserialize(value, use_pickle)
    
    def hgetall(self, name: str, use_pickle: bool = False) -> Dict:
        """
        Hash'in tüm field'larını al.
        
        Args:
            name: Hash adı
            use_pickle: Pickle kullanıldı mı
            
        Returns:
            Dictionary (field: value)
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        data = self.client.hgetall(name)
        
        if use_pickle:
            return {k: self._deserialize(v, use_pickle) for k, v in data.items()}
        
        return data
    
    def hdel(self, name: str, *keys: str) -> int:
        """
        Hash field(lar)ını sil.
        
        Args:
            name: Hash adı
            *keys: Silinecek field'lar
            
        Returns:
            Silinen field sayısı
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        return self.client.hdel(name, *keys)
    
    # ==================== List Operations ====================
    
    def lpush(self, key: str, *values: Any, use_pickle: bool = False) -> int:
        """
        List'in başına eleman ekle.
        
        Args:
            key: List key
            *values: Eklenecek değerler
            use_pickle: Pickle kullan
            
        Returns:
            List'in yeni uzunluğu
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        serialized = [self._serialize(v, use_pickle) for v in values]
        return self.client.lpush(key, *serialized)
    
    def rpush(self, key: str, *values: Any, use_pickle: bool = False) -> int:
        """
        List'in sonuna eleman ekle.
        
        Args:
            key: List key
            *values: Eklenecek değerler
            use_pickle: Pickle kullan
            
        Returns:
            List'in yeni uzunluğu
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        serialized = [self._serialize(v, use_pickle) for v in values]
        return self.client.rpush(key, *serialized)
    
    def lrange(
        self,
        key: str,
        start: int = 0,
        end: int = -1,
        use_pickle: bool = False
    ) -> List:
        """
        List'ten range al.
        
        Args:
            key: List key
            start: Başlangıç index
            end: Bitiş index (-1 = son)
            use_pickle: Pickle kullanıldı mı
            
        Returns:
            Değer listesi
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        values = self.client.lrange(key, start, end)
        return [self._deserialize(v, use_pickle) for v in values]
    
    # ==================== Sorted Set Operations ====================
    
    def zadd(self, key: str, mapping: Dict[str, float]) -> int:
        """
        Sorted set'e eleman ekle.
        
        Args:
            key: Set key
            mapping: {member: score} dictionary
            
        Returns:
            Eklenen eleman sayısı
            
        Example:
            >>> redis.zadd('leaderboard', {'user1': 100, 'user2': 200})
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        return self.client.zadd(key, mapping)
    
    def zrange(
        self,
        key: str,
        start: int = 0,
        end: int = -1,
        withscores: bool = False
    ) -> List:
        """
        Sorted set'ten range al (score'a göre sıralı).
        
        Args:
            key: Set key
            start: Başlangıç index
            end: Bitiş index
            withscores: Score'ları da döndür
            
        Returns:
            Member listesi veya (member, score) tuple listesi
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        return self.client.zrange(key, start, end, withscores=withscores)
    
    # ==================== Pub/Sub Operations ====================
    
    def publish(self, channel: str, message: Any, use_pickle: bool = False) -> int:
        """
        Kanala mesaj gönder.
        
        Args:
            channel: Kanal adı
            message: Mesaj
            use_pickle: Pickle kullan
            
        Returns:
            Mesajı alan subscriber sayısı
            
        Example:
            >>> redis.publish('signals', {'symbol': 'BTCUSDT', 'action': 'BUY'})
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        serialized = self._serialize(message, use_pickle)
        return self.client.publish(channel, serialized)
    
    def subscribe(self, *channels: str, callback: Optional[Callable] = None) -> None:
        """
        Kanala abone ol.
        
        Args:
            *channels: Kanal adları
            callback: Mesaj geldiğinde çağrılacak fonksiyon
            
        Example:
            >>> def handle_message(message):
            ...     print(f"Mesaj geldi: {message}")
            >>> redis.subscribe('signals', callback=handle_message)
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        if not self._pubsub:
            self._pubsub = self.client.pubsub()
        
        self._pubsub.subscribe(*channels)
        
        if callback:
            for message in self._pubsub.listen():
                if message['type'] == 'message':
                    data = self._deserialize(message['data'])
                    callback(data)
    
    # ==================== Batch Operations ====================
    
    def pipeline(self) -> redis.client.Pipeline:
        """
        Pipeline oluştur (batch işlemler için).
        
        Returns:
            Pipeline instance
            
        Example:
            >>> pipe = redis.pipeline()
            >>> pipe.set('key1', 'value1')
            >>> pipe.set('key2', 'value2')
            >>> pipe.execute()
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        return self.client.pipeline()
    
    # ==================== Utility Methods ====================
    
    def flush_db(self) -> bool:
        """
        Mevcut database'i temizle (TEHLİKELİ!).
        
        Returns:
            Başarılı ise True
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        self.logger.warning(f"Redis DB {self.config['db']} temizleniyor!")
        return self.client.flushdb()
    
    def keys(self, pattern: str = "*") -> List[str]:
        """
        Pattern'e uyan key'leri listele.
        
        Args:
            pattern: Glob pattern (*, ?, [])
            
        Returns:
            Key listesi
            
        Example:
            >>> redis.keys('orderbook:*')
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        return [key.decode() if isinstance(key, bytes) else key 
                for key in self.client.keys(pattern)]
    
    def info(self, section: Optional[str] = None) -> Dict:
        """
        Redis sunucu bilgilerini al.
        
        Args:
            section: Bilgi kategorisi (memory, stats, vs)
            
        Returns:
            Bilgi dictionary
        """
        if not self._connected:
            raise RedisError("Redis bağlı değil")
        
        return self.client.info(section)
    
    def health_check(self) -> Dict[str, Any]:
        """
        Redis sağlık kontrolü.
        
        Returns:
            Sağlık durumu bilgileri
        """
        try:
            start = time.time()
            self.client.ping()
            latency = (time.time() - start) * 1000  # ms
            
            # Bellek kullanımı
            info = self.client.info('memory')
            used_memory_mb = info.get('used_memory', 0) / (1024 * 1024)
            
            # Key sayısı
            db_info = self.client.info('keyspace')
            db_key = f'db{self.config["db"]}'
            key_count = db_info.get(db_key, {}).get('keys', 0)
            
            return {
                'healthy': True,
                'latency_ms': round(latency, 2),
                'connected': self._connected,
                'used_memory_mb': round(used_memory_mb, 2),
                'key_count': key_count,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            return {
                'healthy': False,
                'error': str(e),
                'connected': self._connected,
                'timestamp': datetime.now().isoformat()
            }
    
    def __repr__(self) -> str:
        """String representation."""
        status = "connected" if self._connected else "disconnected"
        return f"RedisManager({self.config['host']}:{self.config['port']}/db{self.config['db']}, {status})"


if __name__ == "__main__":
    # Test kodu
    print("🧪 Redis Manager Test")
    print("-" * 50)
    
    # Logger setup
    logging.basicConfig(level=logging.INFO)
    
    try:
        # Redis Manager oluştur
        redis_mgr = RedisManager(
            host="localhost",
            port=6379,
            db=0
        )
        print(f"✅ Manager oluşturuldu: {redis_mgr}")
        
        # Bağlan (gerçek Redis yoksa hata verir)
        # redis_mgr.connect()
        # print("✅ Bağlantı başarılı")
        
        # Key-value test
        # redis_mgr.set('test_key', {'data': 'test'}, ttl=60)
        # value = redis_mgr.get('test_key')
        # print(f"✅ Get: {value}")
        
        # Hash test
        # redis_mgr.hset('positions', 'BTCUSDT', {'price': 50000})
        # pos = redis_mgr.hget('positions', 'BTCUSDT')
        # print(f"✅ Hash: {pos}")
        
        # List test
        # redis_mgr.rpush('signals', {'signal': 'BUY'}, {'signal': 'SELL'})
        # signals = redis_mgr.lrange('signals')
        # print(f"✅ List: {signals}")
        
        # Sağlık kontrolü
        # health = redis_mgr.health_check()
        # print(f"✅ Health: {health}")
        
        # Bağlantıyı kapat
        # redis_mgr.close()
        # print("✅ Bağlantı kapatıldı")
        
        print("\n🎉 Redis Manager hazır!")
        print("💡 Gerçek test için Redis kurulu olmalı")
        
    except Exception as e:
        print(f"❌ Hata: {e}")
        import traceback
        traceback.print_exc()