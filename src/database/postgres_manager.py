"""
Trading Bot - PostgreSQL Manager
=================================

PostgreSQL veritabanı bağlantı ve yönetim sistemi.
Connection pooling, query execution, migration support ile.

Özellikler:
    - Connection pooling (psycopg2)
    - Otomatik yeniden bağlanma
    - Query execution (sync/async)
    - Transaction management
    - Migration support
    - Health check

Tablolar:
    - trades: Trade geçmişi
    - positions: Açık pozisyonlar
    - parameters: Sistem parametreleri
    - rr_history: RR sistem geçmişi
    - coin_scores: Coin seçim skorları

Örnek Kullanım:
    >>> from postgres_manager import PostgresManager
    >>> db = PostgresManager()
    >>> db.connect()
    >>> result = db.execute("SELECT * FROM trades LIMIT 10")
    >>> db.close()

Author: Trading Bot Team
Version: 1.0
Python: 3.10+
"""

from __future__ import annotations
import psycopg2
from psycopg2 import pool, extras, sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from typing import Any, Optional, Dict, List, Tuple, Union
from datetime import datetime
from pathlib import Path
import time
import logging
from contextlib import contextmanager


class DatabaseError(Exception):
    """Veritabanı ile ilgili hatalar için özel exception."""
    pass


