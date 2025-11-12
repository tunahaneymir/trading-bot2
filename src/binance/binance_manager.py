"""
Trading Bot - Binance Manager (python-binance wrapper)
=======================================================

python-binance kütüphanesini wrapper olarak kullanır.
Daha stabil ve Binance API ile tam uyumlu.

Author: Trading Bot Team
Version: 1.1 (python-binance wrapper)
"""

from typing import Optional, Dict, Any, List, Literal
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException

from src.core.config_manager import ConfigManager
from src.core.logger import setup_logger
from src.binance.rate_limiter import RateLimiter


class BinanceError(Exception):
    """Binance API ile ilgili hatalar için özel exception."""
    
    def __init__(self, message: str, code: Optional[int] = None, response: Optional[Dict] = None):
        super().__init__(message)
        self.code = code
        self.response = response


class BinanceManager:
    """
    Binance Futures API yöneticisi (python-binance wrapper).
    
    python-binance kütüphanesini kullanarak Binance API'ye bağlanır.
    Daha stabil ve tam uyumlu.
    """
    
    def __init__(
        self,
        config: Optional[ConfigManager] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: bool = True
    ):
        """
        Initialize Binance manager.
        
        Args:
            config: ConfigManager instance
            api_key: API key
            api_secret: API secret
            testnet: Testnet kullan
        """
        self.logger = setup_logger('binance')
        
        # Önce .env'den dene (en güvenilir)
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        env_api_key = os.getenv('CONFIG_BINANCE_API_KEY')
        env_api_secret = os.getenv('CONFIG_BINANCE_API_SECRET')
        env_testnet = os.getenv('CONFIG_BINANCE_TESTNET', 'true').lower() == 'true'
        
        # Config'den al (eğer env'de yoksa)
        if config:
            self.config = config
            self.api_key = env_api_key or config.get('binance.api_key', api_key)
            self.api_secret = env_api_secret or config.get('binance.api_secret', api_secret)
            self.testnet = env_testnet if env_api_key else config.get('binance.testnet', testnet)
            rate_limit = config.get('binance.rate_limit', 1200)
        else:
            self.config = None
            self.api_key = env_api_key or api_key
            self.api_secret = env_api_secret or api_secret
            self.testnet = env_testnet if env_api_key else testnet
            rate_limit = 1200
        
        # API key'leri temizle
        if self.api_key:
            self.api_key = self.api_key.strip()
        if self.api_secret:
            self.api_secret = self.api_secret.strip()
        
        # Validasyon
        if not self.api_key or not self.api_secret:
            raise BinanceError("API key ve secret gerekli")
        
        # python-binance client
        try:
            self.client = Client(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet
            )
        except Exception as e:
            raise BinanceError(f"Client oluşturulamadı: {e}")
        
        # Rate limiter
        self.rate_limiter = RateLimiter(max_weight_per_minute=rate_limit)
        
        # Base URL (bilgi amaçlı)
        self.base_url = "https://testnet.binancefuture.com" if self.testnet else "https://fapi.binance.com"
        
        # Connection durumu
        self._connected = False
        
        self.logger.info(
            f"BinanceManager başlatıldı (python-binance wrapper)",
            extra={'extra_data': {
                'testnet': self.testnet,
                'base_url': self.base_url
            }}
        )
    
    def connect(self) -> bool:
        """
        Binance API'ye bağlan ve test et.
        
        Returns:
            Bağlantı başarılı ise True
        """
        try:
            # Server time test
            server_time = self.client.get_server_time()
            
            # Account test
            account = self.client.futures_account()
            
            self._connected = True
            
            self.logger.info(
                "Binance API bağlantısı başarılı",
                extra={'extra_data': {
                    'server_time': server_time.get('serverTime'),
                    'testnet': self.testnet
                }}
            )
            
            return True
            
        except BinanceAPIException as e:
            self._connected = False
            raise BinanceError(f"Binance API hatası: {e.message}", code=e.code)
        except Exception as e:
            self._connected = False
            raise BinanceError(f"Bağlantı hatası: {e}")
    
    def is_connected(self) -> bool:
        """Bağlantı durumu."""
        return self._connected
    
    # ==================== MARKET DATA ====================
    
    def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> List[List]:
        """Candlestick data al."""
        try:
            return self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                limit=min(limit, 1500),
                startTime=start_time,
                endTime=end_time
            )
        except BinanceAPIException as e:
            raise BinanceError(f"Klines hatası: {e.message}", code=e.code)
    
    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """24h ticker bilgisi al."""
        try:
            return self.client.futures_ticker(symbol=symbol)
        except BinanceAPIException as e:
            raise BinanceError(f"Ticker hatası: {e.message}", code=e.code)
    
    def get_ticker_price(self, symbol: str) -> Dict[str, Any]:
        """Güncel fiyat al."""
        try:
            return self.client.futures_symbol_ticker(symbol=symbol)
        except BinanceAPIException as e:
            raise BinanceError(f"Ticker price hatası: {e.message}", code=e.code)
    
    def get_order_book(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """Order book al."""
        try:
            return self.client.futures_order_book(symbol=symbol, limit=limit)
        except BinanceAPIException as e:
            raise BinanceError(f"Order book hatası: {e.message}", code=e.code)
    
    def get_mark_price(self, symbol: str) -> Dict[str, Any]:
        """Mark price ve funding rate al."""
        try:
            return self.client.futures_mark_price(symbol=symbol)
        except BinanceAPIException as e:
            raise BinanceError(f"Mark price hatası: {e.message}", code=e.code)
    
    def get_funding_rate(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Funding rate history al."""
        try:
            return self.client.futures_funding_rate(symbol=symbol, limit=min(limit, 1000))
        except BinanceAPIException as e:
            raise BinanceError(f"Funding rate hatası: {e.message}", code=e.code)
    
    # ==================== ACCOUNT ====================
    
    def get_balance(self) -> List[Dict[str, Any]]:
        """Account balance al."""
        try:
            account = self.client.futures_account()
            return account.get('assets', [])
        except BinanceAPIException as e:
            raise BinanceError(f"Balance hatası: {e.message}", code=e.code)
    
    def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Pozisyonları al."""
        try:
            positions = self.client.futures_position_information(symbol=symbol)
            return positions if positions else []
        except BinanceAPIException as e:
            raise BinanceError(f"Positions hatası: {e.message}", code=e.code)
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Açık emirleri al."""
        try:
            return self.client.futures_get_open_orders(symbol=symbol)
        except BinanceAPIException as e:
            raise BinanceError(f"Open orders hatası: {e.message}", code=e.code)
    
    # ==================== TRADING ====================
    
    def place_order(
        self,
        symbol: str,
        side: Literal['BUY', 'SELL'],
        order_type: Literal['MARKET', 'LIMIT', 'STOP_MARKET', 'STOP_LIMIT', 'TAKE_PROFIT_MARKET'],
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: Literal['GTC', 'IOC', 'FOK'] = 'GTC',
        reduce_only: bool = False,
        close_position: bool = False
    ) -> Dict[str, Any]:
        """Emir ver."""
        try:
            params = {
                'symbol': symbol,
                'side': side,
                'type': order_type
            }
            
            if quantity:
                params['quantity'] = quantity
            if price:
                params['price'] = price
            if stop_price:
                params['stopPrice'] = stop_price
            if order_type == 'LIMIT':
                params['timeInForce'] = time_in_force
            if reduce_only:
                params['reduceOnly'] = 'true'
            if close_position:
                params['closePosition'] = 'true'
            
            self.logger.info(
                f"Emir veriliyor: {side} {quantity} {symbol} @ {order_type}",
                extra={'extra_data': params}
            )
            
            return self.client.futures_create_order(**params)
            
        except BinanceAPIException as e:
            raise BinanceError(f"Order hatası: {e.message}", code=e.code)
    
    def cancel_order(self, symbol: str, order_id: Optional[int] = None, client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """Emri iptal et."""
        try:
            if order_id:
                return self.client.futures_cancel_order(symbol=symbol, orderId=order_id)
            elif client_order_id:
                return self.client.futures_cancel_order(symbol=symbol, origClientOrderId=client_order_id)
            else:
                raise BinanceError("order_id veya client_order_id gerekli")
        except BinanceAPIException as e:
            raise BinanceError(f"Cancel hatası: {e.message}", code=e.code)
    
    def cancel_all_orders(self, symbol: str) -> Dict[str, Any]:
        """Tüm emirleri iptal et."""
        try:
            return self.client.futures_cancel_all_open_orders(symbol=symbol)
        except BinanceAPIException as e:
            raise BinanceError(f"Cancel all hatası: {e.message}", code=e.code)
    
    # ==================== UTILITY ====================
    
    def get_exchange_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Exchange bilgisi al."""
        try:
            return self.client.futures_exchange_info()
        except BinanceAPIException as e:
            raise BinanceError(f"Exchange info hatası: {e.message}", code=e.code)
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Rate limiter durumu."""
        return self.rate_limiter.get_statistics()
    
    def close(self) -> None:
        """Manager'ı kapat."""
        self._connected = False
        self.logger.info("BinanceManager kapatıldı")
    
    def __enter__(self):
        """Context manager."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"BinanceManager(testnet={self.testnet}, "
            f"connected={self._connected}, wrapper=python-binance)"
        )


if __name__ == "__main__":
    print("🧪 BinanceManager (python-binance wrapper) Test")
    print("-" * 70)
    
    try:
        from pathlib import Path
        import os
        
        config = ConfigManager()
        config.set('binance.api_key', os.getenv('CONFIG_BINANCE_API_KEY', 'test'))
        config.set('binance.api_secret', os.getenv('CONFIG_BINANCE_API_SECRET', 'test'))
        config.set('binance.testnet', True)
        
        manager = BinanceManager(config)
        print(f"✅ Manager oluşturuldu: {manager}")
        
        print("\n🎉 Wrapper başarıyla oluşturuldu!")
        print("💡 Gerçek testler için quick_test.py veya demo_faz3.py kullanın")
        
    except Exception as e:
        print(f"❌ Test hatası: {e}")