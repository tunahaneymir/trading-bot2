"""
Emir Yürütücü (Order Executor)
================================

Binance Futures API'ye emir gönderme ve yönetme sistemi.

Sorumluluklar:
-------------
- Market ve limit emirleri gönderme
- Emir durumu takibi
- Stop loss / take profit emirleri
- Emir iptal ve modifikasyon
- Kayma (slippage) yönetimi
- Rate limiting ve hata yönetimi
- POST-ONLY limit emirleri (maker fee)

Order Types:
-----------
- MARKET: Market emri (anında al/sat)
- LIMIT: Limit emri (belirli fiyattan)
- STOP_MARKET: Stop market emri
- TAKE_PROFIT_MARKET: Take profit emri
- STOP_LOSS: Stop loss emri
- TAKE_PROFIT: Take profit emri

Yazar: Trading Bot Sistemi
Versiyon: 1.0.0
Faz: 5
"""

import asyncio
import uuid
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timezone
import logging


class OrderType(Enum):
    """Emir tipleri."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"


class OrderSide(Enum):
    """Emir yönü."""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    """Emir durumu."""
    PENDING = "PENDING"          # Henüz gönderilmedi
    SUBMITTED = "SUBMITTED"      # Binance'e gönderildi
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # Kısmen gerçekleşti
    FILLED = "FILLED"            # Tamamen gerçekleşti
    CANCELLED = "CANCELLED"      # İptal edildi
    REJECTED = "REJECTED"        # Reddedildi
    EXPIRED = "EXPIRED"          # Süresi doldu
    FAILED = "FAILED"            # Başarısız


class TimeInForce(Enum):
    """Time in force tipleri."""
    GTC = "GTC"  # Good Till Cancel
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill
    GTX = "GTX"  # Good Till Crossing (Post-Only)


@dataclass
class Order:
    """
    Trading emri.

    Bir emrin tüm bilgilerini içerir:
    - Emir parametreleri
    - Durum takibi
    - Gerçekleşme bilgileri
    """
    # Temel bilgiler
    order_id: str
    symbol: str
    order_type: OrderType
    side: OrderSide
    quantity: float

    # Fiyat bilgileri
    price: Optional[float] = None  # Limit emirler için
    stop_price: Optional[float] = None  # Stop emirler için

    # Durum
    status: OrderStatus = OrderStatus.PENDING
    time_in_force: TimeInForce = TimeInForce.GTC

    # Gerçekleşme bilgileri
    filled_quantity: float = 0.0
    average_price: Optional[float] = None
    commission: float = 0.0

    # Binance bilgileri
    binance_order_id: Optional[int] = None
    client_order_id: Optional[str] = None

    # Zaman bilgileri
    created_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None

    # Metadata
    notes: str = ""
    tags: List[str] = None
    extra_data: Dict[str, Any] = None

    def __post_init__(self):
        """Başlangıç değerlerini ayarla."""
        if isinstance(self.order_type, str):
            self.order_type = OrderType[self.order_type]
        if isinstance(self.side, str):
            self.side = OrderSide[self.side]
        if isinstance(self.status, str):
            self.status = OrderStatus[self.status]
        if isinstance(self.time_in_force, str):
            self.time_in_force = TimeInForce[self.time_in_force]

        if self.tags is None:
            self.tags = []
        if self.extra_data is None:
            self.extra_data = {}

        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

        # Client order ID oluştur
        if self.client_order_id is None:
            self.client_order_id = f"bot_{self.order_id[:8]}"

    def is_filled(self) -> bool:
        """Emir tamamen gerçekleşti mi?"""
        return self.status == OrderStatus.FILLED

    def is_active(self) -> bool:
        """Emir hala aktif mi?"""
        return self.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED]

    def is_closed(self) -> bool:
        """Emir kapandı mı?"""
        return self.status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED, OrderStatus.FAILED]

    def get_fill_percentage(self) -> float:
        """Gerçekleşme yüzdesi."""
        if self.quantity == 0:
            return 0.0
        return (self.filled_quantity / self.quantity) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Dictionary'ye çevir."""
        data = asdict(self)

        # Enum'ları string'e çevir
        data['order_type'] = self.order_type.value
        data['side'] = self.side.value
        data['status'] = self.status.value
        data['time_in_force'] = self.time_in_force.value

        # Datetime'ları ISO format'a çevir
        data['created_at'] = self.created_at.isoformat() if self.created_at else None
        data['submitted_at'] = self.submitted_at.isoformat() if self.submitted_at else None
        data['filled_at'] = self.filled_at.isoformat() if self.filled_at else None

        return data


