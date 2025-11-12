"""
Trading Motoru (Trading Engine)
================================

Ana trading loop ve bileşen orkestratörü.

Sorumluluklar:
-------------
- Ana trading döngüsü yönetimi
- Veri toplama ve işleme
- Sinyal üretimi koordinasyonu
- Pozisyon yönetimi koordinasyonu
- Emir yürütme koordinasyonu
- Risk kontrolü
- Performance tracking
- Event handling

Trading Flow:
------------
1. Market verisi topla (1h + 15m)
2. İndikatör hesapla
3. Sinyal üret (SignalGenerator)
4. Risk kontrolü
5. Pozisyon kararı (aç/kapat/güncelle)
6. Emir gönder (OrderExecutor)
7. Pozisyon takibi (PositionManager)
8. State kaydet

States:
-------
INITIALIZING : Başlatılıyor
RUNNING      : Çalışıyor
PAUSED       : Duraklatıldı
STOPPED      : Durduruldu
ERROR        : Hata durumu

Yazar: Trading Bot Sistemi
Versiyon: 1.0.0
Faz: 5
"""

import asyncio
import signal
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timezone
from dataclasses import dataclass, field
import logging
import json

# Trading bileşenleri
from .signal_generator import SignalGenerator, SignalType
from .position_manager import PositionManager, PositionSide, Position, CloseReason
from .order_executor import OrderExecutor, OrderSide, OrderType


class EngineState(Enum):
    """Motor durumu."""
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


@dataclass
class TradingStats:
    """Trading istatistikleri."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_profit: float = 0.0
    total_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # Risk metrikleri
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    peak_balance: float = 0.0

    # Timing
    start_time: Optional[datetime] = None
    last_trade_time: Optional[datetime] = None

    def update_trade(self, pnl: float, balance: float) -> None:
        """Trade sonrası istatistikleri güncelle."""
        self.total_trades += 1
        self.last_trade_time = datetime.now(timezone.utc)

        if pnl > 0:
            self.winning_trades += 1
            self.total_profit += pnl
            self.consecutive_wins += 1
            self.consecutive_losses = 0
            self.max_consecutive_wins = max(self.max_consecutive_wins, self.consecutive_wins)
            self.largest_win = max(self.largest_win, pnl)
        else:
            self.losing_trades += 1
            self.total_loss += abs(pnl)
            self.consecutive_losses += 1
            self.consecutive_wins = 0
            self.max_consecutive_losses = max(self.max_consecutive_losses, self.consecutive_losses)
            self.largest_loss = max(self.largest_loss, abs(pnl))

        # Drawdown
        self.peak_balance = max(self.peak_balance, balance)
        self.current_drawdown = ((self.peak_balance - balance) / self.peak_balance * 100
                                if self.peak_balance > 0 else 0)
        self.max_drawdown = max(self.max_drawdown, self.current_drawdown)

    def get_win_rate(self) -> float:
        """Kazanma oranı (%)."""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100

    def get_profit_factor(self) -> float:
        """Profit factor."""
        if self.total_loss == 0:
            return 0.0
        return self.total_profit / self.total_loss

    def get_net_profit(self) -> float:
        """Net kar."""
        return self.total_profit - self.total_loss

    def to_dict(self) -> Dict[str, Any]:
        """Dictionary'ye çevir."""
        return {
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': self.get_win_rate(),
            'total_profit': self.total_profit,
            'total_loss': self.total_loss,
            'net_profit': self.get_net_profit(),
            'profit_factor': self.get_profit_factor(),
            'largest_win': self.largest_win,
            'largest_loss': self.largest_loss,
            'max_consecutive_wins': self.max_consecutive_wins,
            'max_consecutive_losses': self.max_consecutive_losses,
            'max_drawdown': self.max_drawdown,
            'current_drawdown': self.current_drawdown
        }


