#!/usr/bin/env python3
"""
Database Setup Script

Veritabanı şemasını oluşturur ve yapılandırır.
- PostgreSQL tabloları
- İndeksler
- Trigger'lar
- İlk verileri

Usage:
    python scripts/setup_databases.py
    python scripts/setup_databases.py --drop  # Mevcut tabloları sil
    python scripts/setup_databases.py --reset # Sil ve yeniden oluştur
"""

import sys
import argparse
from pathlib import Path

# Proje root'unu sys.path'e ekle
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.config_manager import ConfigManager
from src.core.logger import setup_logger
from src.database.postgres_manager import PostgresManager, DatabaseError

from dotenv import load_dotenv
load_dotenv()

import os
print("\n[DEBUG ENV CHECK]")
print("POSTGRES_USER:", os.getenv("POSTGRES_USER"))
print("POSTGRES_PASSWORD:", os.getenv("POSTGRES_PASSWORD"))
print("POSTGRES_DB:", os.getenv("POSTGRES_DB"))
print("POSTGRES_HOST:", os.getenv("POSTGRES_HOST"))
print("POSTGRES_PORT:", os.getenv("POSTGRES_PORT"))
print("DATABASE_URL:", os.getenv("DATABASE_URL"))
print("[/DEBUG ENV CHECK]\n")


# Logger setup
logger = setup_logger(__name__)


# SQL Scripts
CREATE_TABLES_SQL = """
-- ==========================================
-- TRADES TABLOSU
-- ==========================================
CREATE TABLE IF NOT EXISTS trades (
    trade_id VARCHAR(36) PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    entry_price DECIMAL(20,8) NOT NULL,
    quantity DECIMAL(20,8) NOT NULL,
    stop_loss DECIMAL(20,8),
    take_profit DECIMAL(20,8),
    rr_ratio DECIMAL(5,2),
    entry_time TIMESTAMP NOT NULL,
    exit_price DECIMAL(20,8),
    exit_time TIMESTAMP,
    exit_reason VARCHAR(50),
    duration_seconds INTEGER,
    pnl DECIMAL(20,8),
    pnl_percentage DECIMAL(10,2),
    fees DECIMAL(20,8) DEFAULT 0,
    net_pnl DECIMAL(20,8),
    actual_rr DECIMAL(10,2),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- POSITIONS TABLOSU
-- ==========================================
CREATE TABLE IF NOT EXISTS positions (
    position_id VARCHAR(36) PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    entry_price DECIMAL(20,8) NOT NULL,
    current_price DECIMAL(20,8),
    quantity DECIMAL(20,8) NOT NULL,
    stop_loss DECIMAL(20,8),
    take_profit DECIMAL(20,8),
    unrealized_pnl DECIMAL(20,8),
    unrealized_pnl_percentage DECIMAL(10,2),
    entry_time TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- PARAMETERS TABLOSU
-- ==========================================
CREATE TABLE IF NOT EXISTS parameters (
    id SERIAL PRIMARY KEY,
    category VARCHAR(50) NOT NULL,
    parameter_name VARCHAR(100) NOT NULL,
    parameter_value TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(50) DEFAULT 'system',
    UNIQUE(category, parameter_name)
);

-- ==========================================
-- RR_HISTORY TABLOSU
-- ==========================================
CREATE TABLE IF NOT EXISTS rr_history (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    trade_id VARCHAR(36),
    symbol VARCHAR(20) NOT NULL,
    planned_rr DECIMAL(5,2) NOT NULL,
    actual_rr DECIMAL(10,2),
    success BOOLEAN,
    win_rate DECIMAL(5,2),
    avg_rr DECIMAL(10,2),
    profit_factor DECIMAL(10,2),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trade_id) REFERENCES trades(trade_id) ON DELETE SET NULL
);

-- ==========================================
-- COIN_SCORES TABLOSU
-- ==========================================
CREATE TABLE IF NOT EXISTS coin_scores (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    score DECIMAL(5,2) NOT NULL,
    volume_score DECIMAL(5,2),
    volatility_score DECIMAL(5,2),
    trend_score DECIMAL(5,2),
    liquidity_score DECIMAL(5,2),
    rank INTEGER,
    volume_24h BIGINT,
    atr_percentage DECIMAL(5,2),
    spread_percentage DECIMAL(5,3),
    selected BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_INDEXES_SQL = """
-- ==========================================
-- İNDEKSLER
-- ==========================================

-- Trades indexes
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades (symbol);
CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades (entry_time);
CREATE INDEX IF NOT EXISTS idx_trades_exit_time ON trades (exit_time);
CREATE INDEX IF NOT EXISTS idx_trades_side ON trades (side);
CREATE INDEX IF NOT EXISTS idx_trades_created_at ON trades (created_at);

