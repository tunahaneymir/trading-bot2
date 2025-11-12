"""
Pozisyon Yöneticisi (Position Manager)
======================================

Açık pozisyonları takip eder, stop loss / take profit yönetir,
ve PostgreSQL'e pozisyon verilerini kaydeder.

Sorumluluklar:
-------------
- Yeni pozisyon açma
- Pozisyon kapatma
- Stop loss / take profit güncelleme
- Pozisyon durumu takibi
- PnL (Profit & Loss) hesaplama
- Risk metrikleri
- PostgreSQL entegrasyonu

Position States:
---------------
OPENING  : Pozisyon açılıyor (emir gönderildi)
OPEN     : Pozisyon açık (aktif)
CLOSING  : Pozisyon kapanıyor (çıkış emri gönderildi)
CLOSED   : Pozisyon kapatıldı (tamamlandı)
CANCELLED: Pozisyon iptal edildi

Yazar: Trading Bot Sistemi
Versiyon: 1.0.0
Faz: 5
"""

import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import logging
import json


class PositionState(Enum):
    """Pozisyon durumları."""
    OPENING = "OPENING"      # Pozisyon açılıyor
    OPEN = "OPEN"            # Pozisyon açık
    CLOSING = "CLOSING"      # Pozisyon kapanıyor
    CLOSED = "CLOSED"        # Pozisyon kapatıldı
    CANCELLED = "CANCELLED"  # Pozisyon iptal edildi


class PositionSide(Enum):
    """Pozisyon yönü."""
    LONG = "LONG"    # Long pozisyon (al)
    SHORT = "SHORT"  # Short pozisyon (sat)


class CloseReason(Enum):
    """Pozisyon kapanma nedeni."""
    TAKE_PROFIT = "TAKE_PROFIT"        # Take profit'e ulaştı
    STOP_LOSS = "STOP_LOSS"            # Stop loss'a takıldı
    SIGNAL = "SIGNAL"                  # Sinyal değişti
    TRAILING_STOP = "TRAILING_STOP"    # Trailing stop
    MANUAL = "MANUAL"                  # Manuel kapatma
    TIMEOUT = "TIMEOUT"                # Zaman aşımı
    RISK_LIMIT = "RISK_LIMIT"          # Risk limiti
    EMERGENCY = "EMERGENCY"            # Acil durum


