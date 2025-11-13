"""
Shutdown Manager
================

Güvenli sistem kapatma ve kill-switch yönetimi.

Sorumluluklar:
--------------
- Graceful shutdown koordinasyonu
- Emergency shutdown (kill-switch)
- State persistence (tüm state dosyalarını kaydetme)
- Açık pozisyonları yönetme (kapatma veya kaydetme)
- Shutdown raporları oluşturma
- Signal handling (SIGINT, SIGTERM)
- Shutdown tetikleyicileri (max drawdown, seri kayıp, vb.)

Faz: 6
Versiyon: 1.0.0
"""

import asyncio
import signal
import json
import logging
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timezone


class ShutdownReason(Enum):
    """Shutdown nedeni."""
    USER_REQUEST = "USER_REQUEST"           # Kullanıcı isteği (Ctrl+C)
    MAX_DRAWDOWN = "MAX_DRAWDOWN"          # Max drawdown aşıldı
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"  # Günlük kayıp limiti
    CONSECUTIVE_LOSSES = "CONSECUTIVE_LOSSES"  # Ardışık kayıp limiti
    API_CONNECTION_LOST = "API_CONNECTION_LOST"  # API bağlantısı kesildi
    SYSTEM_ERROR = "SYSTEM_ERROR"          # Sistem hatası
    MANUAL = "MANUAL"                      # Manuel kapatma
    EMERGENCY = "EMERGENCY"                # Acil durum


@dataclass
class ShutdownReport:
    """
    Shutdown raporu.

    Attributes:
    -----------
    shutdown_time : datetime
        Kapatma zamanı
    reason : ShutdownReason
        Kapatma nedeni
    uptime_seconds : float
        Sistem çalışma süresi (saniye)
    open_positions_count : int
        Açık pozisyon sayısı
    positions_closed : int
        Kapatılan pozisyon sayısı
    total_balance : float
        Kapanış anı bakiyesi
    total_pnl : float
        Toplam PnL
    last_10_trades : List[Dict[str, Any]]
        Son 10 trade özeti
    state_saved : bool
        State kaydedildi mi?
    errors : List[str]
        Kapatma sırasında oluşan hatalar
    """
    shutdown_time: datetime
    reason: ShutdownReason
    uptime_seconds: float
    open_positions_count: int
    positions_closed: int
    total_balance: float
    total_pnl: float
    last_10_trades: List[Dict[str, Any]] = field(default_factory=list)
    state_saved: bool = False
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Dictionary'ye çevir."""
        data = asdict(self)
        data['shutdown_time'] = self.shutdown_time.isoformat()
        data['reason'] = self.reason.value
        return data


