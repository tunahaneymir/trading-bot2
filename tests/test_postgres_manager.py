"""
Trading Bot - PostgreSQL Manager Tests
=======================================

PostgresManager için unit testler.
Mock kullanarak gerçek veritabanı olmadan test.

Test Kapsama:
    - Connection management
    - Query execution
    - Transaction handling
    - Table operations
    - Health check
    - Error handling

Author: Trading Bot Team
Version: 1.0
Python: 3.10+
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime
import sys
from pathlib import Path

# Parent dizini path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.postgres_manager import PostgresManager, DatabaseError


# ==================== Fixtures ====================

@pytest.fixture
def mock_psycopg2():
    """Mock psycopg2 modülü."""
    with patch('src.database.postgres_manager.psycopg2') as mock:
        yield mock


@pytest.fixture
def mock_pool():
    """Mock connection pool."""
    pool = Mock()
    pool.getconn = Mock()
    pool.putconn = Mock()
    pool.closeall = Mock()
    return pool


@pytest.fixture
def mock_connection():
    """Mock database connection."""
    conn = Mock()
    conn.cursor = Mock()
    conn.commit = Mock()
    conn.rollback = Mock()
    return conn


@pytest.fixture
def mock_cursor():
    """Mock database cursor."""
    cursor = Mock()
    cursor.execute = Mock()
    cursor.executemany = Mock()
    cursor.fetchone = Mock()
    cursor.fetchall = Mock()
    cursor.close = Mock()
    return cursor


@pytest.fixture
def postgres_manager():
    """PostgresManager instance (bağlantısız)."""
    return PostgresManager(
        host="localhost",
        port=5432,
        database="test_db",
        user="test_user",
        password="test_pass"
    )


# ==================== Connection Tests ====================

def test_manager_initialization():
    """Manager başlangıç değerlerini test et."""
    manager = PostgresManager(
        host="testhost",
        port=5433,
        database="testdb"
    )
    
    assert manager.config['host'] == "testhost"
    assert manager.config['port'] == 5433
    assert manager.config['database'] == "testdb"
    assert manager._connected is False
    assert manager.pool is None


def test_connect_success(postgres_manager, mock_psycopg2, mock_pool):
    """Başarılı bağlantı testi."""
    mock_psycopg2.pool.SimpleConnectionPool.return_value = mock_pool
    
    postgres_manager.connect()
    
    assert postgres_manager._connected is True
    assert postgres_manager.pool == mock_pool
    mock_psycopg2.pool.SimpleConnectionPool.assert_called_once()


def test_connect_failure(postgres_manager, mock_psycopg2):
    """Bağlantı hatası testi."""
    mock_psycopg2.pool.SimpleConnectionPool.side_effect = Exception("Connection failed")
    
    with pytest.raises(DatabaseError) as exc_info:
        postgres_manager.connect()
    
    assert "Connection failed" in str(exc_info.value)
    assert postgres_manager._connected is False


def test_close(postgres_manager, mock_pool):
    """Bağlantı kapatma testi."""
    postgres_manager.pool = mock_pool
    postgres_manager._connected = True
    
    postgres_manager.close()
    
    mock_pool.closeall.assert_called_once()
    assert postgres_manager._connected is False


# ==================== Context Manager Tests ====================

def test_get_connection_success(postgres_manager, mock_pool, mock_connection):
    """Connection context manager testi."""
    postgres_manager.pool = mock_pool
    postgres_manager._connected = True
    mock_pool.getconn.return_value = mock_connection
    
    with postgres_manager.get_connection() as conn:
        assert conn == mock_connection
    
    mock_pool.getconn.assert_called_once()
    mock_pool.putconn.assert_called_once_with(mock_connection)


def test_get_connection_not_connected(postgres_manager):
    """Bağlantısız context manager hatası."""
    with pytest.raises(DatabaseError) as exc_info:
        with postgres_manager.get_connection():
            pass
    
    assert "bağlı değil" in str(exc_info.value).lower()


def test_get_cursor_success(postgres_manager, mock_pool, mock_connection, mock_cursor):
    """Cursor context manager testi."""
    postgres_manager.pool = mock_pool
    postgres_manager._connected = True
    mock_pool.getconn.return_value = mock_connection
    mock_connection.cursor.return_value = mock_cursor
    
    with postgres_manager.get_cursor() as cur:
        assert cur == mock_cursor
        cur.execute("SELECT 1")
    
    mock_cursor.execute.assert_called_once_with("SELECT 1")
    mock_connection.commit.assert_called_once()
    mock_cursor.close.assert_called_once()


def test_get_cursor_error_rollback(postgres_manager, mock_pool, mock_connection, mock_cursor):
    """Cursor hatası rollback testi."""
    postgres_manager.pool = mock_pool
    postgres_manager._connected = True
    mock_pool.getconn.return_value = mock_connection
    mock_connection.cursor.return_value = mock_cursor
    mock_cursor.execute.side_effect = Exception("Query error")
    
    with pytest.raises(Exception):
        with postgres_manager.get_cursor() as cur:
            cur.execute("BAD SQL")
    
    mock_connection.rollback.assert_called_once()
    mock_cursor.close.assert_called_once()


# ==================== Query Execution Tests ====================

@patch.object(PostgresManager, 'get_cursor')
def test_execute_fetch_all(mock_get_cursor, postgres_manager, mock_cursor):
    """Execute ile tüm sonuçları getirme testi."""
    mock_cursor.fetchall.return_value = [(1, 'test'), (2, 'data')]
    mock_get_cursor.return_value.__enter__.return_value = mock_cursor
    
    results = postgres_manager.execute("SELECT * FROM test")
    
    assert len(results) == 2
    assert results[0] == (1, 'test')
    mock_cursor.execute.assert_called_once_with("SELECT * FROM test", None)


@patch.object(PostgresManager, 'get_cursor')
def test_execute_fetch_one(mock_get_cursor, postgres_manager, mock_cursor):
    """Execute ile tek sonuç getirme testi."""
    mock_cursor.fetchone.return_value = (1, 'test')
    mock_get_cursor.return_value.__enter__.return_value = mock_cursor
    
    result = postgres_manager.execute("SELECT 1", fetch_one=True)
    
    assert result == (1, 'test')
    mock_cursor.fetchone.assert_called_once()


@patch.object(PostgresManager, 'get_cursor')
def test_execute_with_params(mock_get_cursor, postgres_manager, mock_cursor):
    """Parametreli query testi."""
    mock_cursor.fetchall.return_value = [(1,)]
    mock_get_cursor.return_value.__enter__.return_value = mock_cursor
    
    postgres_manager.execute("SELECT * FROM test WHERE id = %s", (123,))
    
    mock_cursor.execute.assert_called_once_with(
        "SELECT * FROM test WHERE id = %s",
        (123,)
    )


@patch.object(PostgresManager, 'get_cursor')
def test_execute_no_fetch(mock_get_cursor, postgres_manager, mock_cursor):
    """Fetch olmadan execute (INSERT/UPDATE) testi."""
    mock_get_cursor.return_value.__enter__.return_value = mock_cursor
    
    result = postgres_manager.execute("INSERT INTO test VALUES (1)", fetch=False)
    
    assert result is None
    mock_cursor.execute.assert_called_once()


@patch.object(PostgresManager, 'get_cursor')
def test_execute_many(mock_get_cursor, postgres_manager, mock_cursor):
    """Batch execute testi."""
    mock_get_cursor.return_value.__enter__.return_value = mock_cursor
    params = [(1, 'a'), (2, 'b'), (3, 'c')]
    
    postgres_manager.execute_many("INSERT INTO test VALUES (%s, %s)", params)
    
    mock_cursor.executemany.assert_called_once_with(
        "INSERT INTO test VALUES (%s, %s)",
        params
    )


# ==================== Transaction Tests ====================

@patch.object(PostgresManager, 'get_connection')
def test_execute_transaction_success(mock_get_connection, postgres_manager, mock_connection, mock_cursor):
    """Transaction başarı testi."""
    mock_get_connection.return_value.__enter__.return_value = mock_connection
    mock_connection.cursor.return_value = mock_cursor
    
    queries = [
        ("INSERT INTO test VALUES (%s)", (1,)),
        ("UPDATE test SET val = %s WHERE id = %s", ('a', 1))
    ]
    
    postgres_manager.execute_transaction(queries)
    
    assert mock_cursor.execute.call_count == 2
    mock_connection.commit.assert_called_once()


@patch.object(PostgresManager, 'get_connection')
def test_execute_transaction_failure(mock_get_connection, postgres_manager, mock_connection, mock_cursor):
    """Transaction hata testi (rollback)."""
    mock_get_connection.return_value.__enter__.return_value = mock_connection
    mock_connection.cursor.return_value = mock_cursor
    mock_cursor.execute.side_effect = Exception("Query failed")
    
    queries = [("INSERT INTO test VALUES (1)", None)]
    
    with pytest.raises(DatabaseError):
        postgres_manager.execute_transaction(queries)
    
    mock_connection.rollback.assert_called_once()


# ==================== Table Operations Tests ====================

@patch.object(PostgresManager, 'execute')
def test_table_exists_true(mock_execute, postgres_manager):
    """Tablo varlık kontrolü (var) testi."""
    mock_execute.return_value = (True,)
    
    exists = postgres_manager.table_exists('test_table')
    
    assert exists is True
    mock_execute.assert_called_once()


@patch.object(PostgresManager, 'execute')
def test_table_exists_false(mock_execute, postgres_manager):
    """Tablo varlık kontrolü (yok) testi."""
    mock_execute.return_value = (False,)
    
    exists = postgres_manager.table_exists('nonexistent')
    
    assert exists is False


@patch.object(PostgresManager, 'get_cursor')
def test_create_tables_success(mock_get_cursor, postgres_manager, mock_cursor):
    """Tablo oluşturma testi."""
    mock_get_cursor.return_value.__enter__.return_value = mock_cursor
    
    postgres_manager.create_tables()
    
    # Schema SQL çalıştırıldı mı?
    assert mock_cursor.execute.called
    # İlk argüman uzun SQL string olmalı
    call_args = mock_cursor.execute.call_args[0][0]
    assert 'CREATE TABLE' in call_args


# ==================== Health Check Tests ====================

@patch.object(PostgresManager, 'execute')
def test_health_check_success(mock_execute, postgres_manager, mock_pool):
    """Sağlık kontrolü başarı testi."""
    postgres_manager.pool = mock_pool
    postgres_manager._connected = True
    mock_pool._pool = []
    mock_pool._used = []
    mock_execute.return_value = (1,)
    
    health = postgres_manager.health_check()
    
    assert health['healthy'] is True
    assert health['connected'] is True
    assert 'latency_ms' in health
    assert health['pool']['max'] == postgres_manager.max_conn


@patch.object(PostgresManager, 'execute')
def test_health_check_failure(mock_execute, postgres_manager):
    """Sağlık kontrolü hata testi."""
    postgres_manager._connected = True
    mock_execute.side_effect = Exception("Connection lost")
    
    health = postgres_manager.health_check()
    
    assert health['healthy'] is False
    assert 'error' in health


# ==================== Statistics Tests ====================

@patch.object(PostgresManager, 'table_exists')
@patch.object(PostgresManager, 'execute')
def test_get_stats(mock_execute, mock_table_exists, postgres_manager):
    """Veritabanı istatistikleri testi."""
    mock_table_exists.return_value = True
    mock_execute.return_value = (100,)
    
    stats = postgres_manager.get_stats()
    
    assert 'trades' in stats
    assert stats['trades'] == 100
    # Her tablo için çağrıldı mı?
    assert mock_execute.call_count >= 5  # 5 tablo


@patch.object(PostgresManager, 'table_exists')
def test_get_stats_table_not_exists(mock_table_exists, postgres_manager):
    """Tablo yoksa stats testi."""
    mock_table_exists.return_value = False
    
    stats = postgres_manager.get_stats()
    
    # Tablo yok = -1
    assert stats['trades'] == -1


# ==================== String Representation Tests ====================

def test_repr_disconnected():
    """Repr testi (bağlantısız)."""
    manager = PostgresManager(host="localhost", database="test")
    
    repr_str = repr(manager)
    
    assert "localhost" in repr_str
    assert "test" in repr_str
    assert "disconnected" in repr_str


def test_repr_connected(postgres_manager):
    """Repr testi (bağlantılı)."""
    postgres_manager._connected = True
    
    repr_str = repr(postgres_manager)
    
    assert "connected" in repr_str


# ==================== Parametreli Testler ====================

@pytest.mark.parametrize("host,port,db", [
    ("localhost", 5432, "db1"),
    ("192.168.1.1", 5433, "db2"),
    ("db.example.com", 5434, "production")
])
def test_different_configs(host, port, db):
    """Farklı konfigürasyonlar testi."""
    manager = PostgresManager(host=host, port=port, database=db)
    
    assert manager.config['host'] == host
    assert manager.config['port'] == port
    assert manager.config['database'] == db


# ==================== Test Runner ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])