-- Positions indexes
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions (symbol);
CREATE INDEX IF NOT EXISTS idx_positions_entry_time ON positions (entry_time);
CREATE INDEX IF NOT EXISTS idx_positions_side ON positions (side);

-- Parameters indexes
CREATE INDEX IF NOT EXISTS idx_parameters_category ON parameters (category);
CREATE INDEX IF NOT EXISTS idx_parameters_name ON parameters (parameter_name);

-- RR History indexes
CREATE INDEX IF NOT EXISTS idx_rr_history_timestamp ON rr_history (timestamp);
CREATE INDEX IF NOT EXISTS idx_rr_history_trade_id ON rr_history (trade_id);
CREATE INDEX IF NOT EXISTS idx_rr_history_symbol ON rr_history (symbol);

-- Coin Scores indexes
CREATE INDEX IF NOT EXISTS idx_coin_scores_timestamp ON coin_scores (timestamp);
CREATE INDEX IF NOT EXISTS idx_coin_scores_symbol ON coin_scores (symbol);
CREATE INDEX IF NOT EXISTS idx_coin_scores_selected ON coin_scores (selected);
CREATE INDEX IF NOT EXISTS idx_coin_scores_rank ON coin_scores (rank);
"""

CREATE_TRIGGERS_SQL = """
-- ==========================================
-- TRIGGER FUNCTION
-- ==========================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- ==========================================
-- TRIGGERS
-- ==========================================

-- Trades trigger
DROP TRIGGER IF EXISTS update_trades_updated_at ON trades;
CREATE TRIGGER update_trades_updated_at
    BEFORE UPDATE ON trades
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Positions trigger
DROP TRIGGER IF EXISTS update_positions_updated_at ON positions;
CREATE TRIGGER update_positions_updated_at
    BEFORE UPDATE ON positions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Parameters trigger
DROP TRIGGER IF EXISTS update_parameters_updated_at ON parameters;
CREATE TRIGGER update_parameters_updated_at
    BEFORE UPDATE ON parameters
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
"""

INSERT_DEFAULT_DATA_SQL = """
-- ==========================================
-- DEFAULT PARAMETERS
-- ==========================================
INSERT INTO parameters (category, parameter_name, parameter_value, description)
VALUES
    ('trading', 'max_positions', '5', 'Maximum simultaneous positions'),
    ('trading', 'default_leverage', '10', 'Default leverage'),
    ('trading', 'position_size_pct', '10', 'Position size as % of balance'),
    ('risk', 'max_drawdown_pct', '20', 'Maximum allowed drawdown %'),
    ('risk', 'daily_loss_limit_pct', '5', 'Daily loss limit %'),
    ('risk', 'min_rr_ratio', '1.5', 'Minimum risk/reward ratio'),
    ('coin_selection', 'min_volume_24h', '50000000', 'Minimum 24h volume USD'),
    ('coin_selection', 'max_spread_pct', '0.1', 'Maximum spread %'),
    ('coin_selection', 'update_interval_sec', '300', 'Update interval seconds')
ON CONFLICT (category, parameter_name) DO NOTHING;
"""

DROP_TABLES_SQL = """
-- ==========================================
-- DROP TABLES (CASCADE)
-- ==========================================
DROP TABLE IF EXISTS coin_scores CASCADE;
DROP TABLE IF EXISTS rr_history CASCADE;
DROP TABLE IF EXISTS parameters CASCADE;
DROP TABLE IF EXISTS positions CASCADE;
DROP TABLE IF EXISTS trades CASCADE;