class TradingEngine:
    """
    Ana trading motoru.

    Tüm trading bileşenlerini orkestre eder ve ana döngüyü yönetir.
    """

    def __init__(
        self,
        signal_generator: SignalGenerator,
        position_manager: PositionManager,
        order_executor: OrderExecutor,
        config: Optional[Dict] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Trading Engine başlatıcı.

        Parametreler:
        ------------
        signal_generator : SignalGenerator
            Sinyal üretici
        position_manager : PositionManager
            Pozisyon yönetici
        order_executor : OrderExecutor
            Emir yürütücü
        config : Optional[Dict]
            Konfigürasyon
        logger : Optional[logging.Logger]
            Logger
        """
        self.signal_generator = signal_generator
        self.position_manager = position_manager
        self.order_executor = order_executor
        self.config = config or self._default_config()
        self.logger = logger or logging.getLogger(__name__)

        # Motor durumu
        self.state = EngineState.INITIALIZING
        self.is_running = False
        self.loop_count = 0

        # İstatistikler
        self.stats = TradingStats(start_time=datetime.now(timezone.utc))

        # Trading parametreleri
        self.symbols = self.config.get('symbols', ['BTCUSDT'])
        self.loop_interval = self.config.get('loop_interval_seconds', 60)

        # Hooks (Faz 6+ için genişletilebilir)
        self.hooks: Dict[str, List[Callable]] = {
            'on_start': [],
            'on_stop': [],
            'on_signal': [],
            'on_position_open': [],
            'on_position_close': [],
            'on_error': [],
            'on_loop': []
        }

        # Shutdown handler
        self._setup_shutdown_handlers()

        self.logger.info("TradingEngine başlatıldı")

    def _default_config(self) -> Dict:
        """Varsayılan konfigürasyon."""
        return {
            'symbols': ['BTCUSDT'],
            'loop_interval_seconds': 60,
            'max_positions': 5,
            'position_size_usdt': 100.0,
            'max_risk_per_trade': 0.02,  # %2
            'max_total_risk': 0.06,  # %6
            'min_signal_confidence': 0.75,  # STRONG sinyaller için
            'enable_trailing_stop': True,
            'trailing_stop_percent': 2.0,
            'max_drawdown_percent': 10.0,
            'cooldown_after_loss_seconds': 300,  # 5 dakika
            # TODO: Faz 6'da risk yönetimi eklenecek
            'risk_management': {
                'enabled': False,
                'max_daily_loss': 0.03,  # %3
                'max_weekly_loss': 0.06  # %6
            }
        }

    def _setup_shutdown_handlers(self) -> None:
        """Shutdown signal handlers."""
        def shutdown_handler(signum, frame):
            self.logger.warning(f"Shutdown sinyali alındı: {signum}")
            asyncio.create_task(self.stop())

        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)

    def register_hook(self, event: str, callback: Callable) -> None:
        """
        Event hook kaydet.

        Parametreler:
        ------------
        event : str
            Event adı ('on_start', 'on_signal', vb.)
        callback : Callable
            Callback fonksiyonu
        """
        if event in self.hooks:
            self.hooks[event].append(callback)
            self.logger.debug(f"Hook kaydedildi: {event}")
        else:
            self.logger.warning(f"Bilinmeyen event: {event}")

    async def _trigger_hooks(self, event: str, **kwargs) -> None:
        """Hook'ları tetikle."""
        for callback in self.hooks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(**kwargs)
                else:
                    callback(**kwargs)
            except Exception as e:
                self.logger.error(f"Hook hatası ({event}): {e}")

    async def start(self) -> None:
        """
        Trading motorunu başlat.
        """
        if self.is_running:
            self.logger.warning("Motor zaten çalışıyor")
            return

        self.logger.info("Trading motoru başlatılıyor...")
        self.state = EngineState.RUNNING
        self.is_running = True

        # Start hooks
        await self._trigger_hooks('on_start')

        # Ana döngü
        try:
            while self.is_running:
                await self._trading_loop()
                await asyncio.sleep(self.loop_interval)

        except Exception as e:
            self.logger.error(f"Trading loop hatası: {e}")
            self.state = EngineState.ERROR
            await self._trigger_hooks('on_error', error=e)
            raise

        finally:
            await self.stop()

    async def stop(self) -> None:
        """
        Trading motorunu durdur.
        """
        if not self.is_running:
            return

        self.logger.info("Trading motoru durduruluyor...")
        self.is_running = False
        self.state = EngineState.STOPPED

        # Aktif emirleri iptal et
        await self.order_executor.cancel_all_orders()

        # Stop hooks
        await self._trigger_hooks('on_stop')

        # Final stats
        self.logger.info("=" * 60)
        self.logger.info("Final İstatistikler:")
        stats = self.stats.to_dict()
        for key, value in stats.items():
            if isinstance(value, float):
                self.logger.info(f"  {key}: {value:.2f}")
            else:
                self.logger.info(f"  {key}: {value}")
        self.logger.info("=" * 60)

    async def _trading_loop(self) -> None:
        """
        Ana trading döngüsü.

        Flow:
        -----
        1. Market verisi topla
        2. Aktif pozisyonları güncelle
        3. Çıkış koşulları kontrol et
        4. Yeni sinyal ara
        5. Pozisyon aç (gerekirse)
        """
        self.loop_count += 1
        self.logger.info(f"Trading loop #{self.loop_count}")

        try:
            # 1. Market verisi topla
            market_data = await self._collect_market_data()

            # 2. Aktif pozisyonları güncelle
            await self._update_active_positions(market_data)

            # 3. Çıkış koşulları kontrol et
            await self._check_exit_conditions(market_data)

            # 4. Yeni sinyal ara (eğer pozisyon limiti dolmadıysa)
            if self._can_open_new_position():
                await self._check_entry_signals(market_data)

            # Loop hook
            await self._trigger_hooks('on_loop', loop_count=self.loop_count)

        except Exception as e:
            self.logger.error(f"Trading loop hatası: {e}")
            await self._trigger_hooks('on_error', error=e)

    async def _collect_market_data(self) -> Dict[str, Dict]:
        """
        Market verisi topla.

        Returns:
        --------
        Dict[str, Dict]
            Sembol -> Veri mapping
        """
        # TODO: Faz 6'da BinanceManager'dan gerçek veri
        import numpy as np

        market_data = {}
        for symbol in self.symbols:
            # Mock data (Faz 6'da gerçek veriyle değiştirilecek)
            n_1h = 100
            n_15m = 100

            base_1h = np.cumsum(np.random.randn(n_1h) * 100) + 50000
            base_15m = np.cumsum(np.random.randn(n_15m) * 50) + 50000

            market_data[symbol] = {
                'current_price': base_15m[-1],
                'data_1h': {
                    'high': base_1h + np.random.rand(n_1h) * 100,
                    'low': base_1h - np.random.rand(n_1h) * 100,
                    'close': base_1h
                },
                'data_15m': {
                    'high': base_15m + np.random.rand(n_15m) * 50,
                    'low': base_15m - np.random.rand(n_15m) * 50,
                    'close': base_15m,
                    'volume': np.random.rand(n_15m) * 1000000
                }
            }

        return market_data

    async def _update_active_positions(self, market_data: Dict) -> None:
        """Aktif pozisyonları güncelle."""
        active_positions = self.position_manager.get_active_positions()

        for position in active_positions:
            if position.symbol in market_data:
                current_price = market_data[position.symbol]['current_price']
                await self.position_manager.update_position(
                    position.position_id,
                    current_price
                )

    async def _check_exit_conditions(self, market_data: Dict) -> None:
        """Çıkış koşullarını kontrol et."""
        active_positions = self.position_manager.get_active_positions()

        for position in active_positions:
            if position.symbol not in market_data:
                continue

            current_price = market_data[position.symbol]['current_price']

            # Exit koşulu kontrolü
            exit_reason = await self.position_manager.check_exit_conditions(
                position.position_id,
                current_price
            )

            if exit_reason:
                await self._close_position(position, current_price, exit_reason)

    async def _check_entry_signals(self, market_data: Dict) -> None:
        """Entry sinyalleri kontrol et."""
        for symbol in self.symbols:
            if symbol not in market_data:
                continue

            # Sinyal üret
            signal = self.signal_generator.generate_signal(
                data_1h=market_data[symbol]['data_1h'],
                data_15m=market_data[symbol]['data_15m'],
                timestamp=datetime.now(timezone.utc).isoformat()
            )

            # Signal hook
            await self._trigger_hooks('on_signal', symbol=symbol, signal=signal)

            # Sinyal değerlendir
            if self._should_enter_trade(signal):
                await self._open_position(symbol, signal, market_data[symbol]['current_price'])

    def _should_enter_trade(self, signal) -> bool:
        """Trade açılmalı mı?"""
        # Minimum güven kontrolü
        if signal.confidence_score < self.config['min_signal_confidence']:
            return False

        # STRONG sinyaller için
        if signal.signal_type not in [SignalType.STRONG_BUY, SignalType.STRONG_SELL]:
            return False

        # Risk kontrolü
        # TODO: Faz 6'da gelişmiş risk kontrolü
        if self.stats.current_drawdown > self.config['max_drawdown_percent']:
            self.logger.warning("Max drawdown aşıldı, trade açılmıyor")
            return False

        return True

    def _can_open_new_position(self) -> bool:
        """Yeni pozisyon açılabilir mi?"""
        active_count = len(self.position_manager.get_active_positions())
        max_positions = self.config['max_positions']

        return active_count < max_positions

    async def _open_position(self, symbol: str, signal, current_price: float) -> None:
        """Pozisyon aç."""
        try:
            # Side belirleme
            if signal.signal_type == SignalType.STRONG_BUY:
                side = PositionSide.LONG
                order_side = OrderSide.BUY
            else:  # STRONG_SELL
                side = PositionSide.SHORT
                order_side = OrderSide.SELL

            # Pozisyon büyüklüğü hesapla
            position_size_usdt = self.config['position_size_usdt']
            quantity = position_size_usdt / current_price

            # Emir gönder
            order = await self.order_executor.submit_market_order(
                symbol=symbol,
                side=order_side,
                quantity=quantity
            )

            # Pozisyon oluştur
            position = await self.position_manager.open_position(
                symbol=symbol,
                side=side,
                entry_price=order.average_price or current_price,
                quantity=quantity,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                signal_type=signal.signal_type.value,
                signal_confidence=signal.confidence_score,
                trailing_stop_percent=self.config.get('trailing_stop_percent'),
                notes=f"Signal: {signal.signal_type.value}"
            )

            self.logger.info(f"Pozisyon açıldı: {position.position_id}")

            # Hook
            await self._trigger_hooks('on_position_open', position=position)

        except Exception as e:
            self.logger.error(f"Pozisyon açma hatası: {e}")

    async def _close_position(
        self,
        position: Position,
        current_price: float,
        reason: CloseReason
    ) -> None:
        """Pozisyon kapat."""
        try:
            # Emir gönder
            order_side = OrderSide.SELL if position.side == PositionSide.LONG else OrderSide.BUY

            order = await self.order_executor.submit_market_order(
                symbol=position.symbol,
                side=order_side,
                quantity=position.quantity,
                reduce_only=True
            )

            # Pozisyon kapat
            closed_position = await self.position_manager.close_position(
                position_id=position.position_id,
                exit_price=order.average_price or current_price,
                exit_reason=reason
            )

            # İstatistikleri güncelle
            balance = self.stats.get_net_profit()  # Basitleştirilmiş
            self.stats.update_trade(closed_position.realized_pnl, balance)

            self.logger.info(
                f"Pozisyon kapandı: {closed_position.position_id} | "
                f"PnL: ${closed_position.realized_pnl:.2f}"
            )

            # Hook
            await self._trigger_hooks('on_position_close', position=closed_position)

        except Exception as e:
            self.logger.error(f"Pozisyon kapatma hatası: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Motor durumunu getir."""
        return {
            'state': self.state.value,
            'is_running': self.is_running,
            'loop_count': self.loop_count,
            'active_positions': len(self.position_manager.get_active_positions()),
            'stats': self.stats.to_dict(),
            'position_stats': self.position_manager.get_statistics(),
            'order_stats': self.order_executor.get_statistics()
        }


if __name__ == "__main__":
    print("Trading Engine - Test")
    print("=" * 60)

    async def test_trading_engine():
        """Test fonksiyonu."""
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)

        # Mock bileşenler
        signal_gen = SignalGenerator(logger=logger)
        pos_mgr = PositionManager(logger=logger)

        class MockBinance:
            pass

        order_exec = OrderExecutor(binance_manager=MockBinance(), logger=logger)

        # Engine oluştur
        engine = TradingEngine(
            signal_generator=signal_gen,
            position_manager=pos_mgr,
            order_executor=order_exec,
            config={'symbols': ['BTCUSDT'], 'loop_interval_seconds': 2},
            logger=logger
        )
        print("✅ TradingEngine oluşturuldu")

        # Hook kaydı
        def on_signal_hook(symbol, signal):
            print(f"   [HOOK] Sinyal: {symbol} - {signal.signal_type.value}")

        engine.register_hook('on_signal', on_signal_hook)

        # Test 1: Kısa bir run
        print("\n📊 Test 1: Trading Loop (3 döngü)")

        async def run_for_loops(engine, count=3):
            await asyncio.sleep(1)
            for i in range(count):
                await engine._trading_loop()
                await asyncio.sleep(1)
            await engine.stop()

        await run_for_loops(engine, 3)

        # Status
        print("\n📊 Test 2: Status")
        status = engine.get_status()
        print(f"   State: {status['state']}")
        print(f"   Loop Count: {status['loop_count']}")
        print(f"   Win Rate: {status['stats']['win_rate']:.1f}%")

        print("\n" + "=" * 60)
        print("✅ Tüm testler başarılı!")

    asyncio.run(test_trading_engine())
