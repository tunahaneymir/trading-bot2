"""
Trade History Export Script
============================

Export trade history to CSV or Excel for analysis and reporting.

Features:
- CSV export (simple, fast)
- Excel export (multi-sheet: summary, trades, signals)
- Filters: date range, symbol, phase, market regime, confidence
- Statistics summary
- Performance metrics

Usage:
    # Export all trades to CSV
    python scripts/export_trades.py --format csv --output trades.csv
    
    # Export BTCUSDT trades from 2025
    python scripts/export_trades.py --symbol BTCUSDT --start 2025-01-01 --format excel
    
    # Export Phase 1 trades with confidence > 0.7
    python scripts/export_trades.py --phase 1 --min-confidence 0.7 --format csv
"""

import sys
import os
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any
import csv

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.config_manager import ConfigManager
from src.database.postgres_manager import PostgresManager
from src.core.logger import setup_logger

logger = setup_logger('export_trades', 'INFO')


class TradeExporter:
    """Trade history export manager."""
    
    def __init__(self, config: ConfigManager):
        """Initialize exporter."""
        self.config = config
        self.postgres = PostgresManager(
            host=config.get('postgres.host'),
            port=config.get('postgres.port'),
            database=config.get('postgres.database'),
            user=config.get('postgres.user'),
            password=config.get('postgres.password')
        )
    
    def connect(self):
        """Connect to database."""
        try:
            self.postgres.connect()
            logger.info("✅ Database connected")
            return True
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            return False
    
    def close(self):
        """Close database connection."""
        self.postgres.close()
        logger.info("Database connection closed")
    
    def fetch_trades(
        self,
        start_date: str = None,
        end_date: str = None,
        symbol: str = None,
        phase: int = None,
        market_regime: str = None,
        min_confidence: float = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch trades with filters.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            symbol: Symbol filter
            phase: Phase filter (1, 2, 3)
            market_regime: Market regime filter
            min_confidence: Minimum confidence score
        
        Returns:
            List of trade dictionaries
        """
        # Build query
        query = "SELECT * FROM trades WHERE 1=1"
        params = []
        
        if start_date:
            query += " AND entry_time >= %s"
            params.append(start_date)
        
        if end_date:
            query += " AND entry_time <= %s"
            params.append(end_date)
        
        if symbol:
            query += " AND symbol = %s"
            params.append(symbol)
        
        if phase:
            query += " AND coin_selection_phase = %s"
            params.append(phase)
        
        if market_regime:
            query += " AND market_regime = %s"
            params.append(market_regime)
        
        if min_confidence:
            query += " AND confidence_score >= %s"
            params.append(min_confidence)
        
        query += " ORDER BY entry_time DESC"
        
        # Execute
        try:
            result = self.postgres.execute(query, tuple(params), fetch=True)
            
            if result:
                # Convert to list of dicts
                columns = [
                    'trade_id', 'symbol', 'side', 'entry_price', 'quantity',
                    'stop_loss', 'take_profit', 'rr_ratio', 'entry_time', 'exit_price',
                    'exit_time', 'exit_reason', 'duration_seconds', 'pnl', 'pnl_percentage',
                    'fees', 'net_pnl', 'actual_rr', 'notes', 'created_at', 'updated_at',
                    'leverage', 'risk_amount', 'signal_confidence', 'signal_type', 'timeframe'
                ]

                
                trades = []
                for row in result:
                    trade = dict(zip(columns, row))
                    trades.append(trade)
                
                logger.info(f"✅ Fetched {len(trades)} trades")
                return trades
            else:
                logger.warning("No trades found")
                return []
        
        except Exception as e:
            logger.error(f"❌ Failed to fetch trades: {e}")
            return []
    
    def calculate_statistics(self, trades):
        """Calculate trade statistics."""
        if not trades:
            return {}

        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if (t.get('pnl') or 0) > 0)
        losing_trades = sum(1 for t in trades if (t.get('pnl') or 0) < 0)

        total_pnl = sum((t.get('pnl') or 0) for t in trades)
        winning_pnl = sum((t.get('pnl') or 0) for t in trades if (t.get('pnl') or 0) > 0)
        losing_pnl = sum((t.get('pnl') or 0) for t in trades if (t.get('pnl') or 0) < 0)

        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        avg_win = winning_pnl / winning_trades if winning_trades > 0 else 0
        avg_loss = losing_pnl / losing_trades if losing_trades > 0 else 0
        profit_factor = abs(winning_pnl / losing_pnl) if losing_pnl != 0 else 0

        durations = [t.get('duration_seconds', 0) for t in trades if t.get('duration_seconds')]
        avg_duration = sum(durations) / len(durations) if durations else 0

        stats = {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'winning_pnl': winning_pnl,
            'losing_pnl': losing_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'avg_duration_seconds': avg_duration,
            'avg_duration_minutes': avg_duration / 60 if avg_duration else 0
        }

        return stats


    
    def export_to_csv(self, trades: List[Dict], output_file: str):
        """Export trades to CSV."""
        if not trades:
            logger.warning("No trades to export")
            return False
        
        try:
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)
            
            # Write CSV
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=trades[0].keys())
                writer.writeheader()
                writer.writerows(trades)
            
            logger.info(f"✅ Exported {len(trades)} trades to {output_file}")
            return True
        
        except Exception as e:
            logger.error(f"❌ CSV export failed: {e}")
            return False
    
    def export_to_excel(self, trades: List[Dict], output_file: str):
        """Export trades to Excel (multi-sheet)."""
        try:
            import pandas as pd
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment
            from openpyxl.utils.dataframe import dataframe_to_rows
            
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)
            
            # Create workbook
            wb = Workbook()
            
            # 1. Summary Sheet
            ws_summary = wb.active
            ws_summary.title = "Summary"
            
            stats = self.calculate_statistics(trades)
            
            # Header style
            header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            header_font = Font(bold=True, color="FFFFFF")
            
            # Write summary
            ws_summary['A1'] = "Trade Statistics"
            ws_summary['A1'].font = Font(bold=True, size=14)
            
            row = 3
            for key, value in stats.items():
                ws_summary[f'A{row}'] = key.replace('_', ' ').title()
                ws_summary[f'B{row}'] = value
                if isinstance(value, float):
                    ws_summary[f'B{row}'].number_format = '0.00'
                row += 1
            
            # 2. Trades Sheet
            ws_trades = wb.create_sheet("Trades")
            
            # Convert to DataFrame
            df = pd.DataFrame(trades)
            
            # Write header
            for col_num, column_title in enumerate(df.columns, 1):
                cell = ws_trades.cell(row=1, column=col_num)
                cell.value = column_title
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center')
            
            # Write data
            for row_num, row_data in enumerate(df.values, 2):
                for col_num, cell_value in enumerate(row_data, 1):
                    cell = ws_trades.cell(row=row_num, column=col_num)
                    cell.value = cell_value
            
            # Auto-adjust column widths
            for column in ws_trades.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                ws_trades.column_dimensions[column_letter].width = adjusted_width
            
            # 3. Phase Breakdown Sheet
            ws_phases = wb.create_sheet("Phase Breakdown")
            
            # Group by phase
            phase_stats = {}
            for phase in [1, 2, 3]:
                phase_trades = [t for t in trades if t.get('coin_selection_phase') == phase]
                if phase_trades:
                    phase_stats[f'Phase {phase}'] = self.calculate_statistics(phase_trades)
            
            # Write phase stats
            ws_phases['A1'] = "Phase Performance"
            ws_phases['A1'].font = Font(bold=True, size=14)
            
            row = 3
            for phase_name, stats in phase_stats.items():
                ws_phases[f'A{row}'] = phase_name
                ws_phases[f'A{row}'].font = Font(bold=True)
                row += 1
                
                for key, value in stats.items():
                    ws_phases[f'A{row}'] = "  " + key.replace('_', ' ').title()
                    ws_phases[f'B{row}'] = value
                    if isinstance(value, float):
                        ws_phases[f'B{row}'].number_format = '0.00'
                    row += 1
                
                row += 1  # Empty row between phases
            
            # Save workbook
            wb.save(output_file)
            
            logger.info(f"✅ Exported {len(trades)} trades to {output_file}")
            logger.info(f"   Sheets: Summary, Trades, Phase Breakdown")
            return True
        
        except ImportError:
            logger.error("❌ pandas and openpyxl required for Excel export")
            logger.error("   Install: pip install pandas openpyxl --break-system-packages")
            return False
        except Exception as e:
            logger.error(f"❌ Excel export failed: {e}")
            return False


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Export Trade History')
    
    # Output
    parser.add_argument('--format', choices=['csv', 'excel'], default='csv',
                       help='Export format')
    parser.add_argument('--output', type=str,
                       help='Output file path')
    
    # Filters
    parser.add_argument('--start', type=str,
                       help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str,
                       help='End date (YYYY-MM-DD)')
    parser.add_argument('--symbol', type=str,
                       help='Symbol filter (e.g., BTCUSDT)')
    parser.add_argument('--phase', type=int, choices=[1, 2, 3],
                       help='Phase filter')
    parser.add_argument('--regime', type=str, choices=['BULL', 'BEAR', 'SIDEWAYS', 'VOLATILE'],
                       help='Market regime filter')
    parser.add_argument('--min-confidence', type=float,
                       help='Minimum confidence score (0-1)')
    
    args = parser.parse_args()
    
    # Default output file
    if not args.output:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        ext = 'csv' if args.format == 'csv' else 'xlsx'
        args.output = f"exports/trades_{timestamp}.{ext}"
    
    print("=" * 70)
    print("TRADE HISTORY EXPORT")
    print("=" * 70)
    print(f"Format: {args.format.upper()}")
    print(f"Output: {args.output}")
    
    if args.start:
        print(f"Start Date: {args.start}")
    if args.end:
        print(f"End Date: {args.end}")
    if args.symbol:
        print(f"Symbol: {args.symbol}")
    if args.phase:
        print(f"Phase: {args.phase}")
    if args.regime:
        print(f"Market Regime: {args.regime}")
    if args.min_confidence:
        print(f"Min Confidence: {args.min_confidence}")
    
    print("=" * 70)
    
    # Load config
    config = ConfigManager()
    config.load('config/config.yaml')
    
    # Create exporter
    exporter = TradeExporter(config)
    
    if not exporter.connect():
        print("❌ Failed to connect to database")
        return 1
    
    try:
        # Fetch trades
        print("\n⏳ Fetching trades...")
        trades = exporter.fetch_trades(
            start_date=args.start,
            end_date=args.end,
            symbol=args.symbol,
            phase=args.phase,
            market_regime=args.regime,
            min_confidence=args.min_confidence
        )
        
        if not trades:
            print("❌ No trades found")
            return 1
        
        print(f"✅ Found {len(trades)} trades")
        
        # Calculate and display statistics
        stats = exporter.calculate_statistics(trades)
        print("\n📊 Trade Statistics:")
        print("-" * 70)
        print(f"Total Trades:     {stats['total_trades']}")
        print(f"Win Rate:         {stats['win_rate']:.2f}%")
        print(f"Total PnL:        ${stats['total_pnl']:.2f}")
        print(f"Profit Factor:    {stats['profit_factor']:.2f}")
        print(f"Avg Win:          ${stats['avg_win']:.2f}")
        print(f"Avg Loss:         ${stats['avg_loss']:.2f}")
        print(f"Avg Duration:     {stats['avg_duration_minutes']:.1f} minutes")
        print("-" * 70)
        
        # Export
        print(f"\n⏳ Exporting to {args.format.upper()}...")
        
        if args.format == 'csv':
            success = exporter.export_to_csv(trades, args.output)
        else:
            success = exporter.export_to_excel(trades, args.output)
        
        if success:
            print(f"\n✅ Export completed!")
            print(f"📁 File: {args.output}")
            return 0
        else:
            print(f"\n❌ Export failed")
            return 1
    
    finally:
        exporter.close()


if __name__ == '__main__':
    sys.exit(main())