"""
Strateji Backtest Script
========================

Trading stratejisini geçmiş verilerle test eder ve performans raporlar.

Özellikler:
----------
- Multi-timeframe veri yükleme
- SignalGenerator ile sinyal üretimi
- Simüle edilmiş trade yürütme
- Detaylı performans analizi
- JSON ve CSV raporlama
- Görselleştirme hazırlığı

Kullanım:
--------
```bash
python scripts/backtest_strategy.py --symbol BTCUSDT --start 2024-01-01 --end 2024-12-31
```

Yazar: Trading Bot Sistemi
Versiyon: 1.0.0
Faz: 5
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any
import logging

# Proje root'u path'e ekle
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Trading bileşenleri
from trading import (
    SignalGenerator,
    PositionManager,
    Position,
    PositionSide,
    CloseReason,
    SignalType
)


class BacktestEngine:
    """
    Backtest motoru.

    Geçmiş verilerle trading stratejisini test eder.
    """

    def __init__(
        self,
        symbol: str,
        initial_balance: float = 10000.0,
        position_size_usdt: float = 100.0,
        logger: logging.Logger = None
    ):
        """
        Backtest Engine başlatıcı.

        Parametreler:
        ------------
        symbol : str
            Test edilecek coin sembolü
        initial_balance : float
            Başlangıç bakiyesi (USDT)
        position_size_usdt : float
            Pozisyon büyüklüğü (USDT)
        logger : logging.Logger
            Logger instance
        """
        self.symbol = symbol
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.position_size_usdt = position_size_usdt
        self.logger = logger or logging.getLogger(__name__)

        # Bileşenler
        self.signal_generator = SignalGenerator(logger=self.logger)
        self.position_manager = PositionManager(logger=self.logger)

        # Trade geçmişi
        self.trades: List[Position] = []
        self.signals_history: List[Dict] = []

        # Performans metrikleri
        self.equity_curve: List[Dict] = []
        self.drawdowns: List[float] = []
        self.peak_balance = initial_balance

    async def run_backtest(
        self,
        data_1h: Dict,
        data_15m: Dict,
        timestamps: List[str]
    ) -> Dict[str, Any]:
        """
        Backtest çalıştır.

        Parametreler:
        ------------
        data_1h : Dict
            1 saatlik veri {'high', 'low', 'close'}
        data_15m : Dict
            15 dakikalık veri {'high', 'low', 'close', 'volume'}
        timestamps : List[str]
            Zaman damgaları

        Returns:
        --------
        Dict[str, Any]
            Backtest sonuçları
        """
        self.logger.info("Backtest başlatılıyor...")
        self.logger.info(f"Sembol: {self.symbol}")
        self.logger.info(f"Başlangıç bakiyesi: ${self.initial_balance:.2f}")

        total_steps = len(timestamps)

        for i, timestamp in enumerate(timestamps):
            if i % 100 == 0:
                progress = (i / total_steps) * 100
                self.logger.info(f"İlerleme: {progress:.1f}% ({i}/{total_steps})")

            # Mevcut veri window
            window_1h = self._get_data_window(data_1h, i, window_size=100)
            window_15m = self._get_data_window(data_15m, i, window_size=100)

            if not window_1h or not window_15m:
                continue

            current_price = window_15m['close'][-1]

            # Aktif pozisyonları güncelle
            await self._update_positions(current_price)

            # Çıkış kontrolü
            await self._check_exits(current_price, timestamp)

            # Yeni sinyal kontrolü
            if len(self.position_manager.get_active_positions()) == 0:
                await self._check_entry(window_1h, window_15m, current_price, timestamp)

            # Equity curve kaydet
            self._record_equity(timestamp, current_price)

        # Final raporlama
        results = self._generate_report()

        self.logger.info("=" * 60)
        self.logger.info("Backtest tamamlandı!")
        self.logger.info(f"Final bakiye: ${self.current_balance:.2f}")
        self.logger.info(f"Toplam trade: {results['total_trades']}")
        self.logger.info(f"Kazanma oranı: {results['win_rate']:.2f}%")
        self.logger.info(f"Net kar: ${results['net_profit']:.2f}")
        self.logger.info("=" * 60)

        return results

    def _get_data_window(
        self,
        data: Dict,
        current_idx: int,
        window_size: int
    ) -> Dict:
        """Veri window'u al."""
        if current_idx < window_size:
            return None

        window = {}
        for key, values in data.items():
            window[key] = values[current_idx - window_size:current_idx]

        return window

    async def _update_positions(self, current_price: float) -> None:
        """Aktif pozisyonları güncelle."""
        for position in self.position_manager.get_active_positions():
            await self.position_manager.update_position(
                position.position_id,
                current_price
            )

    async def _check_exits(self, current_price: float, timestamp: str) -> None:
        """Çıkış koşullarını kontrol et."""
        for position in self.position_manager.get_active_positions():
            exit_reason = await self.position_manager.check_exit_conditions(
                position.position_id,
                current_price
            )

            if exit_reason:
                await self._close_position(position, current_price, exit_reason)

    async def _check_entry(
        self,
        data_1h: Dict,
        data_15m: Dict,
        current_price: float,
        timestamp: str
    ) -> None:
        """Entry sinyali kontrol et."""
        # Sinyal üret
        signal = self.signal_generator.generate_signal(
            data_1h=data_1h,
            data_15m=data_15m,
            timestamp=timestamp
        )

        # Sinyal kaydet
        self.signals_history.append({
            'timestamp': timestamp,
            'signal_type': signal.signal_type.value,
            'confidence': signal.confidence_score,
            'price': current_price
        })

        # STRONG sinyaller için trade aç
        if signal.signal_type in [SignalType.STRONG_BUY, SignalType.STRONG_SELL]:
            await self._open_position(signal, current_price, timestamp)

    async def _open_position(
        self,
        signal,
        current_price: float,
        timestamp: str
    ) -> None:
        """Pozisyon aç."""
        # Side belirleme
        if signal.signal_type == SignalType.STRONG_BUY:
            side = PositionSide.LONG
        else:
            side = PositionSide.SHORT

        # Quantity hesapla
        quantity = self.position_size_usdt / current_price

        # Pozisyon oluştur
        position = await self.position_manager.open_position(
            symbol=self.symbol,
            side=side,
            entry_price=current_price,
            quantity=quantity,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            signal_type=signal.signal_type.value,
            signal_confidence=signal.confidence_score,
            notes=f"Backtest - {timestamp}"
        )

        self.logger.debug(
            f"Pozisyon açıldı: {side.value} @ ${current_price:.2f}"
        )

    async def _close_position(
        self,
        position: Position,
        current_price: float,
        reason: CloseReason
    ) -> None:
        """Pozisyon kapat."""
        closed = await self.position_manager.close_position(
            position_id=position.position_id,
            exit_price=current_price,
            exit_reason=reason
        )

        # Bakiye güncelle
        self.current_balance += closed.realized_pnl

        # Trade kaydet
        self.trades.append(closed)

        self.logger.debug(
            f"Pozisyon kapandı: {reason.value} | "
            f"PnL: ${closed.realized_pnl:.2f}"
        )

    def _record_equity(self, timestamp: str, current_price: float) -> None:
        """Equity curve kaydet."""
        # Unrealized PnL hesapla
        unrealized_pnl = self.position_manager.calculate_total_unrealized_pnl()

        # Toplam equity
        total_equity = self.current_balance + unrealized_pnl

        # Drawdown hesapla
        if total_equity > self.peak_balance:
            self.peak_balance = total_equity

        drawdown = 0.0
        if self.peak_balance > 0:
            drawdown = ((self.peak_balance - total_equity) / self.peak_balance) * 100

        self.drawdowns.append(drawdown)

        # Equity curve kaydet
        self.equity_curve.append({
            'timestamp': timestamp,
            'balance': self.current_balance,
            'unrealized_pnl': unrealized_pnl,
            'total_equity': total_equity,
            'drawdown': drawdown
        })

    def _generate_report(self) -> Dict[str, Any]:
        """Performans raporu oluştur."""
        total_trades = len(self.trades)
        winning_trades = sum(1 for t in self.trades if t.realized_pnl > 0)
        losing_trades = total_trades - winning_trades

        total_profit = sum(t.realized_pnl for t in self.trades if t.realized_pnl > 0)
        total_loss = abs(sum(t.realized_pnl for t in self.trades if t.realized_pnl < 0))

        net_profit = total_profit - total_loss
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        profit_factor = (total_profit / total_loss) if total_loss > 0 else 0

        avg_win = (total_profit / winning_trades) if winning_trades > 0 else 0
        avg_loss = (total_loss / losing_trades) if losing_trades > 0 else 0

        max_drawdown = max(self.drawdowns) if self.drawdowns else 0

        return {
            'symbol': self.symbol,
            'initial_balance': self.initial_balance,
            'final_balance': self.current_balance,
            'net_profit': net_profit,
            'net_profit_percent': (net_profit / self.initial_balance * 100),
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'max_drawdown': max_drawdown,
            'total_signals': len(self.signals_history),
            'trades': [t.to_dict() for t in self.trades],
            'signals': self.signals_history,
            'equity_curve': self.equity_curve
        }

    def save_report(self, output_path: str) -> None:
        """Raporu kaydet."""
        report = self._generate_report()

        # JSON kaydet
        json_path = f"{output_path}_report.json"
        with open(json_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        self.logger.info(f"Rapor kaydedildi: {json_path}")


async def main():
    """Ana fonksiyon."""
    parser = argparse.ArgumentParser(description='Backtest trading stratejisi')
    parser.add_argument('--symbol', type=str, default='BTCUSDT', help='Coin sembolü')
    parser.add_argument('--initial-balance', type=float, default=10000.0, help='Başlangıç bakiyesi')
    parser.add_argument('--position-size', type=float, default=100.0, help='Pozisyon büyüklüğü')
    parser.add_argument('--output', type=str, default='backtest_results', help='Çıktı dosyası')
    parser.add_argument('--verbose', action='store_true', help='Detaylı log')

    args = parser.parse_args()

    # Logger
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Backtest engine
    engine = BacktestEngine(
        symbol=args.symbol,
        initial_balance=args.initial_balance,
        position_size_usdt=args.position_size,
        logger=logger
    )

    # Mock veri (TODO: Faz 6'da gerçek veri yükleme)
    import numpy as np

    logger.info("Mock veri oluşturuluyor...")
    n_points = 1000

    # 1h veri
    base_1h = np.cumsum(np.random.randn(n_points) * 100) + 50000
    data_1h = {
        'high': base_1h + np.random.rand(n_points) * 100,
        'low': base_1h - np.random.rand(n_points) * 100,
        'close': base_1h
    }

    # 15m veri
    base_15m = np.cumsum(np.random.randn(n_points) * 50) + 50000
    data_15m = {
        'high': base_15m + np.random.rand(n_points) * 50,
        'low': base_15m - np.random.rand(n_points) * 50,
        'close': base_15m,
        'volume': np.random.rand(n_points) * 1000000
    }

    # Timestamps
    timestamps = [
        datetime.now(timezone.utc).isoformat()
        for _ in range(n_points)
    ]

    # Backtest çalıştır
    results = await engine.run_backtest(data_1h, data_15m, timestamps)

    # Rapor kaydet
    engine.save_report(args.output)

    # Özet yazdır
    print("\n" + "=" * 60)
    print("BACKTEST SONUÇLARI")
    print("=" * 60)
    print(f"Sembol: {results['symbol']}")
    print(f"Toplam Trade: {results['total_trades']}")
    print(f"Kazanan: {results['winning_trades']} ({results['win_rate']:.2f}%)")
    print(f"Kaybeden: {results['losing_trades']}")
    print(f"Net Kar: ${results['net_profit']:.2f} ({results['net_profit_percent']:.2f}%)")
    print(f"Profit Factor: {results['profit_factor']:.2f}")
    print(f"Max Drawdown: {results['max_drawdown']:.2f}%")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
