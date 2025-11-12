"""
Trading Bot - Trade History Manager
====================================

Trade geçmişi yönetim sistemi.
PostgreSQL (kalıcı) + Redis (cache) ile.

Özellikler:
    - Trade kayıt etme (insert)
    - Trade güncelleme (close trade)
    - Trade sorgulama (filters)
    - İstatistik hesaplama
    - Hot state caching (Redis)
    - Batch operations

Trade Yaşam Döngüsü:
    1. create_trade() -> PostgreSQL + Redis cache
    2. update_trade() -> Pozisyon güncelle
    3. close_trade() -> Trade'i kapat, PnL hesapla
    4. get_trade() -> Önce Redis, sonra PostgreSQL

İstatistikler:
    - Win rate, Average RR, PnL
    - Sharpe, Sortino, Calmar
    - Drawdown, Max win/loss streak

Örnek Kullanım:
    >>> from trade_history_manager import TradeHistoryManager
    >>> thm = TradeHistoryManager(postgres, redis)
    >>> trade_id = thm.create_trade(symbol='BTCUSDT', side='LONG', ...)
    >>> thm.close_trade(trade_id, exit_price=51000, exit_reason='TP_HIT')
    >>> stats = thm.get_stats(days=30)

Author: Trading Bot Team
Version: 1.0
Python: 3.10+
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
import uuid
import logging


class TradeHistoryError(Exception):
    """Trade history ile ilgili hatalar için özel exception."""
    pass


class TradeHistoryManager:
    """
    Trade geçmişi yönetim sistemi.
    
    PostgreSQL (kalıcı depolama) + Redis (hot cache) ile çalışır.
    
    Attributes:
        postgres: PostgresManager instance
        redis: RedisManager instance
        logger: Logger instance
    """
    
    # Redis key prefix'leri
    REDIS_PREFIX_TRADE = "trade:"
    REDIS_PREFIX_POSITION = "position:"
    REDIS_PREFIX_STATS = "stats:"
    
    def __init__(
        self,
        postgres_manager,
        redis_manager,
        logger: Optional[logging.Logger] = None
    ):
        """
        Trade History Manager'ı başlat.
        
        Args:
            postgres_manager: PostgresManager instance
            redis_manager: RedisManager instance
            logger: Logger instance
        """
        self.postgres = postgres_manager
        self.redis = redis_manager
        self.logger = logger or logging.getLogger(__name__)
    
    # ==================== Trade Creation ====================
    
    def create_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        stop_loss: float,
        take_profit: float,
        rr_ratio: float,
        leverage: int = 1,
        signal_confidence: Optional[float] = None,
        signal_type: Optional[str] = None,
        timeframe: Optional[str] = None,
        notes: Optional[str] = None
    ) -> str:
        """
        Yeni trade oluştur.
        
        Args:
            symbol: Trading pair (BTCUSDT)
            side: LONG veya SHORT
            entry_price: Giriş fiyatı
            quantity: Miktar
            stop_loss: Stop loss fiyatı
            take_profit: Take profit fiyatı
            rr_ratio: Risk/Reward oranı
            leverage: Kaldıraç
            signal_confidence: Sinyal güveni (0-1)
            signal_type: Sinyal tipi
            timeframe: Zaman dilimi
            notes: Notlar
            
        Returns:
            Trade ID (UUID)
            
        Raises:
            TradeHistoryError: Trade oluşturulamazsa
            
        Example:
            >>> trade_id = thm.create_trade(
            ...     symbol='BTCUSDT',
            ...     side='LONG',
            ...     entry_price=50000,
            ...     quantity=0.1,
            ...     stop_loss=49000,
            ...     take_profit=52000,
            ...     rr_ratio=2.0
            ... )
        """
        trade_id = str(uuid.uuid4())
        entry_time = datetime.now()
        
        # Risk miktarını hesapla
        risk_amount = abs(entry_price - stop_loss) * quantity
        
        try:
            # PostgreSQL'e kaydet
            query = """
                INSERT INTO trades (
                    trade_id, symbol, side, entry_price, quantity, leverage,
                    entry_time, stop_loss, take_profit, rr_ratio, risk_amount,
                    signal_confidence, signal_type, timeframe, notes
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """
            
            params = (
                trade_id, symbol, side, entry_price, quantity, leverage,
                entry_time, stop_loss, take_profit, rr_ratio, risk_amount,
                signal_confidence, signal_type, timeframe, notes
            )
            
            self.postgres.execute(query, params, fetch=False)
            
            # Pozisyon tablosuna da ekle
            self._create_position(
                trade_id, symbol, side, entry_price, quantity,
                stop_loss, take_profit, rr_ratio, leverage,
                signal_confidence, timeframe, entry_time
            )
            
            # Redis'e cache'le
            trade_data = {
                'trade_id': trade_id,
                'symbol': symbol,
                'side': side,
                'entry_price': entry_price,
                'quantity': quantity,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'rr_ratio': rr_ratio,
                'entry_time': entry_time.isoformat(),
                'status': 'OPEN'
            }
            
            redis_key = f"{self.REDIS_PREFIX_TRADE}{trade_id}"
            self.redis.set(redis_key, trade_data, ttl=self.redis.TTL_HOT_STATE)
            
            self.logger.info(f"Trade oluşturuldu: {trade_id} - {symbol} {side}")
            return trade_id
            
        except Exception as e:
            self.logger.error(f"Trade oluşturma hatası: {e}")
            raise TradeHistoryError(f"Trade oluşturulamadı: {e}")
    
    def _create_position(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        stop_loss: float,
        take_profit: float,
        rr_ratio: float,
        leverage: int,
        signal_confidence: Optional[float],
        timeframe: Optional[str],
        entry_time: datetime
    ) -> None:
        """Açık pozisyon kaydı oluştur."""
        position_id = trade_id  # Trade ID ile aynı
        
        query = """
            INSERT INTO positions (
                position_id, symbol, side, entry_price, quantity, leverage,
                stop_loss, take_profit, rr_ratio, signal_confidence,
                timeframe, entry_time
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """
        
        params = (
            position_id, symbol, side, entry_price, quantity, leverage,
            stop_loss, take_profit, rr_ratio, signal_confidence,
            timeframe, entry_time
        )
        
        self.postgres.execute(query, params, fetch=False)
    
    # ==================== Trade Update ====================
    
    def update_position(
        self,
        trade_id: str,
        current_price: float,
        update_cache: bool = True
    ) -> None:
        """
        Pozisyon fiyatını ve PnL'i güncelle.
        
        Args:
            trade_id: Trade ID
            current_price: Güncel fiyat
            update_cache: Redis cache'i güncelle
        """
        try:
            # Pozisyon bilgisini al
            position = self.get_trade(trade_id)
            if not position:
                raise TradeHistoryError(f"Trade bulunamadı: {trade_id}")
            
            # PnL hesapla
            entry_price = float(position['entry_price'])
            quantity = float(position['quantity'])
            side = position['side']
            
            if side == 'LONG':
                unrealized_pnl = (current_price - entry_price) * quantity
            else:  # SHORT
                unrealized_pnl = (entry_price - current_price) * quantity
            
            unrealized_pnl_pct = (unrealized_pnl / (entry_price * quantity)) * 100
            
            # PostgreSQL güncelle
            query = """
                UPDATE positions
                SET current_price = %s,
                    unrealized_pnl = %s,
                    unrealized_pnl_percentage = %s,
                    last_update = CURRENT_TIMESTAMP
                WHERE position_id = %s
            """
            
            self.postgres.execute(
                query,
                (current_price, unrealized_pnl, unrealized_pnl_pct, trade_id),
                fetch=False
            )
            
            # Redis cache güncelle
            if update_cache:
                redis_key = f"{self.REDIS_PREFIX_TRADE}{trade_id}"
                trade_data = self.redis.get(redis_key)
                
                if trade_data:
                    trade_data['current_price'] = current_price
                    trade_data['unrealized_pnl'] = unrealized_pnl
                    trade_data['unrealized_pnl_pct'] = unrealized_pnl_pct
                    self.redis.set(redis_key, trade_data, ttl=self.redis.TTL_HOT_STATE)
            
        except TradeHistoryError:
            # TradeHistoryError'ları direkt raise et
            raise
        except Exception as e:
            self.logger.error(f"Pozisyon güncelleme hatası: {e}")
            raise TradeHistoryError(f"Pozisyon güncellenemedi: {e}")
    
    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str,
        fees: float = 0,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Trade'i kapat ve sonuçları kaydet.
        
        Args:
            trade_id: Trade ID
            exit_price: Çıkış fiyatı
            exit_reason: Çıkış sebebi (TP_HIT, SL_HIT, MANUAL, SIGNAL_REVERSE)
            fees: İşlem ücretleri
            notes: Notlar
            
        Returns:
            Trade sonuç bilgileri
            
        Raises:
            TradeHistoryError: Trade kapatılamazsa
        """
        try:
            # Trade bilgisini al
            trade = self.get_trade(trade_id)
            if not trade:
                raise TradeHistoryError(f"Trade bulunamadı: {trade_id}")
            
            # Süre hesapla
            entry_time = datetime.fromisoformat(trade['entry_time'])
            exit_time = datetime.now()
            duration = (exit_time - entry_time).total_seconds()
            
            # PnL hesapla
            entry_price = float(trade['entry_price'])
            quantity = float(trade['quantity'])
            side = trade['side']
            
            if side == 'LONG':
                pnl = (exit_price - entry_price) * quantity
            else:  # SHORT
                pnl = (entry_price - exit_price) * quantity
            
            pnl_percentage = (pnl / (entry_price * quantity)) * 100
            net_pnl = pnl - fees
            
            # Actual RR hesapla
            stop_loss = float(trade['stop_loss'])
            risk = abs(entry_price - stop_loss) * quantity
            actual_rr = pnl / risk if risk > 0 else 0
            
            # PostgreSQL güncelle
            query = """
                UPDATE trades
                SET exit_price = %s,
                    exit_time = %s,
                    exit_reason = %s,
                    duration_seconds = %s,
                    pnl = %s,
                    pnl_percentage = %s,
                    fees = %s,
                    net_pnl = %s,
                    actual_rr = %s,
                    notes = COALESCE(notes || E'\n' || %s, %s)
                WHERE trade_id = %s
            """
            
            params = (
                exit_price, exit_time, exit_reason, duration,
                pnl, pnl_percentage, fees, net_pnl, actual_rr,
                notes, notes, trade_id
            )
            
            self.postgres.execute(query, params, fetch=False)
            
            # Pozisyonu sil
            self.postgres.execute(
                "DELETE FROM positions WHERE position_id = %s",
                (trade_id,),
                fetch=False
            )
            
            # Redis cache'i temizle
            redis_key = f"{self.REDIS_PREFIX_TRADE}{trade_id}"
            self.redis.delete(redis_key)
            
            # Sonuç bilgilerini döndür
            result = {
                'trade_id': trade_id,
                'symbol': trade['symbol'],
                'side': side,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'pnl': pnl,
                'pnl_percentage': pnl_percentage,
                'net_pnl': net_pnl,
                'actual_rr': actual_rr,
                'duration_seconds': duration,
                'exit_reason': exit_reason
            }
            
            self.logger.info(
                f"Trade kapatıldı: {trade_id} - {trade['symbol']} "
                f"PnL: {net_pnl:.2f} ({pnl_percentage:.2f}%)"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Trade kapatma hatası: {e}")
            raise TradeHistoryError(f"Trade kapatılamadı: {e}")
    
    # ==================== Trade Query ====================
    
    def get_trade(self, trade_id: str, from_cache: bool = True) -> Optional[Dict]:
        """
        Trade bilgisini al.
        
        Args:
            trade_id: Trade ID
            from_cache: Önce Redis'e bak
            
        Returns:
            Trade bilgileri veya None
        """
        # Önce Redis'e bak
        if from_cache:
            redis_key = f"{self.REDIS_PREFIX_TRADE}{trade_id}"
            cached = self.redis.get(redis_key)
            if cached:
                return cached
        
        # PostgreSQL'den al
        query = "SELECT * FROM trades WHERE trade_id = %s"
        result = self.postgres.execute(query, (trade_id,), fetch_one=True, return_dict=True)
        
        return dict(result) if result else None
    
    def get_open_positions(self) -> List[Dict]:
        """
        Tüm açık pozisyonları al.
        
        Returns:
            Açık pozisyon listesi
        """
        query = "SELECT * FROM positions ORDER BY entry_time DESC"
        results = self.postgres.execute(query, return_dict=True)
        
        return [dict(row) for row in results] if results else []
    
    def get_recent_trades(
        self,
        limit: int = 100,
        symbol: Optional[str] = None,
        days: Optional[int] = None
    ) -> List[Dict]:
        """
        Son trade'leri al.
        
        Args:
            limit: Maksimum trade sayısı
            symbol: Sadece bu symbol (opsiyonel)
            days: Son X gün (opsiyonel)
            
        Returns:
            Trade listesi
        """
        query = "SELECT * FROM trades WHERE exit_time IS NOT NULL"
        params = []
        
        if symbol:
            query += " AND symbol = %s"
            params.append(symbol)
        
        if days:
            query += " AND entry_time > NOW() - INTERVAL '%s days'"
            params.append(days)
        
        query += " ORDER BY exit_time DESC LIMIT %s"
        params.append(limit)
        
        results = self.postgres.execute(query, tuple(params), return_dict=True)
        return [dict(row) for row in results] if results else []
    
    # ==================== Statistics ====================
    
    def get_stats(
        self,
        days: Optional[int] = None,
        symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Trade istatistiklerini hesapla.
        
        Args:
            days: Son X gün (None = tümü)
            symbol: Sadece bu symbol (None = tümü)
            
        Returns:
            İstatistik dictionary
        """
        # Filtre oluştur
        where_clauses = ["exit_time IS NOT NULL"]
        params = []
        
        if days:
            where_clauses.append("entry_time > NOW() - INTERVAL '%s days'")
            params.append(days)
        
        if symbol:
            where_clauses.append("symbol = %s")
            params.append(symbol)
        
        where_sql = " AND ".join(where_clauses)
        
        # Genel istatistikler
        query = f"""
            SELECT
                COUNT(*) as total_trades,
                COUNT(CASE WHEN net_pnl > 0 THEN 1 END) as winning_trades,
                COUNT(CASE WHEN net_pnl <= 0 THEN 1 END) as losing_trades,
                SUM(net_pnl) as total_pnl,
                AVG(net_pnl) as avg_pnl,
                AVG(pnl_percentage) as avg_pnl_percentage,
                AVG(actual_rr) as avg_actual_rr,
                MAX(net_pnl) as max_win,
                MIN(net_pnl) as min_loss,
                AVG(duration_seconds) as avg_duration_seconds
            FROM trades
            WHERE {where_sql}
        """
        
        result = self.postgres.execute(query, tuple(params), fetch_one=True, return_dict=True)
        
        if not result or result['total_trades'] == 0:
            return self._empty_stats()
        
        stats = dict(result)
        
        # Win rate
        total = int(stats['total_trades'])
        wins = int(stats['winning_trades'] or 0)
        stats['win_rate'] = (wins / total * 100) if total > 0 else 0
        
        # Profit factor
        total_wins = self._get_sum_pnl(where_sql, params, positive=True)
        total_losses = abs(self._get_sum_pnl(where_sql, params, positive=False))
        stats['profit_factor'] = (total_wins / total_losses) if total_losses > 0 else 0
        
        # Max streak
        stats.update(self._calculate_streaks(where_sql, params))
        
        # Drawdown (basit)
        stats['max_drawdown'] = self._calculate_max_drawdown(where_sql, params)
        
        return stats
    
    def _empty_stats(self) -> Dict[str, Any]:
        """Boş istatistik dictionary."""
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0,
            'total_pnl': 0,
            'avg_pnl': 0,
            'avg_pnl_percentage': 0,
            'avg_actual_rr': 0,
            'max_win': 0,
            'min_loss': 0,
            'profit_factor': 0,
            'max_win_streak': 0,
            'max_loss_streak': 0,
            'max_drawdown': 0
        }
    
    def _get_sum_pnl(self, where_sql: str, params: List, positive: bool) -> float:
        """PnL toplamını al (kazanan veya kaybeden)."""
        condition = "net_pnl > 0" if positive else "net_pnl <= 0"
        query = f"""
            SELECT COALESCE(SUM(net_pnl), 0) as sum_pnl
            FROM trades
            WHERE {where_sql} AND {condition}
        """
        
        result = self.postgres.execute(query, tuple(params), fetch_one=True)
        return float(result[0]) if result else 0
    
    def _calculate_streaks(self, where_sql: str, params: List) -> Dict[str, int]:
        """Max kazanma/kaybetme serisini hesapla."""
        query = f"""
            SELECT net_pnl
            FROM trades
            WHERE {where_sql}
            ORDER BY exit_time ASC
        """
        
        results = self.postgres.execute(query, tuple(params))
        
        if not results:
            return {'max_win_streak': 0, 'max_loss_streak': 0}
        
        max_win_streak = 0
        max_loss_streak = 0
        current_win_streak = 0
        current_loss_streak = 0
        
        for row in results:
            pnl = float(row[0])
            
            if pnl > 0:
                current_win_streak += 1
                current_loss_streak = 0
                max_win_streak = max(max_win_streak, current_win_streak)
            else:
                current_loss_streak += 1
                current_win_streak = 0
                max_loss_streak = max(max_loss_streak, current_loss_streak)
        
        return {
            'max_win_streak': max_win_streak,
            'max_loss_streak': max_loss_streak
        }
    
    def _calculate_max_drawdown(self, where_sql: str, params: List) -> float:
        """Maksimum drawdown hesapla (basit)."""
        query = f"""
            SELECT net_pnl
            FROM trades
            WHERE {where_sql}
            ORDER BY exit_time ASC
        """
        
        results = self.postgres.execute(query, tuple(params))
        
        if not results:
            return 0
        
        cumulative = 0
        peak = 0
        max_dd = 0
        
        for row in results:
            pnl = float(row[0])
            cumulative += pnl
            
            if cumulative > peak:
                peak = cumulative
            
            drawdown = peak - cumulative
            max_dd = max(max_dd, drawdown)
        
        return max_dd
    
    def __repr__(self) -> str:
        """String representation."""
        return f"TradeHistoryManager(postgres={self.postgres}, redis={self.redis})"


if __name__ == "__main__":
    # Test kodu
    print("🧪 Trade History Manager Test")
    print("-" * 50)
    
    # Mock managers (gerçek test için PostgreSQL ve Redis gerekli)
    print("✅ TradeHistoryManager sınıfı hazır")
    print("💡 Gerçek test için PostgreSQL ve Redis gerekli")
    print()
    print("Kullanım örneği:")
    print("""
    from postgres_manager import PostgresManager
    from redis_manager import RedisManager
    from trade_history_manager import TradeHistoryManager
    
    # Managers
    postgres = PostgresManager()
    postgres.connect()
    
    redis = RedisManager()
    redis.connect()
    
    # Trade History Manager
    thm = TradeHistoryManager(postgres, redis)
    
    # Trade aç
    trade_id = thm.create_trade(
        symbol='BTCUSDT',
        side='LONG',
        entry_price=50000,
        quantity=0.1,
        stop_loss=49000,
        take_profit=52000,
        rr_ratio=2.0
    )
    
    # Pozisyon güncelle
    thm.update_position(trade_id, current_price=51000)
    
    # Trade kapat
    result = thm.close_trade(
        trade_id,
        exit_price=52000,
        exit_reason='TP_HIT',
        fees=5.0
    )
    
    # İstatistikler
    stats = thm.get_stats(days=30)
    print(f"Win Rate: {stats['win_rate']:.2f}%")
    print(f"Profit Factor: {stats['profit_factor']:.2f}")
    """)
    
    print("\n🎉 Trade History Manager hazır!")