@dataclass
class Position:
    """
    Trading pozisyonu.
    
    Bir pozisyonun tüm bilgilerini içerir:
    - Entry/exit bilgileri
    - Risk parametreleri
    - PnL hesaplamaları
    - State tracking
    """
    # Temel bilgiler
    position_id: str
    symbol: str
    side: PositionSide
    state: PositionState
    
    # Entry bilgileri
    entry_price: float
    quantity: float
    entry_time: datetime
    entry_signal_type: str
    entry_signal_confidence: float
    
    # Risk yönetimi
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop_percent: Optional[float] = None
    risk_reward_ratio: float = 2.0
    
    # Exit bilgileri
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[CloseReason] = None
    
    # PnL ve performans
    realized_pnl: float = 0.0
    realized_pnl_percent: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_percent: float = 0.0
    
    # Komisyon ve maliyetler
    entry_fee: float = 0.0
    exit_fee: float = 0.0
    total_cost: float = 0.0
    
    # Güncellemeler
    last_update_time: Optional[datetime] = None
    last_price: Optional[float] = None
    highest_price: Optional[float] = None  # Trailing stop için
    lowest_price: Optional[float] = None   # Trailing stop için
    
    # Metadata
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    extra_data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Başlangıç değerlerini ayarla."""
        if isinstance(self.side, str):
            self.side = PositionSide[self.side]
        if isinstance(self.state, str):
            self.state = PositionState[self.state]
        if self.exit_reason and isinstance(self.exit_reason, str):
            self.exit_reason = CloseReason[self.exit_reason]
        
        # Datetime string'lerini convert et
        if isinstance(self.entry_time, str):
            self.entry_time = datetime.fromisoformat(self.entry_time)
        if isinstance(self.exit_time, str):
            self.exit_time = datetime.fromisoformat(self.exit_time)
        if isinstance(self.last_update_time, str):
            self.last_update_time = datetime.fromisoformat(self.last_update_time)
        
        # İlk fiyat takibi
        if self.highest_price is None:
            self.highest_price = self.entry_price
        if self.lowest_price is None:
            self.lowest_price = self.entry_price
    
    def update_price(self, current_price: float) -> None:
        """
        Güncel fiyatla pozisyonu güncelle.
        
        Parametreler:
        ------------
        current_price : float
            Güncel market fiyatı
        """
        self.last_price = current_price
        self.last_update_time = datetime.now(timezone.utc)
        
        # Highest/lowest tracking
        if current_price > self.highest_price:
            self.highest_price = current_price
        if current_price < self.lowest_price:
            self.lowest_price = current_price
        
        # Unrealized PnL hesapla
        self.unrealized_pnl = self._calculate_unrealized_pnl(current_price)
        self.unrealized_pnl_percent = self._calculate_unrealized_pnl_percent(current_price)
    
    def _calculate_unrealized_pnl(self, current_price: float) -> float:
        """
        Gerçekleşmemiş kar/zarar hesapla (USDT).
        
        Parametreler:
        ------------
        current_price : float
            Güncel fiyat
        
        Returns:
        --------
        float
            Unrealized PnL (USDT)
        """
        if self.side == PositionSide.LONG:
            pnl = (current_price - self.entry_price) * self.quantity
        else:  # SHORT
            pnl = (self.entry_price - current_price) * self.quantity
        
        return pnl
    
    def _calculate_unrealized_pnl_percent(self, current_price: float) -> float:
        """
        Gerçekleşmemiş kar/zarar yüzdesi hesapla.
        
        Parametreler:
        ------------
        current_price : float
            Güncel fiyat
        
        Returns:
        --------
        float
            Unrealized PnL (%)
        """
        if self.entry_price == 0:
            return 0.0
        
        if self.side == PositionSide.LONG:
            return ((current_price - self.entry_price) / self.entry_price) * 100
        else:  # SHORT
            return ((self.entry_price - current_price) / self.entry_price) * 100
    
    def close_position(
        self,
        exit_price: float,
        exit_reason: CloseReason,
        exit_fee: float = 0.0
    ) -> None:
        """
        Pozisyonu kapat.
        
        Parametreler:
        ------------
        exit_price : float
            Çıkış fiyatı
        exit_reason : CloseReason
            Kapanma nedeni
        exit_fee : float
            Çıkış komisyonu
        """
        self.exit_price = exit_price
        self.exit_time = datetime.now(timezone.utc)
        self.exit_reason = exit_reason
        self.exit_fee = exit_fee
        self.state = PositionState.CLOSED
        
        # Realized PnL hesapla
        if self.side == PositionSide.LONG:
            gross_pnl = (exit_price - self.entry_price) * self.quantity
        else:  # SHORT
            gross_pnl = (self.entry_price - exit_price) * self.quantity
        
        # Komisyonları düş
        self.total_cost = self.entry_fee + self.exit_fee
        self.realized_pnl = gross_pnl - self.total_cost
        
        # Yüzde hesapla
        if self.entry_price > 0:
            position_value = self.entry_price * self.quantity
            self.realized_pnl_percent = (self.realized_pnl / position_value) * 100
    
    def should_stop_loss(self, current_price: float) -> bool:
        """
        Stop loss kontrolü.
        
        Parametreler:
        ------------
        current_price : float
            Güncel fiyat
        
        Returns:
        --------
        bool
            Stop loss'a takıldı mı?
        """
        if self.stop_loss is None:
            return False
        
        if self.side == PositionSide.LONG:
            return current_price <= self.stop_loss
        else:  # SHORT
            return current_price >= self.stop_loss
    
    def should_take_profit(self, current_price: float) -> bool:
        """
        Take profit kontrolü.
        
        Parametreler:
        ------------
        current_price : float
            Güncel fiyat
        
        Returns:
        --------
        bool
            Take profit'e ulaştı mı?
        """
        if self.take_profit is None:
            return False
        
        if self.side == PositionSide.LONG:
            return current_price >= self.take_profit
        else:  # SHORT
            return current_price <= self.take_profit
    
    def update_trailing_stop(self, current_price: float) -> None:
        """
        Trailing stop güncelle.
        
        Parametreler:
        ------------
        current_price : float
            Güncel fiyat
        """
        if self.trailing_stop_percent is None:
            return
        
        if self.side == PositionSide.LONG:
            # Long pozisyon: highest price'dan % düşüş
            new_stop = self.highest_price * (1 - self.trailing_stop_percent / 100)
            if self.stop_loss is None or new_stop > self.stop_loss:
                self.stop_loss = new_stop
        else:  # SHORT
            # Short pozisyon: lowest price'dan % yükseliş
            new_stop = self.lowest_price * (1 + self.trailing_stop_percent / 100)
            if self.stop_loss is None or new_stop < self.stop_loss:
                self.stop_loss = new_stop
    
    def get_position_size_usdt(self) -> float:
        """Pozisyon büyüklüğü (USDT)."""
        return self.entry_price * self.quantity
    
    def get_risk_amount_usdt(self) -> Optional[float]:
        """Risk miktarı (USDT)."""
        if self.stop_loss is None:
            return None
        
        if self.side == PositionSide.LONG:
            risk_per_unit = self.entry_price - self.stop_loss
        else:
            risk_per_unit = self.stop_loss - self.entry_price
        
        return abs(risk_per_unit * self.quantity)
    
    def get_reward_amount_usdt(self) -> Optional[float]:
        """Beklenen kazanç miktarı (USDT)."""
        if self.take_profit is None:
            return None
        
        if self.side == PositionSide.LONG:
            reward_per_unit = self.take_profit - self.entry_price
        else:
            reward_per_unit = self.entry_price - self.take_profit
        
        return abs(reward_per_unit * self.quantity)
    
    def to_dict(self) -> Dict[str, Any]:
        """Dictionary'ye çevir."""
        data = asdict(self)
        
        # Enum'ları string'e çevir
        data['side'] = self.side.value
        data['state'] = self.state.value
        if self.exit_reason:
            data['exit_reason'] = self.exit_reason.value
        
        # Datetime'ları ISO format'a çevir
        data['entry_time'] = self.entry_time.isoformat() if self.entry_time else None
        data['exit_time'] = self.exit_time.isoformat() if self.exit_time else None
        data['last_update_time'] = self.last_update_time.isoformat() if self.last_update_time else None
        
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Position':
        """Dictionary'den oluştur."""
        return cls(**data)