-- Drop trigger function
DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;
"""


def setup_database(drop_existing: bool = False, insert_defaults: bool = True) -> bool:
    """
    Veritabanını kur.
    
    Args:
        drop_existing: Mevcut tabloları sil
        insert_defaults: Default verileri ekle
        
    Returns:
        Başarılı ise True
    """
    try:
        # Config ve manager
        logger.info("⚙️  Konfigürasyon yükleniyor...")
        config = ConfigManager()
        
        logger.info("🔌 PostgreSQL'e bağlanıyor...")
        import os
        from src.database.postgres_manager import PostgresManager

        postgres = PostgresManager(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        database=os.getenv("POSTGRES_DB", "trading_bot"),
        user=os.getenv("POSTGRES_USER", "trading_user"),
        password=os.getenv("POSTGRES_PASSWORD", "")
        )
        postgres.connect()

        
        # Drop tables if requested
        if drop_existing:
            logger.warning("⚠️  Mevcut tablolar siliniyor...")
            postgres.execute(DROP_TABLES_SQL, fetch=False)
            logger.info("✅ Tablolar silindi")
        
        # Create tables
        logger.info("📦 Tablolar oluşturuluyor...")
        postgres.execute(CREATE_TABLES_SQL, fetch=False)
        logger.info("✅ Tablolar oluşturuldu")
        
        # Create indexes
        logger.info("🔍 İndeksler oluşturuluyor...")
        postgres.execute(CREATE_INDEXES_SQL, fetch=False)
        logger.info("✅ İndeksler oluşturuldu")
        
        # Create triggers
        logger.info("⚡ Trigger'lar oluşturuluyor...")
        postgres.execute(CREATE_TRIGGERS_SQL, fetch=False)
        logger.info("✅ Trigger'lar oluşturuldu")
        
        # Insert default data
        if insert_defaults:
            logger.info("📊 Default veriler ekleniyor...")
            postgres.execute(INSERT_DEFAULT_DATA_SQL, fetch=False)
            logger.info("✅ Default veriler eklendi")
        
        # Verify
        logger.info("🔍 Doğrulama yapılıyor...")
        tables = postgres.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """, fetch=True)
        
        table_names = [row[0] for row in tables]
        logger.info(f"✅ Oluşturulan tablolar: {', '.join(table_names)}")
        
        # Disconnect
        postgres.close()
        
        logger.info("🎉 Veritabanı kurulumu tamamlandı!")
        return True
        
    except DatabaseError as e:
        logger.error(f"❌ Veritabanı hatası: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Beklenmeyen hata: {e}")
        return False


def verify_database() -> bool:
    """
    Veritabanı yapısını doğrula.
    
    Returns:
        Başarılı ise True
    """
    try:
        logger.info("🔍 Veritabanı doğrulanıyor...")
        
        config = ConfigManager()
        postgres = PostgresManager(config)
        postgres.connect()
        
        # Check tables
        required_tables = ['trades', 'positions', 'parameters', 'rr_history', 'coin_scores']
        
        for table in required_tables:
            result = postgres.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = '{table}'
                )
            """, fetch_one=True)
            
            if result and result[0]:
                logger.info(f"  ✅ {table} tablosu mevcut")
            else:
                logger.error(f"  ❌ {table} tablosu eksik!")
                return False
        
        # Check indexes
        indexes = postgres.execute("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE schemaname = 'public'
        """, fetch_all=True)
        
        index_count = len(indexes)
        logger.info(f"  ✅ {index_count} adet indeks mevcut")
        
        # Check triggers
        triggers = postgres.execute("""
            SELECT trigger_name 
            FROM information_schema.triggers 
            WHERE trigger_schema = 'public'
        """, fetch_all=True)
        
        trigger_count = len(triggers)
        logger.info(f"  ✅ {trigger_count} adet trigger mevcut")
        
        postgres.disconnect()
        
        logger.info("🎉 Veritabanı doğrulama başarılı!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Doğrulama hatası: {e}")
        return False


def main():
    """Ana fonksiyon."""
    parser = argparse.ArgumentParser(description='Veritabanı kurulum scripti')
    parser.add_argument('--drop', action='store_true', help='Mevcut tabloları sil')
    parser.add_argument('--reset', action='store_true', help='Sil ve yeniden oluştur')
    parser.add_argument('--verify', action='store_true', help='Sadece doğrula')
    parser.add_argument('--no-defaults', action='store_true', help='Default verileri ekleme')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  🗄️  TRADING BOT - DATABASE SETUP")
    print("=" * 60)
    print()
    
    # Verify only
    if args.verify:
        success = verify_database()
        sys.exit(0 if success else 1)
    
    # Setup database
    drop_existing = args.drop or args.reset
    insert_defaults = not args.no_defaults
    
    if drop_existing:
        response = input("⚠️  Mevcut tablolar silinecek! Devam edilsin mi? (y/N): ")
        if response.lower() != 'y':
            print("❌ İşlem iptal edildi")
            sys.exit(0)
    
    success = setup_database(
        drop_existing=drop_existing,
        insert_defaults=insert_defaults
    )
    
    if success:
        print()
        print("=" * 60)
        print("  ✅ KURULUM BAŞARILI!")
        print("=" * 60)
        print()
        print("📝 Şimdi yapabilecekleriniz:")
        print("  • python demo_faz2.py          # Demo çalıştır")
        print("  • python scripts/migrate_data.py  # Veri taşı (varsa)")
        print()
    else:
        print()
        print("=" * 60)
        print("  ❌ KURULUM BAŞARISIZ!")
        print("=" * 60)
        print()
        print("💡 Kontrol edilmesi gerekenler:")
        print("  • PostgreSQL çalışıyor mu?")
        print("  • .env dosyası doğru mu?")
        print("  • Veritabanı erişim izinleri var mı?")
        print()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()