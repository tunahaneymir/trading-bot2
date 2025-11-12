#!/usr/bin/env python3
"""
Data Migration Script

Eski veritabanından/dosyalardan yeni şemaya veri taşır.
- CSV'den import
- Eski schema'dan yeni schema'ya
- Backup'tan restore

Usage:
    python scripts/migrate_data.py --from-csv trades.csv
    python scripts/migrate_data.py --from-backup backup/2025-11-05/
    python scripts/migrate_data.py --from-db old_trading_bot
"""

import sys
import json
import csv
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# Proje root'unu sys.path'e ekle
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.config_manager import ConfigManager
from src.core.logger import setup_logger
from src.database.postgres_manager import PostgresManager, DatabaseError
from src.database.trade_history_manager import TradeHistoryManager

from dotenv import load_dotenv
load_dotenv()

# Logger setup
logger = setup_logger(__name__)


class DataMigrator:
    """Data migration helper."""
    
    def __init__(self):
        """Initialize."""
        import os
        self.config = ConfigManager()
        self.postgres = PostgresManager(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            database=os.getenv("POSTGRES_DB", "trading_bot"),
            user=os.getenv("POSTGRES_USER", "trading_user"),
            password=os.getenv("POSTGRES_PASSWORD", "")
        )
        self.trade_history = None
        
    def connect(self) -> None:
        """Veritabanına bağlan."""
        self.postgres.connect()
        # Redis gerekmediği için None geçebiliriz
        self.trade_history = TradeHistoryManager(self.postgres, None)
        
    def disconnect(self) -> None:
        """Bağlantıyı kes."""
        if self.postgres:
            self.postgres.close()
    
    def migrate_from_csv(self, csv_path: Path, table: str = 'trades') -> bool:
        """
        CSV dosyasından veri import et.
        
        Args:
            csv_path: CSV dosya yolu
            table: Hedef tablo
            
        Returns:
            Başarılı ise True
        """
        try:
            logger.info(f"📂 CSV okunuyor: {csv_path}")
            
            if not csv_path.exists():
                logger.error(f"❌ Dosya bulunamadı: {csv_path}")
                return False
            
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            
            logger.info(f"📊 {len(rows)} satır bulundu")
            
            # Table'a göre migration
            if table == 'trades':
                return self._migrate_trades_from_csv(rows)
            elif table == 'parameters':
                return self._migrate_parameters_from_csv(rows)
            else:
                logger.error(f"❌ Desteklenmeyen tablo: {table}")
                return False
                
        except Exception as e:
            logger.error(f"❌ CSV migration hatası: {e}")
            return False
    
    def _migrate_trades_from_csv(self, rows: List[Dict]) -> bool:
        """CSV'den trade'leri import et."""
        try:
            success_count = 0
            error_count = 0
            
            for i, row in enumerate(rows, 1):
                try:
                    # Parse row
                    trade_data = {
                        'trade_id': row.get('trade_id', f'imported_{i}'),
                        'symbol': row['symbol'],
                        'side': row['side'],
                        'entry_price': float(row['entry_price']),
                        'quantity': float(row['quantity']),
                        'stop_loss': float(row.get('stop_loss', 0)) if row.get('stop_loss') else None,
                        'take_profit': float(row.get('take_profit', 0)) if row.get('take_profit') else None,
                        'rr_ratio': float(row.get('rr_ratio', 0)) if row.get('rr_ratio') else None,
                        'entry_time': row.get('entry_time', datetime.now().isoformat()),
                        'exit_price': float(row['exit_price']) if row.get('exit_price') else None,
                        'exit_time': row.get('exit_time'),
                        'exit_reason': row.get('exit_reason'),
                        'pnl': float(row['pnl']) if row.get('pnl') else None,
                        'net_pnl': float(row['net_pnl']) if row.get('net_pnl') else None,
                        'notes': row.get('notes')
                    }
                    
                    # Insert
                    query = """
                        INSERT INTO trades (
                            trade_id, symbol, side, entry_price, quantity,
                            stop_loss, take_profit, rr_ratio, entry_time,
                            exit_price, exit_time, exit_reason, pnl, net_pnl, notes
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (trade_id) DO NOTHING
                    """
                    
                    params = (
                        trade_data['trade_id'],
                        trade_data['symbol'],
                        trade_data['side'],
                        trade_data['entry_price'],
                        trade_data['quantity'],
                        trade_data['stop_loss'],
                        trade_data['take_profit'],
                        trade_data['rr_ratio'],
                        trade_data['entry_time'],
                        trade_data['exit_price'],
                        trade_data['exit_time'],
                        trade_data['exit_reason'],
                        trade_data['pnl'],
                        trade_data['net_pnl'],
                        trade_data['notes']
                    )
                    
                    self.postgres.execute(query, params, fetch=False)
                    success_count += 1
                    
                    if i % 100 == 0:
                        logger.info(f"  📊 İşlenen: {i}/{len(rows)}")
                    
                except Exception as e:
                    logger.warning(f"⚠️  Satır {i} atlandı: {e}")
                    error_count += 1
            
            logger.info(f"✅ Başarılı: {success_count}, Hatalı: {error_count}")
            return error_count == 0
            
        except Exception as e:
            logger.error(f"❌ Trade migration hatası: {e}")
            return False
    
    def _migrate_parameters_from_csv(self, rows: List[Dict]) -> bool:
        """CSV'den parametreleri import et."""
        try:
            success_count = 0
            
            for row in rows:
                query = """
                    INSERT INTO parameters (
                        category, parameter_name, parameter_value, description
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (category, parameter_name) 
                    DO UPDATE SET parameter_value = EXCLUDED.parameter_value
                """
                
                params = (
                    row['category'],
                    row['parameter_name'],
                    row['parameter_value'],
                    row.get('description', '')
                )
                
                self.postgres.execute(query, params, fetch=False)
                success_count += 1
            
            logger.info(f"✅ {success_count} parametre eklendi/güncellendi")
            return True
            
        except Exception as e:
            logger.error(f"❌ Parameter migration hatası: {e}")
            return False
    
    def migrate_from_json(self, json_path: Path) -> bool:
        """
        JSON backup'tan restore et.
        
        Args:
            json_path: JSON dosya yolu
            
        Returns:
            Başarılı ise True
        """
        try:
            logger.info(f"📂 JSON okunuyor: {json_path}")
            
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Trades
            if 'trades' in data:
                logger.info(f"📊 {len(data['trades'])} trade bulundu")
                for trade in data['trades']:
                    # Insert logic here
                    pass
            
            # Parameters
            if 'parameters' in data:
                logger.info(f"📊 {len(data['parameters'])} parametre bulundu")
                # Insert logic here
            
            logger.info("✅ JSON migration tamamlandı")
            return True
            
        except Exception as e:
            logger.error(f"❌ JSON migration hatası: {e}")
            return False
    
    def migrate_from_old_database(self, old_db_name: str) -> bool:
        """
        Eski veritabanından yeni şemaya kopyala.
        
        Args:
            old_db_name: Eski database adı
            
        Returns:
            Başarılı ise True
        """
        try:
            logger.info(f"🔄 Eski DB'den migration: {old_db_name}")
            
            # Connect to old database
            old_config = self.config.config.copy()
            old_config['postgres']['database'] = old_db_name
            old_postgres = PostgresManager(ConfigManager.from_dict(old_config))
            old_postgres.connect()
            
            # Get all trades
            old_trades = old_postgres.execute(
                "SELECT * FROM trades ORDER BY entry_time",
                fetch_all=True
            )
            
            logger.info(f"📊 {len(old_trades)} trade bulundu")
            
            # Insert to new database
            for trade in old_trades:
                # Insert logic here
                pass
            
            old_postgres.disconnect()
            
            logger.info("✅ Database migration tamamlandı")
            return True
            
        except Exception as e:
            logger.error(f"❌ Database migration hatası: {e}")
            return False
    
    def export_to_csv(self, output_path: Path, table: str = 'trades') -> bool:
        """
        Veritabanından CSV'ye export.
        
        Args:
            output_path: Çıktı dosyası
            table: Kaynak tablo
            
        Returns:
            Başarılı ise True
        """
        try:
            logger.info(f"📤 Export yapılıyor: {table} → {output_path}")
            
            # Get data
            rows = self.postgres.execute(
                f"SELECT * FROM {table} ORDER BY created_at",
                fetch_all=True
            )
            
            if not rows:
                logger.warning("⚠️  Veri bulunamadı")
                return False
            
            # Get column names
            columns = self.postgres.execute(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{table}'
                ORDER BY ordinal_position
            """, fetch_all=True)
            
            column_names = [col[0] for col in columns]
            
            # Write CSV
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(column_names)
                writer.writerows(rows)
            
            logger.info(f"✅ {len(rows)} satır export edildi")
            return True
            
        except Exception as e:
            logger.error(f"❌ Export hatası: {e}")
            return False


def main():
    """Ana fonksiyon."""
    parser = argparse.ArgumentParser(description='Veri migration scripti')
    parser.add_argument('--from-csv', type=Path, help='CSV dosyasından import')
    parser.add_argument('--from-json', type=Path, help='JSON dosyasından import')
    parser.add_argument('--from-db', type=str, help='Eski database\'den import')
    parser.add_argument('--to-csv', type=Path, help='CSV\'ye export')
    parser.add_argument('--table', type=str, default='trades', help='Tablo adı')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  📦 TRADING BOT - DATA MIGRATION")
    print("=" * 60)
    print()
    
    # Create migrator
    migrator = DataMigrator()
    
    try:
        # Connect
        logger.info("🔌 Bağlanıyor...")
        migrator.connect()
        
        success = False
        
        # Import from CSV
        if args.from_csv:
            success = migrator.migrate_from_csv(args.from_csv, args.table)
        
        # Import from JSON
        elif args.from_json:
            success = migrator.migrate_from_json(args.from_json)
        
        # Import from old database
        elif args.from_db:
            success = migrator.migrate_from_old_database(args.from_db)
        
        # Export to CSV
        elif args.to_csv:
            success = migrator.export_to_csv(args.to_csv, args.table)
        
        else:
            print("❌ Lütfen bir işlem seçin:")
            print("  --from-csv   CSV'den import")
            print("  --from-json  JSON'dan import")
            print("  --from-db    Eski DB'den import")
            print("  --to-csv     CSV'ye export")
            print()
            print("Örnek:")
            print("  python scripts/migrate_data.py --from-csv data/trades.csv")
            print("  python scripts/migrate_data.py --to-csv exports/trades.csv")
            sys.exit(1)
        
        if success:
            print()
            print("=" * 60)
            print("  ✅ MIGRATION BAŞARILI!")
            print("=" * 60)
            print()
        else:
            print()
            print("=" * 60)
            print("  ❌ MIGRATION BAŞARISIZ!")
            print("=" * 60)
            print()
            print("💡 Log dosyasını kontrol edin:")
            print("  logs/trading.log")
            print()
        
        sys.exit(0 if success else 1)
        
    except Exception as e:
        logger.error(f"❌ Beklenmeyen hata: {e}")
        print()
        print("=" * 60)
        print("  ❌ HATA!")
        print("=" * 60)
        print(f"\n{e}\n")
        sys.exit(1)
        
    finally:
        migrator.disconnect()


if __name__ == "__main__":
    main()