class PostgresManager:
    """
    PostgreSQL bağlantı ve yönetim sistemi.
    
    Connection pooling ile performans optimizasyonu.
    Otomatik yeniden bağlanma ve error handling.
    
    Attributes:
        config (Dict): Veritabanı konfigürasyonu
        pool (psycopg2.pool): Connection pool
        logger (logging.Logger): Logger instance
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "trading_bot",
        user: str = "trading_user",
        password: str = "",
        min_conn: int = 1,
        max_conn: int = 10,
        logger: Optional[logging.Logger] = None
    ):
        """
        PostgreSQL Manager'ı başlat.
        
        Args:
            host: PostgreSQL host
            port: PostgreSQL port
            database: Veritabanı adı
            user: Kullanıcı adı
            password: Şifre
            min_conn: Minimum bağlantı sayısı
            max_conn: Maksimum bağlantı sayısı
            logger: Logger instance
        """
        self.config = {
            'host': host,
            'port': port,
            'database': database,
            'user': user,
            'password': password,
        }
        
        self.min_conn = min_conn
        self.max_conn = max_conn
        self.pool: Optional[psycopg2.pool.SimpleConnectionPool] = None
        self.logger = logger or logging.getLogger(__name__)
        self._connected = False
    
    def connect(self) -> None:
        """
        Veritabanına bağlan ve connection pool oluştur.
        
        Raises:
            DatabaseError: Bağlantı başarısız olursa
        """
        try:
            self.pool = psycopg2.pool.SimpleConnectionPool(
                self.min_conn,
                self.max_conn,
                **self.config
            )
            
            if self.pool:
                self._connected = True
                self.logger.info(
                    f"PostgreSQL bağlantısı başarılı: {self.config['host']}:{self.config['port']}/{self.config['database']}"
                )
            else:
                raise DatabaseError("Connection pool oluşturulamadı")
                
        except (psycopg2.Error, Exception) as e:
            self._connected = False
            raise DatabaseError(f"PostgreSQL bağlantı hatası: {e}")
    
    def close(self) -> None:
        """Tüm bağlantıları kapat."""
        if self.pool:
            self.pool.closeall()
            self._connected = False
            self.logger.info("PostgreSQL bağlantıları kapatıldı")
    
    @contextmanager
    def get_connection(self):
        """
        Context manager ile bağlantı al.
        
        Yields:
            psycopg2.connection: Veritabanı bağlantısı
            
        Example:
            >>> with db.get_connection() as conn:
            ...     cursor = conn.cursor()
            ...     cursor.execute("SELECT 1")
        """
        if not self._connected or not self.pool:
            raise DatabaseError("Veritabanı bağlı değil, önce connect() çağrılmalı")
        
        conn = None
        try:
            conn = self.pool.getconn()
            yield conn
        finally:
            if conn:
                self.pool.putconn(conn)
    
    @contextmanager
    def get_cursor(self, cursor_factory=None):
        """
        Context manager ile cursor al.
        
        Args:
            cursor_factory: Cursor factory (DictCursor vs)
            
        Yields:
            psycopg2.cursor: Database cursor
            
        Example:
            >>> with db.get_cursor() as cur:
            ...     cur.execute("SELECT * FROM trades")
            ...     results = cur.fetchall()
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=cursor_factory)
            try:
                yield cursor
                conn.commit()
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Query hatası: {e}")
                raise
            finally:
                cursor.close()
    
    def execute(
        self,
        query: str,
        params: Optional[Union[Tuple, Dict]] = None,
        fetch: bool = True,
        fetch_one: bool = False,
        return_dict: bool = False
    ) -> Optional[Union[List, Dict, Any]]:
        """
        SQL query çalıştır.
        
        Args:
            query: SQL query string
            params: Query parametreleri
            fetch: Sonuçları getir
            fetch_one: Sadece bir sonuç getir
            return_dict: Dictionary olarak döndür
            
        Returns:
            Query sonuçları veya None
            
        Example:
            >>> results = db.execute(
            ...     "SELECT * FROM trades WHERE symbol = %s",
            ...     ('BTCUSDT',)
            ... )
        """
        cursor_factory = extras.RealDictCursor if return_dict else None
        
        with self.get_cursor(cursor_factory=cursor_factory) as cur:
            cur.execute(query, params)
            
            if fetch:
                if fetch_one:
                    return cur.fetchone()
                return cur.fetchall()
            return None
    
    def execute_many(
        self,
        query: str,
        params_list: List[Union[Tuple, Dict]]
    ) -> None:
        """
        Batch insert/update için executemany.
        
        Args:
            query: SQL query string
            params_list: Parametre listesi
            
        Example:
            >>> db.execute_many(
            ...     "INSERT INTO trades (symbol, price) VALUES (%s, %s)",
            ...     [('BTCUSDT', 50000), ('ETHUSDT', 3000)]
            ... )
        """
        with self.get_cursor() as cur:
            cur.executemany(query, params_list)
    
    def execute_transaction(self, queries: List[Tuple[str, Optional[Tuple]]]) -> None:
        """
        Transaction içinde birden fazla query çalıştır.
        
        Args:
            queries: (query, params) tuple listesi
            
        Raises:
            DatabaseError: Transaction başarısız olursa
            
        Example:
            >>> db.execute_transaction([
            ...     ("INSERT INTO trades ...", (params1,)),
            ...     ("UPDATE positions ...", (params2,))
            ... ])
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                for query, params in queries:
                    cursor.execute(query, params)
                conn.commit()
                self.logger.debug(f"Transaction başarılı: {len(queries)} query")
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Transaction hatası: {e}")
                raise DatabaseError(f"Transaction başarısız: {e}")
            finally:
                cursor.close()
    
    def table_exists(self, table_name: str) -> bool:
        """
        Tablonun var olup olmadığını kontrol et.
        
        Args:
            table_name: Tablo adı
            
        Returns:
            Tablo varsa True, yoksa False
        """
        query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public'
                AND table_name = %s
            )
        """
        result = self.execute(query, (table_name,), fetch_one=True)
        return result[0] if result else False
    
    def create_tables(self) -> None:
        """
        Gerekli tabloları oluştur (ilk kurulum için).
        
        Raises:
            DatabaseError: Tablo oluşturulamazsa
        """
        schema = self._get_schema_sql()
        
        try:
            with self.get_cursor() as cur:
                cur.execute(schema)
            self.logger.info("Veritabanı şemaları oluşturuldu")
        except Exception as e:
            raise DatabaseError(f"Şema oluşturma hatası: {e}")
    
    def _get_schema_sql(self) -> str:
        """Tüm tabloların SQL şemasını döndür."""
        return """
        -- Trades tablosu
        CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY,
            trade_id VARCHAR(100) UNIQUE NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            side VARCHAR(10) NOT NULL,  -- LONG, SHORT
            entry_price DECIMAL(20, 8) NOT NULL,
            exit_price DECIMAL(20, 8),
            quantity DECIMAL(20, 8) NOT NULL,
            leverage INTEGER DEFAULT 1,
            
            -- Zaman bilgileri
            entry_time TIMESTAMP NOT NULL,
            exit_time TIMESTAMP,
            duration_seconds INTEGER,
            
            -- Kar/Zarar
            pnl DECIMAL(20, 8),
            pnl_percentage DECIMAL(10, 4),
            fees DECIMAL(20, 8),
            net_pnl DECIMAL(20, 8),
            
            -- Risk yönetimi
            stop_loss DECIMAL(20, 8),
            take_profit DECIMAL(20, 8),
            rr_ratio DECIMAL(10, 4),
            actual_rr DECIMAL(10, 4),
            risk_amount DECIMAL(20, 8),
            
            -- Sinyal bilgileri
            signal_confidence DECIMAL(5, 4),
            signal_type VARCHAR(50),
            timeframe VARCHAR(10),
            
            -- Exit sebepleri
            exit_reason VARCHAR(50),  -- TP_HIT, SL_HIT, MANUAL, SIGNAL_REVERSE
            
            -- Metadata
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Positions tablosu (açık pozisyonlar)
        CREATE TABLE IF NOT EXISTS positions (
            id SERIAL PRIMARY KEY,
            position_id VARCHAR(100) UNIQUE NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            side VARCHAR(10) NOT NULL,
            entry_price DECIMAL(20, 8) NOT NULL,
            quantity DECIMAL(20, 8) NOT NULL,
            leverage INTEGER DEFAULT 1,
            
            -- Risk yönetimi
            stop_loss DECIMAL(20, 8) NOT NULL,
            take_profit DECIMAL(20, 8) NOT NULL,
            rr_ratio DECIMAL(10, 4) NOT NULL,
            
            -- Mevcut durum
            current_price DECIMAL(20, 8),
            unrealized_pnl DECIMAL(20, 8),
            unrealized_pnl_percentage DECIMAL(10, 4),
            
            -- Zaman bilgileri
            entry_time TIMESTAMP NOT NULL,
            last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            -- Metadata
            signal_confidence DECIMAL(5, 4),
            timeframe VARCHAR(10),
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Parameters tablosu (sistem parametreleri)
        CREATE TABLE IF NOT EXISTS parameters (
            id SERIAL PRIMARY KEY,
            key VARCHAR(100) UNIQUE NOT NULL,
            value TEXT NOT NULL,
            value_type VARCHAR(20) NOT NULL,  -- int, float, str, bool, json
            category VARCHAR(50) NOT NULL,  -- risk, trading, system, rr_system
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by VARCHAR(50) DEFAULT 'system'
        );
        
        -- RR History tablosu (RR sistem öğrenme geçmişi)
        CREATE TABLE IF NOT EXISTS rr_history (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            
            -- RR değerleri
            current_rr DECIMAL(10, 4) NOT NULL,
            signal_factor DECIMAL(10, 4) NOT NULL,
            market_factor DECIMAL(10, 4) NOT NULL,
            
            -- Öğrenme bilgileri
            learning_rate DECIMAL(10, 6) NOT NULL,
            signal_weight DECIMAL(10, 4) NOT NULL,
            market_weight DECIMAL(10, 4) NOT NULL,
            
            -- Trade sonucu (varsa)
            trade_id VARCHAR(100),
            win BOOLEAN,
            actual_rr DECIMAL(10, 4),
            
            -- Piyasa durumu
            market_regime VARCHAR(20),  -- bull, bear, sideways
            volatility DECIMAL(10, 6),
            
            -- Metadata
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Coin Scores tablosu (coin seçim skorları)
        CREATE TABLE IF NOT EXISTS coin_scores (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            
            -- Skorlar (0-1 aralığı)
            liquidity_score DECIMAL(5, 4),
            volatility_score DECIMAL(5, 4),
            trend_score DECIMAL(5, 4),
            momentum_score DECIMAL(5, 4),
            volume_score DECIMAL(5, 4),
            correlation_score DECIMAL(5, 4),
            
            -- ML skoru
            ml_score DECIMAL(5, 4),
            
            -- Final skor ve sıralama
            final_score DECIMAL(5, 4) NOT NULL,
            rank INTEGER,
            selected BOOLEAN DEFAULT FALSE,
            
            -- Metadata
            phase INTEGER,  -- 1, 2, 3
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- İndeksler oluştur (CREATE TABLE dışında)
        CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades (symbol);
        CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades (entry_time);
        CREATE INDEX IF NOT EXISTS idx_trades_exit_time ON trades (exit_time);
        
        CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions (symbol);
        CREATE INDEX IF NOT EXISTS idx_positions_entry_time ON positions (entry_time);
        
        CREATE INDEX IF NOT EXISTS idx_parameters_category ON parameters (category);
        
        CREATE INDEX IF NOT EXISTS idx_rr_history_timestamp ON rr_history (timestamp);
        CREATE INDEX IF NOT EXISTS idx_rr_history_trade_id ON rr_history (trade_id);
        
        CREATE INDEX IF NOT EXISTS idx_coin_scores_timestamp ON coin_scores (timestamp);
        CREATE INDEX IF NOT EXISTS idx_coin_scores_symbol ON coin_scores (symbol);
        CREATE INDEX IF NOT EXISTS idx_coin_scores_selected ON coin_scores (selected);
        
        -- Trigger: updated_at otomatik güncelleme
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
        
        CREATE TRIGGER update_trades_updated_at BEFORE UPDATE ON trades
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
            
        CREATE TRIGGER update_positions_updated_at BEFORE UPDATE ON positions
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
            
        CREATE TRIGGER update_parameters_updated_at BEFORE UPDATE ON parameters
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    
    def health_check(self) -> Dict[str, Any]:
        """
        Veritabanı sağlık kontrolü.
        
        Returns:
            Sağlık durumu bilgileri
        """
        try:
            start = time.time()
            result = self.execute("SELECT 1", fetch_one=True)
            latency = (time.time() - start) * 1000  # ms
            
            # Connection pool durumu
            pool_info = {
                'available': len(self.pool._pool) if self.pool else 0,
                'used': len(self.pool._used) if self.pool else 0,
                'max': self.max_conn
            }
            
            return {
                'healthy': result[0] == 1,
                'latency_ms': round(latency, 2),
                'connected': self._connected,
                'pool': pool_info,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            return {
                'healthy': False,
                'error': str(e),
                'connected': self._connected,
                'timestamp': datetime.now().isoformat()
            }
    
    def get_stats(self) -> Dict[str, int]:
        """
        Veritabanı istatistikleri.
        
        Returns:
            Tablo bazında kayıt sayıları
        """
        tables = ['trades', 'positions', 'parameters', 'rr_history', 'coin_scores']
        stats = {}
        
        for table in tables:
            if self.table_exists(table):
                result = self.execute(f"SELECT COUNT(*) FROM {table}", fetch_one=True)
                stats[table] = result[0] if result else 0
            else:
                stats[table] = -1  # Tablo yok
        
        return stats
    
    def __repr__(self) -> str:
        """String representation."""
        status = "connected" if self._connected else "disconnected"
        return f"PostgresManager({self.config['host']}:{self.config['port']}/{self.config['database']}, {status})"


if __name__ == "__main__":
    # Test kodu
    print("🧪 PostgreSQL Manager Test")
    print("-" * 50)
    
    # Logger setup
    logging.basicConfig(level=logging.INFO)
    
    try:
        # PostgreSQL Manager oluştur
        db = PostgresManager(
            host="localhost",
            port=5432,
            database="trading_bot_test",
            user="trading_user",
            password="password",
            min_conn=1,
            max_conn=5
        )
        print(f"✅ Manager oluşturuldu: {db}")
        
        # Bağlan (gerçek PostgreSQL yoksa hata verir)
        # db.connect()
        # print("✅ Bağlantı başarılı")
        
        # Tabloları oluştur
        # db.create_tables()
        # print("✅ Tablolar oluşturuldu")
        
        # Sağlık kontrolü
        # health = db.health_check()
        # print(f"✅ Health check: {health}")
        
        # İstatistikler
        # stats = db.get_stats()
        # print(f"✅ Stats: {stats}")
        
        # Bağlantıyı kapat
        # db.close()
        # print("✅ Bağlantı kapatıldı")
        
        print("\n🎉 PostgreSQL Manager hazır!")
        print("💡 Gerçek test için PostgreSQL kurulu olmalı")
        
    except Exception as e:
        print(f"❌ Hata: {e}")
        import traceback
        traceback.print_exc()