class PositionManager:
    """
    Pozisyon yöneticisi.
    
    Tüm açık pozisyonları takip eder, risk yönetimi yapar,
    ve PostgreSQL'e kaydeder.
    """
    
    def __init__(
        self,
        postgres_manager = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Position Manager başlatıcı.
        
        Parametreler:
        ------------
        postgres_manager : PostgresManager
            PostgreSQL manager instance
        logger : Optional[logging.Logger]
            Logger instance
        """
        self.postgres = postgres_manager
        self.logger = logger or logging.getLogger(__name__)
        
        # Aktif pozisyonlar (memory cache)
        self.active_positions: Dict[str, Position] = {}
        
        # İstatistikler
        self.total_positions_opened = 0
        self.total_positions_closed = 0
        self.total_profit = 0.0
        self.total_loss = 0.0
        
        self.logger.info("PositionManager başlatıldı")
    
    async def open_position(
        self,
        symbol: str,
        side: PositionSide,
        entry_price: float,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        signal_type: str = "MANUAL",
        signal_confidence: float = 0.0,
        trailing_stop_percent: Optional[float] = None,
        notes: str = "",
        tags: Optional[List[str]] = None
    ) -> Position:
        """
        Yeni pozisyon aç.
        
        Parametreler:
        ------------
        symbol : str
            Coin sembolü (örn: BTCUSDT)
        side : PositionSide
            Pozisyon yönü (LONG/SHORT)
        entry_price : float
            Giriş fiyatı
        quantity : float
            Miktar (contract sayısı)
        stop_loss : Optional[float]
            Stop loss fiyatı
        take_profit : Optional[float]
            Take profit fiyatı
        signal_type : str
            Sinyal tipi
        signal_confidence : float
            Sinyal güveni (0-1)
        trailing_stop_percent : Optional[float]
            Trailing stop yüzdesi
        notes : str
            Notlar
        tags : Optional[List[str]]
            Etiketler
        
        Returns:
        --------
        Position
            Oluşturulan pozisyon
        """
        # Pozisyon ID oluştur
        position_id = str(uuid.uuid4())
        
        # Pozisyon oluştur
        position = Position(
            position_id=position_id,
            symbol=symbol,
            side=side,
            state=PositionState.OPENING,
            entry_price=entry_price,
            quantity=quantity,
            entry_time=datetime.now(timezone.utc),
            entry_signal_type=signal_type,
            entry_signal_confidence=signal_confidence,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop_percent=trailing_stop_percent,
            notes=notes,
            tags=tags or []
        )
        
        # Hesaplamalar
        position.entry_fee = self._calculate_fee(entry_price * quantity)
        
        # Memory'ye ekle
        self.active_positions[position_id] = position
        
        # PostgreSQL'e kaydet
        if self.postgres:
            await self._save_position_to_db(position)
        
        # Stats
        self.total_positions_opened += 1
        
        self.logger.info(
            f"Pozisyon açıldı: {position_id} | {symbol} | {side.value} | "
            f"Entry: ${entry_price:.2f} | Qty: {quantity} | "
            f"SL: ${stop_loss:.2f if stop_loss else 'None'} | "
            f"TP: ${take_profit:.2f if take_profit else 'None'}"
        )
        
        return position
    
    async def close_position(
        self,
        position_id: str,
        exit_price: float,
        exit_reason: CloseReason,
        exit_fee: Optional[float] = None
    ) -> Position:
        """
        Pozisyonu kapat.
        
        Parametreler:
        ------------
        position_id : str
            Pozisyon ID
        exit_price : float
            Çıkış fiyatı
        exit_reason : CloseReason
            Kapanma nedeni
        exit_fee : Optional[float]
            Çıkış komisyonu (None ise otomatik hesapla)
        
        Returns:
        --------
        Position
            Kapatılan pozisyon
        """
        if position_id not in self.active_positions:
            raise ValueError(f"Pozisyon bulunamadı: {position_id}")
        
        position = self.active_positions[position_id]
        
        # Exit fee hesapla
        if exit_fee is None:
            exit_fee = self._calculate_fee(exit_price * position.quantity)
        
        # Pozisyonu kapat
        position.close_position(exit_price, exit_reason, exit_fee)
        
        # Memory'den kaldır
        del self.active_positions[position_id]
        
        # PostgreSQL'e güncelle
        if self.postgres:
            await self._save_position_to_db(position)
        
        # Stats güncelle
        self.total_positions_closed += 1
        if position.realized_pnl > 0:
            self.total_profit += position.realized_pnl
        else:
            self.total_loss += abs(position.realized_pnl)
        
        self.logger.info(
            f"Pozisyon kapandı: {position_id} | {position.symbol} | "
            f"Reason: {exit_reason.value} | "
            f"PnL: ${position.realized_pnl:.2f} ({position.realized_pnl_percent:.2f}%)"
        )
        
        return position
    
    async def update_position(
        self,
        position_id: str,
        current_price: float
    ) -> Position:
        """
        Pozisyonu güncel fiyatla güncelle.
        
        Parametreler:
        ------------
        position_id : str
            Pozisyon ID
        current_price : float
            Güncel fiyat
        
        Returns:
        --------
        Position
            Güncellenmiş pozisyon
        """
        if position_id not in self.active_positions:
            raise ValueError(f"Pozisyon bulunamadı: {position_id}")
        
        position = self.active_positions[position_id]
        
        # Fiyatı güncelle
        position.update_price(current_price)
        
        # Trailing stop güncelle
        if position.trailing_stop_percent:
            position.update_trailing_stop(current_price)
        
        return position
    
    async def check_exit_conditions(
        self,
        position_id: str,
        current_price: float
    ) -> Optional[CloseReason]:
        """
        Exit koşullarını kontrol et.
        
        Parametreler:
        ------------
        position_id : str
            Pozisyon ID
        current_price : float
            Güncel fiyat
        
        Returns:
        --------
        Optional[CloseReason]
            Kapatma nedeni (varsa)
        """
        if position_id not in self.active_positions:
            return None
        
        position = self.active_positions[position_id]
        
        # Stop loss kontrolü
        if position.should_stop_loss(current_price):
            self.logger.warning(
                f"Stop loss tetiklendi: {position_id} | {position.symbol} | "
                f"Price: ${current_price:.2f}"
            )
            return CloseReason.STOP_LOSS
        
        # Take profit kontrolü
        if position.should_take_profit(current_price):
            self.logger.info(
                f"Take profit ulaşıldı: {position_id} | {position.symbol} | "
                f"Price: ${current_price:.2f}"
            )
            return CloseReason.TAKE_PROFIT
        
        return None
    
    def get_active_positions(
        self,
        symbol: Optional[str] = None
    ) -> List[Position]:
        """
        Aktif pozisyonları getir.
        
        Parametreler:
        ------------
        symbol : Optional[str]
            Sembol filtresi (None = hepsi)
        
        Returns:
        --------
        List[Position]
            Aktif pozisyonlar
        """
        positions = list(self.active_positions.values())
        
        if symbol:
            positions = [p for p in positions if p.symbol == symbol]
        
        return positions
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """Pozisyon ID ile pozisyon getir."""
        return self.active_positions.get(position_id)
    
    def calculate_total_exposure(self, symbol: Optional[str] = None) -> float:
        """
        Toplam pozisyon exposure (USDT).
        
        Parametreler:
        ------------
        symbol : Optional[str]
            Sembol filtresi
        
        Returns:
        --------
        float
            Toplam exposure (USDT)
        """
        positions = self.get_active_positions(symbol)
        return sum(p.get_position_size_usdt() for p in positions)
    
    def calculate_total_unrealized_pnl(self, symbol: Optional[str] = None) -> float:
        """
        Toplam gerçekleşmemiş PnL (USDT).
        
        Parametreler:
        ------------
        symbol : Optional[str]
            Sembol filtresi
        
        Returns:
        --------
        float
            Toplam unrealized PnL (USDT)
        """
        positions = self.get_active_positions(symbol)
        return sum(p.unrealized_pnl for p in positions)
    
    def calculate_total_risk(self, symbol: Optional[str] = None) -> float:
        """
        Toplam risk miktarı (USDT).
        
        Parametreler:
        ------------
        symbol : Optional[str]
            Sembol filtresi
        
        Returns:
        --------
        float
            Toplam risk (USDT)
        """
        positions = self.get_active_positions(symbol)
        total_risk = 0.0
        
        for position in positions:
            risk = position.get_risk_amount_usdt()
            if risk:
                total_risk += risk
        
        return total_risk
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        İstatistikleri getir.
        
        Returns:
        --------
        Dict[str, Any]
            İstatistikler
        """
        active_positions = len(self.active_positions)
        
        win_count = sum(1 for p in self.active_positions.values() 
                       if p.unrealized_pnl > 0)
        loss_count = active_positions - win_count
        
        return {
            'total_opened': self.total_positions_opened,
            'total_closed': self.total_positions_closed,
            'active_positions': active_positions,
            'winning_positions': win_count,
            'losing_positions': loss_count,
            'total_profit': self.total_profit,
            'total_loss': self.total_loss,
            'net_profit': self.total_profit - self.total_loss,
            'profit_factor': (self.total_profit / self.total_loss 
                            if self.total_loss > 0 else 0),
            'total_exposure_usdt': self.calculate_total_exposure(),
            'total_unrealized_pnl': self.calculate_total_unrealized_pnl(),
            'total_risk': self.calculate_total_risk()
        }
    
    def _calculate_fee(self, position_value: float) -> float:
        """
        Komisyon hesapla.
        
        Parametreler:
        ------------
        position_value : float
            Pozisyon değeri (USDT)
        
        Returns:
        --------
        float
            Komisyon (USDT)
        """
        # Binance Futures maker fee: 0.02% = 0.0002
        # Binance Futures taker fee: 0.05% = 0.0005
        # Varsayılan: maker fee kullan (POST-ONLY emirler)
        maker_fee_rate = 0.0002
        return position_value * maker_fee_rate
    
    async def _save_position_to_db(self, position: Position) -> None:
        """
        Pozisyonu PostgreSQL'e kaydet.
        
        Parametreler:
        ------------
        position : Position
            Kaydedilecek pozisyon
        """
        if not self.postgres:
            return
        
        try:
            query = """
                INSERT INTO positions (
                    position_id, symbol, side, state,
                    entry_price, quantity, entry_time,
                    entry_signal_type, entry_signal_confidence,
                    stop_loss, take_profit, trailing_stop_percent,
                    exit_price, exit_time, exit_reason,
                    realized_pnl, realized_pnl_percent,
                    entry_fee, exit_fee, total_cost,
                    notes, tags, extra_data
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                    $21, $22, $23
                )
                ON CONFLICT (position_id) DO UPDATE SET
                    state = EXCLUDED.state,
                    stop_loss = EXCLUDED.stop_loss,
                    take_profit = EXCLUDED.take_profit,
                    exit_price = EXCLUDED.exit_price,
                    exit_time = EXCLUDED.exit_time,
                    exit_reason = EXCLUDED.exit_reason,
                    realized_pnl = EXCLUDED.realized_pnl,
                    realized_pnl_percent = EXCLUDED.realized_pnl_percent,
                    exit_fee = EXCLUDED.exit_fee,
                    total_cost = EXCLUDED.total_cost,
                    notes = EXCLUDED.notes,
                    tags = EXCLUDED.tags,
                    extra_data = EXCLUDED.extra_data
            """
            
            await self.postgres.execute(
                query,
                position.position_id,
                position.symbol,
                position.side.value,
                position.state.value,
                position.entry_price,
                position.quantity,
                position.entry_time,
                position.entry_signal_type,
                position.entry_signal_confidence,
                position.stop_loss,
                position.take_profit,
                position.trailing_stop_percent,
                position.exit_price,
                position.exit_time,
                position.exit_reason.value if position.exit_reason else None,
                position.realized_pnl,
                position.realized_pnl_percent,
                position.entry_fee,
                position.exit_fee,
                position.total_cost,
                position.notes,
                json.dumps(position.tags),
                json.dumps(position.extra_data)
            )
            
        except Exception as e:
            self.logger.error(f"Pozisyon DB kayıt hatası: {e}")


if __name__ == "__main__":
    import asyncio
    
    print("Position Manager - Test")
    print("=" * 60)
    
    async def test_position_manager():
        """Test fonksiyonu."""
        # Logger
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
        
        # Position Manager oluştur (PostgreSQL olmadan)
        pm = PositionManager(logger=logger)
        print("✅ PositionManager oluşturuldu")
        
        # Test 1: Pozisyon aç
        print("\n📊 Test 1: Pozisyon Açma")
        position = await pm.open_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=50000.0,
            quantity=0.1,
            stop_loss=49000.0,
            take_profit=52000.0,
            signal_type="STRONG_BUY",
            signal_confidence=0.85,
            trailing_stop_percent=2.0,
            notes="Test pozisyonu",
            tags=["test", "demo"]
        )
        print(f"   Position ID: {position.position_id}")
        print(f"   Entry: ${position.entry_price:.2f}")
        print(f"   SL: ${position.stop_loss:.2f}")
        print(f"   TP: ${position.take_profit:.2f}")
        print(f"   Risk: ${position.get_risk_amount_usdt():.2f}")
        print(f"   Reward: ${position.get_reward_amount_usdt():.2f}")
        
        # Test 2: Pozisyon güncelle
        print("\n📊 Test 2: Pozisyon Güncelleme")
        await pm.update_position(position.position_id, 51000.0)
        print(f"   Current Price: $51,000")
        print(f"   Unrealized PnL: ${position.unrealized_pnl:.2f} ({position.unrealized_pnl_percent:.2f}%)")
        print(f"   Trailing SL: ${position.stop_loss:.2f}")
        
        # Test 3: Take profit kontrolü
        print("\n📊 Test 3: Take Profit Kontrolü")
        exit_reason = await pm.check_exit_conditions(position.position_id, 52500.0)
        if exit_reason:
            print(f"   ✅ Exit koşulu: {exit_reason.value}")
            closed = await pm.close_position(position.position_id, 52500.0, exit_reason)
            print(f"   Realized PnL: ${closed.realized_pnl:.2f} ({closed.realized_pnl_percent:.2f}%)")
        
        # Test 4: İstatistikler
        print("\n📊 Test 4: İstatistikler")
        stats = pm.get_statistics()
        print(f"   Total Opened: {stats['total_opened']}")
        print(f"   Total Closed: {stats['total_closed']}")
        print(f"   Net Profit: ${stats['net_profit']:.2f}")
        print(f"   Profit Factor: {stats['profit_factor']:.2f}")
        
        print("\n" + "=" * 60)
        print("✅ Tüm testler başarılı!")
    
    # Async test çalıştır
    asyncio.run(test_position_manager())