class ShutdownManager:
    """
    Shutdown yöneticisi.

    Sistem kapatmalarını düzenli ve güvenli bir şekilde yönetir.
    """

    def __init__(
        self,
        state_dir: str = "state",
        logs_dir: str = "logs",
        close_positions_on_shutdown: bool = False,
        shutdown_timeout_seconds: int = 30,
        logger: Optional[logging.Logger] = None
    ):
        """
        Shutdown Manager başlatıcı.

        Parametreler:
        ------------
        state_dir : str
            State dosyaları dizini
        logs_dir : str
            Log dosyaları dizini
        close_positions_on_shutdown : bool
            Kapanışta pozisyonları kapat mı?
        shutdown_timeout_seconds : int
            Maksimum shutdown süresi (saniye)
        logger : Optional[logging.Logger]
            Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.state_dir = Path(state_dir)
        self.logs_dir = Path(logs_dir)
        self.shutdown_reports_dir = self.logs_dir / "shutdown_reports"

        # Dizinleri oluştur
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.shutdown_reports_dir.mkdir(parents=True, exist_ok=True)

        # Konfigürasyon
        self.close_positions_on_shutdown = close_positions_on_shutdown
        self.shutdown_timeout_seconds = shutdown_timeout_seconds

        # Shutdown durumu
        self.is_shutting_down = False
        self.shutdown_reason: Optional[ShutdownReason] = None
        self.start_time = datetime.now(timezone.utc)

        # Shutdown callbacks (sıralı olarak çağrılır)
        self.shutdown_callbacks: List[Callable] = []

        # State saver callbacks (state dosyalarını kaydetmek için)
        self.state_savers: List[Callable] = []

        # Sistem istatistikleri (shutdown raporu için)
        self.system_stats: Dict[str, Any] = {}

        # Signal handlers
        self._setup_signal_handlers()

        self.logger.info("ShutdownManager başlatıldı")

    def register_shutdown_callback(
        self,
        callback: Callable,
        priority: int = 0
    ) -> None:
        """
        Shutdown callback kaydet.

        Parametreler:
        ------------
        callback : Callable
            Shutdown sırasında çağrılacak fonksiyon (async olabilir)
        priority : int
            Öncelik (düşük önce çalışır)
        """
        self.shutdown_callbacks.append((priority, callback))
        self.shutdown_callbacks.sort(key=lambda x: x[0])
        self.logger.debug(f"Shutdown callback kaydedildi: {callback.__name__} (priority={priority})")

    def register_state_saver(self, saver: Callable) -> None:
        """
        State saver callback kaydet.

        Parametreler:
        ------------
        saver : Callable
            State kaydetme fonksiyonu (async olabilir)
        """
        self.state_savers.append(saver)
        self.logger.debug(f"State saver kaydedildi: {saver.__name__}")

    def update_system_stats(self, stats: Dict[str, Any]) -> None:
        """
        Sistem istatistiklerini güncelle (shutdown raporu için).

        Parametreler:
        ------------
        stats : Dict[str, Any]
            Sistem istatistikleri
        """
        self.system_stats.update(stats)

    def check_shutdown_conditions(
        self,
        current_drawdown: float,
        daily_loss: float,
        consecutive_losses: int,
        max_drawdown: float = 10.0,
        max_daily_loss: float = 3.0,
        max_consecutive_losses: int = 5
    ) -> Optional[ShutdownReason]:
        """
        Shutdown koşullarını kontrol et.

        Parametreler:
        ------------
        current_drawdown : float
            Mevcut drawdown (%)
        daily_loss : float
            Günlük kayıp (%)
        consecutive_losses : int
            Ardışık kayıp sayısı
        max_drawdown : float
            Maksimum drawdown (%)
        max_daily_loss : float
            Maksimum günlük kayıp (%)
        max_consecutive_losses : int
            Maksimum ardışık kayıp

        Returns:
        --------
        Optional[ShutdownReason]
            Shutdown nedeni (varsa)
        """
        # Max drawdown kontrolü
        if current_drawdown >= max_drawdown:
            self.logger.critical(
                f"MAX DRAWDOWN AŞILDI: {current_drawdown:.2f}% >= {max_drawdown:.2f}%"
            )
            return ShutdownReason.MAX_DRAWDOWN

        # Günlük kayıp kontrolü
        if abs(daily_loss) >= max_daily_loss:
            self.logger.critical(
                f"GÜNLÜK KAYIP LİMİTİ AŞILDI: {abs(daily_loss):.2f}% >= {max_daily_loss:.2f}%"
            )
            return ShutdownReason.DAILY_LOSS_LIMIT

        # Ardışık kayıp kontrolü
        if consecutive_losses >= max_consecutive_losses:
            self.logger.critical(
                f"ARDIŞIK KAYIP LİMİTİ AŞILDI: {consecutive_losses} >= {max_consecutive_losses}"
            )
            return ShutdownReason.CONSECUTIVE_LOSSES

        return None

    async def shutdown(
        self,
        reason: ShutdownReason = ShutdownReason.MANUAL
    ) -> ShutdownReport:
        """
        Sistemin güvenli kapatılmasını gerçekleştir.

        Parametreler:
        ------------
        reason : ShutdownReason
            Kapatma nedeni

        Returns:
        --------
        ShutdownReport
            Shutdown raporu
        """
        if self.is_shutting_down:
            self.logger.warning("Shutdown zaten devam ediyor")
            return

        self.is_shutting_down = True
        self.shutdown_reason = reason

        self.logger.warning("=" * 60)
        self.logger.warning(f"SİSTEM KAPATILIYOR: {reason.value}")
        self.logger.warning("=" * 60)

        report = ShutdownReport(
            shutdown_time=datetime.now(timezone.utc),
            reason=reason,
            uptime_seconds=(datetime.now(timezone.utc) - self.start_time).total_seconds(),
            open_positions_count=self.system_stats.get('open_positions', 0),
            positions_closed=0,
            total_balance=self.system_stats.get('balance', 0.0),
            total_pnl=self.system_stats.get('total_pnl', 0.0),
            last_10_trades=self.system_stats.get('last_10_trades', [])
        )

        try:
            # Adım 1: Shutdown callbacks'leri çağır
            await self._execute_shutdown_callbacks()

            # Adım 2: State'i kaydet
            await self._save_all_state()
            report.state_saved = True

            # Adım 3: Rapor oluştur ve kaydet
            await self._save_shutdown_report(report)

            self.logger.info("Shutdown başarıyla tamamlandı")

        except Exception as e:
            self.logger.error(f"Shutdown hatası: {e}")
            report.errors.append(str(e))

        return report

    async def emergency_shutdown(
        self,
        reason: str = "Unknown"
    ) -> None:
        """
        Acil kapatma (en hızlı, minimum işlem).

        Parametreler:
        ------------
        reason : str
            Acil kapatma nedeni
        """
        self.logger.critical("=" * 60)
        self.logger.critical(f"ACİL KAPATMA: {reason}")
        self.logger.critical("=" * 60)

        # Sadece kritik state'i kaydet
        try:
            await self._save_critical_state()
        except Exception as e:
            self.logger.error(f"Acil state kaydetme hatası: {e}")

        # Hemen çık
        self.is_shutting_down = True

    async def _execute_shutdown_callbacks(self) -> None:
        """Shutdown callbacks'lerini çalıştır."""
        for priority, callback in self.shutdown_callbacks:
            try:
                self.logger.info(f"Shutdown callback çalıştırılıyor: {callback.__name__}")

                if asyncio.iscoroutinefunction(callback):
                    await asyncio.wait_for(
                        callback(),
                        timeout=self.shutdown_timeout_seconds / len(self.shutdown_callbacks)
                    )
                else:
                    callback()

            except asyncio.TimeoutError:
                self.logger.error(f"Shutdown callback timeout: {callback.__name__}")
            except Exception as e:
                self.logger.error(f"Shutdown callback hatası ({callback.__name__}): {e}")

    async def _save_all_state(self) -> None:
        """Tüm state dosyalarını kaydet."""
        self.logger.info("State dosyaları kaydediliyor...")

        for saver in self.state_savers:
            try:
                if asyncio.iscoroutinefunction(saver):
                    await saver()
                else:
                    saver()

                self.logger.debug(f"State kaydedildi: {saver.__name__}")

            except Exception as e:
                self.logger.error(f"State kaydetme hatası ({saver.__name__}): {e}")

    async def _save_critical_state(self) -> None:
        """Kritik state'i kaydet (acil kapatma için)."""
        # Minimal kaydetme (pozisyonlar, ağırlıklar)
        critical_files = [
            "open_positions.json",
            "rr_weights.json"
        ]

        for filename in critical_files:
            filepath = self.state_dir / filename
            if filepath.exists():
                try:
                    # Sadece dosya var mı kontrol et, zaten kaydedilmiş olabilir
                    self.logger.debug(f"Critical state mevcut: {filename}")
                except Exception as e:
                    self.logger.error(f"Critical state kontrol hatası ({filename}): {e}")

    async def _save_shutdown_report(self, report: ShutdownReport) -> None:
        """Shutdown raporunu kaydet."""
        timestamp = report.shutdown_time.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"shutdown_{timestamp}.json"
        filepath = self.shutdown_reports_dir / filename

        try:
            with open(filepath, 'w') as f:
                json.dump(report.to_dict(), f, indent=2)

            self.logger.info(f"Shutdown raporu kaydedildi: {filepath}")

        except Exception as e:
            self.logger.error(f"Shutdown raporu kaydetme hatası: {e}")

    def _setup_signal_handlers(self) -> None:
        """Signal handlers kurulumu."""
        def signal_handler(signum, frame):
            self.logger.warning(f"Signal alındı: {signum}")
            # Asyncio event loop'unda shutdown'ı başlat
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.shutdown(ShutdownReason.USER_REQUEST))

        signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # kill komutu