class OrderExecutor:
    """
    Emir yürütücü.

    Binance Futures API'ye emir gönderir ve yönetir.
    """

    def __init__(
        self,
        binance_manager,
        rate_limiter=None,
        logger: Optional[logging.Logger] = None,
        config: Optional[Dict] = None
    ):
        """
        Order Executor başlatıcı.

        Parametreler:
        ------------
        binance_manager : BinanceManager
            Binance API manager
        rate_limiter : RateLimiter, optional
            Rate limiter instance
        logger : Optional[logging.Logger]
            Logger instance
        config : Optional[Dict]
            Konfigürasyon ayarları
        """
        self.binance = binance_manager
        self.rate_limiter = rate_limiter
        self.logger = logger or logging.getLogger(__name__)
        self.config = config or self._default_config()

        # Aktif emirler (memory cache)
        self.active_orders: Dict[str, Order] = {}

        # İstatistikler
        self.total_orders_submitted = 0
        self.total_orders_filled = 0
        self.total_orders_cancelled = 0
        self.total_orders_rejected = 0

        self.logger.info("OrderExecutor başlatıldı")

    def _default_config(self) -> Dict:
        """Varsayılan konfigürasyon."""
        return {
            'max_slippage_percent': 0.5,  # Maksimum kayma %0.5
            'order_timeout_seconds': 300,  # 5 dakika
            'use_post_only': True,  # POST-ONLY (maker fee)
            'retry_attempts': 3,
            'retry_delay_seconds': 1.0,
            'enable_rate_limiting': True
        }

    async def submit_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        reduce_only: bool = False
    ) -> Order:
        """
        Market emri gönder.

        Parametreler:
        ------------
        symbol : str
            Coin sembolü (örn: BTCUSDT)
        side : OrderSide
            Emir yönü (BUY/SELL)
        quantity : float
            Miktar
        reduce_only : bool
            Sadece pozisyon azaltma

        Returns:
        --------
        Order
            Gönderilen emir
        """
        # Order oluştur
        order = Order(
            order_id=str(uuid.uuid4()),
            symbol=symbol,
            order_type=OrderType.MARKET,
            side=side,
            quantity=quantity
        )

        try:
            # Rate limiting
            if self.config['enable_rate_limiting'] and self.rate_limiter:
                await self.rate_limiter.acquire()

            # Binance'e gönder
            order.status = OrderStatus.SUBMITTED
            order.submitted_at = datetime.now(timezone.utc)

            response = await self._send_to_binance_futures(
                symbol=symbol,
                side=side.value,
                order_type='MARKET',
                quantity=quantity,
                reduce_only=reduce_only
            )

            # Response'u parse et
            self._update_order_from_response(order, response)

            # Stats
            self.total_orders_submitted += 1
            if order.is_filled():
                self.total_orders_filled += 1

            self.logger.info(
                f"Market emir gönderildi: {order.order_id} | {symbol} | {side.value} | "
                f"Qty: {quantity} | Status: {order.status.value}"
            )

            return order

        except Exception as e:
            order.status = OrderStatus.FAILED
            self.logger.error(f"Market emir hatası: {e}")
            raise

    async def submit_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        post_only: bool = True,
        time_in_force: TimeInForce = TimeInForce.GTC
    ) -> Order:
        """
        Limit emri gönder.

        Parametreler:
        ------------
        symbol : str
            Coin sembolü
        side : OrderSide
            Emir yönü
        quantity : float
            Miktar
        price : float
            Limit fiyatı
        post_only : bool
            POST-ONLY (maker fee)
        time_in_force : TimeInForce
            Time in force

        Returns:
        --------
        Order
            Gönderilen emir
        """
        # POST-ONLY için GTX kullan
        if post_only:
            time_in_force = TimeInForce.GTX

        # Order oluştur
        order = Order(
            order_id=str(uuid.uuid4()),
            symbol=symbol,
            order_type=OrderType.LIMIT,
            side=side,
            quantity=quantity,
            price=price,
            time_in_force=time_in_force
        )

        try:
            # Rate limiting
            if self.config['enable_rate_limiting'] and self.rate_limiter:
                await self.rate_limiter.acquire()

            # Binance'e gönder
            order.status = OrderStatus.SUBMITTED
            order.submitted_at = datetime.now(timezone.utc)

            response = await self._send_to_binance_futures(
                symbol=symbol,
                side=side.value,
                order_type='LIMIT',
                quantity=quantity,
                price=price,
                time_in_force=time_in_force.value
            )

            # Response'u parse et
            self._update_order_from_response(order, response)

            # Aktif emirlere ekle
            if order.is_active():
                self.active_orders[order.order_id] = order

            # Stats
            self.total_orders_submitted += 1

            self.logger.info(
                f"Limit emir gönderildi: {order.order_id} | {symbol} | {side.value} | "
                f"Price: ${price:.2f} | Qty: {quantity} | TIF: {time_in_force.value}"
            )

            return order

        except Exception as e:
            order.status = OrderStatus.FAILED
            self.logger.error(f"Limit emir hatası: {e}")
            raise

    async def submit_stop_loss_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        stop_price: float,
        reduce_only: bool = True
    ) -> Order:
        """
        Stop loss emri gönder.

        Parametreler:
        ------------
        symbol : str
            Coin sembolü
        side : OrderSide
            Emir yönü
        quantity : float
            Miktar
        stop_price : float
            Stop fiyatı
        reduce_only : bool
            Sadece pozisyon kapatma

        Returns:
        --------
        Order
            Gönderilen emir
        """
        order = Order(
            order_id=str(uuid.uuid4()),
            symbol=symbol,
            order_type=OrderType.STOP_MARKET,
            side=side,
            quantity=quantity,
            stop_price=stop_price
        )

        try:
            if self.config['enable_rate_limiting'] and self.rate_limiter:
                await self.rate_limiter.acquire()

            order.status = OrderStatus.SUBMITTED
            order.submitted_at = datetime.now(timezone.utc)

            response = await self._send_to_binance_futures(
                symbol=symbol,
                side=side.value,
                order_type='STOP_MARKET',
                quantity=quantity,
                stop_price=stop_price,
                reduce_only=reduce_only
            )

            self._update_order_from_response(order, response)

            if order.is_active():
                self.active_orders[order.order_id] = order

            self.total_orders_submitted += 1

            self.logger.info(
                f"Stop loss emri: {order.order_id} | {symbol} | Stop: ${stop_price:.2f}"
            )

            return order

        except Exception as e:
            order.status = OrderStatus.FAILED
            self.logger.error(f"Stop loss emir hatası: {e}")
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """
        Emri iptal et.

        Parametreler:
        ------------
        order_id : str
            Emir ID

        Returns:
        --------
        bool
            Başarılı mı?
        """
        if order_id not in self.active_orders:
            self.logger.warning(f"Emir bulunamadı: {order_id}")
            return False

        order = self.active_orders[order_id]

        try:
            if self.config['enable_rate_limiting'] and self.rate_limiter:
                await self.rate_limiter.acquire()

            # Binance'den iptal et
            await self._cancel_binance_order(order.symbol, order.binance_order_id)

            # Durumu güncelle
            order.status = OrderStatus.CANCELLED
            del self.active_orders[order_id]

            self.total_orders_cancelled += 1

            self.logger.info(f"Emir iptal edildi: {order_id} | {order.symbol}")
            return True

        except Exception as e:
            self.logger.error(f"Emir iptal hatası: {e}")
            return False

    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """
        Tüm emirleri iptal et.

        Parametreler:
        ------------
        symbol : Optional[str]
            Sembol filtresi (None = hepsi)

        Returns:
        --------
        int
            İptal edilen emir sayısı
        """
        orders_to_cancel = list(self.active_orders.values())

        if symbol:
            orders_to_cancel = [o for o in orders_to_cancel if o.symbol == symbol]

        cancelled_count = 0
        for order in orders_to_cancel:
            success = await self.cancel_order(order.order_id)
            if success:
                cancelled_count += 1

        self.logger.info(f"Toplu iptal: {cancelled_count} emir iptal edildi")
        return cancelled_count

    async def get_order_status(self, order_id: str) -> Optional[Order]:
        """
        Emir durumunu sorgula.

        Parametreler:
        ------------
        order_id : str
            Emir ID

        Returns:
        --------
        Optional[Order]
            Güncel emir durumu
        """
        if order_id not in self.active_orders:
            return None

        order = self.active_orders[order_id]

        try:
            # Binance'den sorgula
            response = await self._query_binance_order(order.symbol, order.binance_order_id)

            # Durumu güncelle
            self._update_order_from_response(order, response)

            # Eğer kapandıysa aktif listeden kaldır
            if order.is_closed():
                del self.active_orders[order_id]
                if order.is_filled():
                    self.total_orders_filled += 1

            return order

        except Exception as e:
            self.logger.error(f"Emir durum sorgu hatası: {e}")
            return None

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Aktif emirleri getir."""
        orders = list(self.active_orders.values())
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders

    def get_statistics(self) -> Dict[str, Any]:
        """İstatistikleri getir."""
        return {
            'total_submitted': self.total_orders_submitted,
            'total_filled': self.total_orders_filled,
            'total_cancelled': self.total_orders_cancelled,
            'total_rejected': self.total_orders_rejected,
            'active_orders': len(self.active_orders),
            'fill_rate': (self.total_orders_filled / self.total_orders_submitted * 100
                         if self.total_orders_submitted > 0 else 0)
        }

    async def _send_to_binance_futures(self, **params) -> Dict:
        """
        Binance Futures API'ye emir gönder.

        # TODO: Faz 6'da BinanceManager entegrasyonu
        """
        # Şimdilik mock response
        self.logger.debug(f"Binance'e gönderiliyor: {params}")

        # Mock response
        return {
            'orderId': 12345678,
            'symbol': params['symbol'],
            'status': 'FILLED' if params['order_type'] == 'MARKET' else 'NEW',
            'executedQty': params['quantity'] if params['order_type'] == 'MARKET' else '0',
            'avgPrice': params.get('price', 50000),
            'updateTime': int(datetime.now(timezone.utc).timestamp() * 1000)
        }

    async def _cancel_binance_order(self, symbol: str, order_id: int) -> Dict:
        """Binance'den emir iptal et."""
        # TODO: Faz 6'da BinanceManager entegrasyonu
        self.logger.debug(f"Binance iptal: {symbol}, {order_id}")
        return {'orderId': order_id, 'status': 'CANCELED'}

    async def _query_binance_order(self, symbol: str, order_id: int) -> Dict:
        """Binance'den emir durumu sorgula."""
        # TODO: Faz 6'da BinanceManager entegrasyonu
        self.logger.debug(f"Binance sorgu: {symbol}, {order_id}")
        return {
            'orderId': order_id,
            'symbol': symbol,
            'status': 'FILLED',
            'executedQty': '0.1',
            'avgPrice': '50000'
        }

    def _update_order_from_response(self, order: Order, response: Dict) -> None:
        """Binance response'u ile emri güncelle."""
        order.binance_order_id = response.get('orderId')

        # Status mapping
        binance_status = response.get('status', 'NEW')
        status_map = {
            'NEW': OrderStatus.SUBMITTED,
            'PARTIALLY_FILLED': OrderStatus.PARTIALLY_FILLED,
            'FILLED': OrderStatus.FILLED,
            'CANCELED': OrderStatus.CANCELLED,
            'REJECTED': OrderStatus.REJECTED,
            'EXPIRED': OrderStatus.EXPIRED
        }
        order.status = status_map.get(binance_status, OrderStatus.SUBMITTED)

        # Filled quantity
        executed_qty = float(response.get('executedQty', 0))
        if executed_qty > 0:
            order.filled_quantity = executed_qty
            order.average_price = float(response.get('avgPrice', 0))

            if order.status == OrderStatus.FILLED:
                order.filled_at = datetime.now(timezone.utc)