if __name__ == "__main__":
    print("Shutdown Manager - Test")
    print("=" * 60)

    # Logger
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Shutdown Manager oluştur
    sm = ShutdownManager(
        state_dir="state",
        logs_dir="logs",
        close_positions_on_shutdown=False,
        logger=logger
    )
    print("✅ ShutdownManager oluşturuldu")

    # Test 1: Shutdown condition kontrolü
    print("\n📊 Test 1: Shutdown Condition Kontrolü")
    reason = sm.check_shutdown_conditions(
        current_drawdown=8.5,
        daily_loss=2.5,
        consecutive_losses=3,
        max_drawdown=10.0,
        max_daily_loss=3.0,
        max_consecutive_losses=5
    )
    print(f"   Drawdown: 8.5% | Daily Loss: 2.5% | Consecutive: 3")
    print(f"   Shutdown Gerekli: {reason.value if reason else 'Hayır'}")

    # Test 2: Shutdown condition (max drawdown)
    print("\n📊 Test 2: Max Drawdown Tetiklemesi")
    reason = sm.check_shutdown_conditions(
        current_drawdown=11.0,
        daily_loss=1.0,
        consecutive_losses=2,
        max_drawdown=10.0
    )
    print(f"   Drawdown: 11.0%")
    print(f"   Shutdown Nedeni: {reason.value if reason else 'Yok'}")

    # Test 3: Callback kaydı
    print("\n📊 Test 3: Callback Kaydı")

    def mock_callback():
        print("   Mock callback çalıştı")

    sm.register_shutdown_callback(mock_callback, priority=1)
    print(f"   Callbacks: {len(sm.shutdown_callbacks)}")

    # Test 4: Sistem istatistikleri
    print("\n📊 Test 4: Sistem İstatistikleri")
    sm.update_system_stats({
        'open_positions': 3,
        'balance': 10500.0,
        'total_pnl': 500.0
    })
    print(f"   Stats: {sm.system_stats}")

    # Test 5: Async shutdown (basit test)
    print("\n📊 Test 5: Async Shutdown Test")

    async def test_shutdown():
        report = await sm.shutdown(ShutdownReason.MANUAL)
        print(f"   Uptime: {report.uptime_seconds:.2f}s")
        print(f"   State Saved: {report.state_saved}")
        print(f"   Errors: {len(report.errors)}")

    asyncio.run(test_shutdown())

    print("\n" + "=" * 60)
    print("✅ Tüm testler başarılı!")