if __name__ == "__main__":
    print("Order Executor - Test")
    print("=" * 60)

    async def test_order_executor():
        """Test fonksiyonu."""
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)

        # Mock BinanceManager
        class MockBinanceManager:
            pass

        binance = MockBinanceManager()
        executor = OrderExecutor(binance_manager=binance, logger=logger)
        print("✅ OrderExecutor oluşturuldu")

        # Test 1: Market order
        print("\n📊 Test 1: Market Order")
        order = await executor.submit_market_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=0.1
        )
        print(f"   Order ID: {order.order_id}")
        print(f"   Status: {order.status.value}")
        print(f"   Filled: {order.get_fill_percentage():.1f}%")

        # Test 2: Limit order
        print("\n📊 Test 2: Limit Order")
        order2 = await executor.submit_limit_order(
            symbol="ETHUSDT",
            side=OrderSide.BUY,
            quantity=1.0,
            price=3000.0,
            post_only=True
        )
        print(f"   Order ID: {order2.order_id}")
        print(f"   Price: ${order2.price:.2f}")
        print(f"   TIF: {order2.time_in_force.value}")

        # Test 3: Statistics
        print("\n📊 Test 3: Statistics")
        stats = executor.get_statistics()
        print(f"   Total Submitted: {stats['total_submitted']}")
        print(f"   Total Filled: {stats['total_filled']}")
        print(f"   Active Orders: {stats['active_orders']}")
        print(f"   Fill Rate: {stats['fill_rate']:.1f}%")

        print("\n" + "=" * 60)
        print("✅ Tüm testler başarılı!")

    asyncio.run(test_order_executor())
