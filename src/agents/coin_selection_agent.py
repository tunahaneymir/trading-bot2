"""
Trading Bot - Coin Selection Agent
===================================

Binance Futures'da en uygun coin'leri otomatik seçen AI agent.

Özellikler:
    - USDT-M Perpetual Futures market tarama
    - Multi-metric filtering ve scoring
    - PostgreSQL + Redis entegrasyonu
    - Fazlı coin sayısı (5→10→20)
    - Market regime aware selection
    - Background update support

Workflow:
    1. Market Scan: Tüm USDT-M Perpetual pairs'i tara
    2. Pre-filter: Likidite ve spread filtresi
    3. Calculate Metrics: ATR, RSI, MACD, ADX vb.
    4. Score Coins: 6 metriğin composite skoru
    5. Select Top N: En iyi N coin seç
    6. Store: PostgreSQL + Redis'e kaydet

Author: Trading Bot Team
Version: 1.0 (Faz 4)
Python: 3.10+
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import time
import json
import numpy as np
from dataclasses import dataclass, asdict

# Core components
from src.core.config_manager import ConfigManager
from src.core.logger import setup_logger
from src.binance.binance_manager import BinanceManager, BinanceError
from src.database.postgres_manager import PostgresManager
from src.database.redis_manager import RedisManager

# Utils
from src.utils.scoring import CoinScorer, CoinScores
from src.utils.filters import CoinFilter, FilterConfig

# Agents
from src.agents.market_regime_detector import MarketRegimeDetector, MarketRegime


@dataclass
class CoinMetrics:
    """Bir coin için hesaplanan tüm metrikler."""
    symbol: str
    
    # Market data
    price: float
    volume_24h: float
    volume_7d_avg: float
    spread: float
    
    # Volatility
    volatility: float  # ATR bazlı
    atr: float
    
    # Trend
    adx: float
    trend_direction: int  # 1, -1, 0
    price_position: float  # 0-1 range içinde pozisyon
    
    # Momentum
    rsi: float
    macd_histogram: float
    price_change_24h: float
    
    # Volume
    volume_trend: str  # 'increasing', 'decreasing', 'stable'
    
    # Orderbook (optional)
    orderbook_depth: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Dictionary'ye çevir."""
        return asdict(self)


class CoinSelectionAgent:
    """
    Otomatik coin seçim agent'ı.
    
    En uygun USDT-M Perpetual Futures coinlerini seçer.
    """
    
    def __init__(
        self,
        config: ConfigManager,
        binance_manager: BinanceManager,
        postgres_manager: PostgresManager,
        redis_manager: RedisManager,
        phase: int = 1
    ):
        """
        Initialize coin selection agent.
        
        Args:
            config: Config manager
            binance_manager: Binance API manager
            postgres_manager: PostgreSQL manager
            redis_manager: Redis manager
            phase: Trading phase (1, 2, 3) for coin count
        """
        self.config = config
        self.binance = binance_manager
        self.postgres = postgres_manager
        self.redis = redis_manager
        self.phase = phase
        
        self.logger = setup_logger('coin_selection')
        
        # Coin sayısı (fazlara göre)
        phase_counts = {
            1: config.get('coin_selection.phase_1_count', 5),
            2: config.get('coin_selection.phase_2_count', 10),
            3: config.get('coin_selection.phase_3_count', 20),
        }
        self.coin_count = phase_counts.get(phase, 5)
        
        # Filter ve scorer oluştur
        filter_config = FilterConfig(
            min_volume_24h=config.get('coin_selection.min_volume', 10_000_000),
            max_spread=config.get('coin_selection.max_spread', 0.002),
            min_volatility=config.get('coin_selection.min_volatility', 0.015),
            max_volatility=config.get('coin_selection.max_volatility', 0.20),
        )
        self.coin_filter = CoinFilter(filter_config)
        
        # Scorer (ağırlıklar config'den)
        weights = config.get('coin_selection.weights', None)
        self.scorer = CoinScorer(weights)
        
        # Market regime detector
        self.regime_detector = MarketRegimeDetector()
        
        # Cache keys
        self.cache_key_selected = "coin_selection:current"
        self.cache_key_scores = "coin_scores:current"
        self.cache_key_regime = "market_regime:current"
        
        # Cache TTL (config'den)
        self.cache_ttl = config.get('coin_selection.update_interval_hours', 4) * 3600
        
        self.logger.info(
            f"CoinSelectionAgent başlatıldı (Phase {phase}, {self.coin_count} coins)",
            extra={'extra_data': {
                'phase': phase,
                'coin_count': self.coin_count,
                'cache_ttl_hours': self.cache_ttl / 3600
            }}
        )
    
    # ==================== MARKET SCANNING ====================
    
    def scan_market(self) -> List[Dict[str, Any]]:
        """
        Tüm USDT-M Perpetual Futures market'i tara.
        
        Returns:
            Coin listesi (basic data ile)
        """
        self.logger.info("Market taraması başlatılıyor...")
        
        try:
            # Exchange info al (tüm symbols)
            exchange_info = self.binance.get_exchange_info()
            
            # USDT-M Perpetual symbols filtrele
            symbols = []
            for symbol_info in exchange_info.get('symbols', []):
                symbol = symbol_info.get('symbol')
                contract_type = symbol_info.get('contractType')
                status = symbol_info.get('status')
                
                # USDT-M Perpetual ve TRADING durumunda olanlar
                if (symbol and symbol.endswith('USDT') and 
                    contract_type == 'PERPETUAL' and 
                    status == 'TRADING'):
                    symbols.append(symbol)
            
            self.logger.info(f"Toplam {len(symbols)} USDT-M Perpetual coin bulundu")
            
            # 24h ticker data al (hacim, fiyat vb)
            tickers = []
            try:
                # Tüm tickers'ı tek seferde al
                all_tickers = self.binance.client.futures_ticker()
                
                # Symbol lookup için dict oluştur
                ticker_dict = {t['symbol']: t for t in all_tickers if isinstance(t, dict)}
                
                for symbol in symbols:
                    if symbol in ticker_dict:
                        ticker = ticker_dict[symbol]
                        
                        # Basic data
                        coin_data = {
                            'symbol': symbol,
                            'price': float(ticker.get('lastPrice', 0)),
                            'volume_24h': float(ticker.get('quoteVolume', 0)),
                            'price_change_24h': float(ticker.get('priceChangePercent', 0)),
                            'spread': 0.0,  # Dummy value - gerçek spread sonra hesaplanacak
                        }
                        
                        tickers.append(coin_data)
                
                self.logger.info(f"{len(tickers)} coin için ticker data alındı")
                
            except Exception as e:
                self.logger.error(f"Ticker data alma hatası: {e}")
                return []
            
            return tickers
            
        except BinanceError as e:
            self.logger.error(f"Market scan hatası: {e}")
            return []
    
    def get_orderbook_spread(self, symbol: str) -> Optional[float]:
        """
        Orderbook'tan spread hesapla.
        
        Args:
            symbol: Coin symbol
            
        Returns:
            Spread (yüzde) veya None
        """
        try:
            orderbook = self.binance.get_order_book(symbol, limit=5)
            
            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])
            
            if bids and asks:
                best_bid = float(bids[0][0])
                best_ask = float(asks[0][0])
                
                if best_bid > 0:
                    spread = (best_ask - best_bid) / best_bid * 100  # Yüzde
                    return spread
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Spread hesaplama hatası ({symbol}): {e}")
            return None
    
    # ==================== METRICS CALCULATION ====================
    
    def calculate_atr(self, symbol: str, period: int = 14) -> Optional[float]:
        """
        ATR (Average True Range) hesapla.
        
        Args:
            symbol: Coin symbol
            period: ATR periyodu
            
        Returns:
            ATR değeri veya None
        """
        try:
            # Kline data al (1 günlük, son 20 gün)
            klines = self.binance.get_klines(
                symbol=symbol,
                interval='1d',
                limit=period + 5
            )
            
            if len(klines) < period + 1:
                return None
            
            # True range hesapla
            true_ranges = []
            for i in range(1, len(klines)):
                high = float(klines[i][2])
                low = float(klines[i][3])
                prev_close = float(klines[i-1][4])
                
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(prev_close - low)
                )
                true_ranges.append(tr)
            
            # ATR = TR ortalaması
            atr = np.mean(true_ranges[-period:])
            
            return atr
            
        except Exception as e:
            self.logger.debug(f"ATR hesaplama hatası ({symbol}): {e}")
            return None
    
    def calculate_technical_indicators(
        self,
        symbol: str
    ) -> Dict[str, Any]:
        """
        Teknik indikatörleri hesapla (RSI, MACD, ADX vb).
        
        Args:
            symbol: Coin symbol
            
        Returns:
            İndikatör dictionary
        """
        try:
            # Kline data al (4 saatlik, son 100 bar)
            klines = self.binance.get_klines(
                symbol=symbol,
                interval='4h',
                limit=100
            )
            
            if len(klines) < 50:
                return {}
            
            # Close prices
            closes = [float(k[4]) for k in klines]
            highs = [float(k[2]) for k in klines]
            lows = [float(k[3]) for k in klines]
            
            indicators = {}
            
            # RSI hesapla (14 periyot)
            rsi = self._calculate_rsi(closes, 14)
            if rsi:
                indicators['rsi'] = rsi
            
            # MACD hesapla
            macd_line, signal_line, histogram = self._calculate_macd(closes)
            if histogram is not None:
                indicators['macd_histogram'] = histogram
            
            # ADX hesapla (14 periyot)
            adx = self._calculate_adx(highs, lows, closes, 14)
            if adx:
                indicators['adx'] = adx
            
            # Trend direction (basit)
            ma20 = np.mean(closes[-20:])
            ma50 = np.mean(closes[-50:])
            current_price = closes[-1]
            
            if current_price > ma20 > ma50:
                indicators['trend_direction'] = 1  # Uptrend
            elif current_price < ma20 < ma50:
                indicators['trend_direction'] = -1  # Downtrend
            else:
                indicators['trend_direction'] = 0  # Sideways
            
            # Price position (range içinde)
            recent_high = max(highs[-20:])
            recent_low = min(lows[-20:])
            if recent_high > recent_low:
                indicators['price_position'] = (current_price - recent_low) / (recent_high - recent_low)
            else:
                indicators['price_position'] = 0.5
            
            return indicators
            
        except Exception as e:
            self.logger.debug(f"İndikatör hesaplama hatası ({symbol}): {e}")
            return {}
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> Optional[float]:
        """RSI hesapla."""
        if len(prices) < period + 1:
            return None
        
        # Fiyat değişimleri
        deltas = np.diff(prices)
        
        # Gains ve losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        # Average gains ve losses
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_macd(
        self,
        prices: List[float],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """MACD hesapla."""
        if len(prices) < slow + signal:
            return None, None, None
        
        # EMA hesapla
        ema_fast = self._calculate_ema(prices, fast)
        ema_slow = self._calculate_ema(prices, slow)
        
        if ema_fast is None or ema_slow is None:
            return None, None, None
        
        # MACD line
        macd_line = ema_fast - ema_slow
        
        # Signal line (MACD'nin EMA'sı)
        # Basitleştirilmiş: sadece son değer
        signal_line = macd_line * 0.8  # Approximation
        
        # Histogram
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    def _calculate_ema(self, prices: List[float], period: int) -> Optional[float]:
        """EMA hesapla."""
        if len(prices) < period:
            return None
        
        multiplier = 2 / (period + 1)
        ema = np.mean(prices[:period])  # İlk EMA = SMA
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def _calculate_adx(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int = 14
    ) -> Optional[float]:
        """ADX hesapla (basitleştirilmiş)."""
        if len(highs) < period + 1:
            return None
        
        # +DM ve -DM hesapla
        plus_dm = []
        minus_dm = []
        
        for i in range(1, len(highs)):
            high_diff = highs[i] - highs[i-1]
            low_diff = lows[i-1] - lows[i]
            
            if high_diff > low_diff and high_diff > 0:
                plus_dm.append(high_diff)
                minus_dm.append(0)
            elif low_diff > high_diff and low_diff > 0:
                plus_dm.append(0)
                minus_dm.append(low_diff)
            else:
                plus_dm.append(0)
                minus_dm.append(0)
        
        # ATR hesapla
        true_ranges = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            true_ranges.append(tr)
        
        atr = np.mean(true_ranges[-period:])
        
        if atr == 0:
            return 0
        
        # +DI ve -DI
        plus_di = (np.mean(plus_dm[-period:]) / atr) * 100
        minus_di = (np.mean(minus_dm[-period:]) / atr) * 100
        
        # DX
        di_sum = plus_di + minus_di
        if di_sum == 0:
            return 0
        
        dx = abs(plus_di - minus_di) / di_sum * 100
        
        # ADX (DX'in ortalaması - basitleştirilmiş)
        adx = dx  # Gerçekte DX'in EMA'sı alınır
        
        return adx
    
    def calculate_volume_metrics(self, symbol: str) -> Dict[str, Any]:
        """
        Hacim metriklerini hesapla.
        
        Args:
            symbol: Coin symbol
            
        Returns:
            Volume metrikleri
        """
        try:
            # Son 7 günlük kline data
            klines = self.binance.get_klines(
                symbol=symbol,
                interval='1d',
                limit=7
            )
            
            if len(klines) < 7:
                return {}
            
            volumes = [float(k[7]) for k in klines]  # Quote volume
            
            # 7 günlük ortalama
            volume_7d_avg = np.mean(volumes)
            
            # Volume trend
            first_half = volumes[:3]
            second_half = volumes[-3:]
            
            first_avg = np.mean(first_half)
            second_avg = np.mean(second_half)
            
            if first_avg > 0:
                change = (second_avg - first_avg) / first_avg
                if change > 0.15:
                    volume_trend = 'increasing'
                elif change < -0.15:
                    volume_trend = 'decreasing'
                else:
                    volume_trend = 'stable'
            else:
                volume_trend = 'stable'
            
            return {
                'volume_7d_avg': volume_7d_avg,
                'volume_trend': volume_trend
            }
            
        except Exception as e:
            self.logger.debug(f"Volume metrik hatası ({symbol}): {e}")
            return {}
    
    def calculate_coin_metrics(self, coin_data: Dict[str, Any]) -> Optional[CoinMetrics]:
        """
        Bir coin için tüm metrikleri hesapla.
        
        Args:
            coin_data: Basic coin data
            
        Returns:
            CoinMetrics object veya None
        """
        symbol = coin_data['symbol']
        
        try:
            # Spread hesapla
            spread = self.get_orderbook_spread(symbol)
            if spread is None:
                spread = 0.1  # Default
            
            # ATR hesapla
            atr = self.calculate_atr(symbol)
            if atr is None:
                return None  # ATR olmadan devam edemeyiz
            
            # Volatility (ATR / price)
            price = coin_data['price']
            volatility = (atr / price) if price > 0 else 0
            
            # Technical indicators
            indicators = self.calculate_technical_indicators(symbol)
            if not indicators:
                return None
            
            # Volume metrics
            volume_metrics = self.calculate_volume_metrics(symbol)
            
            # CoinMetrics oluştur
            metrics = CoinMetrics(
                symbol=symbol,
                price=price,
                volume_24h=coin_data['volume_24h'],
                volume_7d_avg=volume_metrics.get('volume_7d_avg', coin_data['volume_24h']),
                spread=spread,
                volatility=volatility,
                atr=atr,
                adx=indicators.get('adx', 25),
                trend_direction=indicators.get('trend_direction', 0),
                price_position=indicators.get('price_position', 0.5),
                rsi=indicators.get('rsi', 50),
                macd_histogram=indicators.get('macd_histogram', 0),
                price_change_24h=coin_data['price_change_24h'],
                volume_trend=volume_metrics.get('volume_trend', 'stable'),
            )
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Metrik hesaplama hatası ({symbol}): {e}")
            return None
    
    # ==================== COIN SELECTION ====================
    
    def select_coins(self, force_update: bool = False) -> List[str]:
        """
        En iyi coin'leri seç.
        
        Ana selection metodu. Cache'i kontrol eder, gerekirse yeniler.
        
        Args:
            force_update: Cache'i yok sayıp yeniden hesapla
            
        Returns:
            Seçili coin sembolleri
        """
        # Cache'den kontrol et
        if not force_update:
            cached = self.get_selected_coins_from_cache()
            if cached:
                self.logger.info(f"Cache'den {len(cached)} coin alındı")
                return cached
        
        self.logger.info("Yeni coin selection başlatılıyor...")
        start_time = time.time()
        
        # 1. Market'i tara
        all_coins = self.scan_market()
        if not all_coins:
            self.logger.error("Market scan başarısız")
            return []
        
        self.logger.info(f"Step 1/6: {len(all_coins)} coin tarandı")
        
        # 2. Pre-filter (volume + spread)
        filtered_coins = self.coin_filter.filter_by_volume(all_coins)
        filtered_coins = self.coin_filter.filter_by_spread(filtered_coins)
        
        self.logger.info(f"Step 2/6: {len(filtered_coins)} coin pre-filter'dan geçti")
        
        if len(filtered_coins) == 0:
            self.logger.error("Pre-filter sonrası coin kalmadı")
            return []
        
        # 3. Metrikleri hesapla (paralel değil, sıralı - rate limit için)
        coins_with_metrics = []
        total = len(filtered_coins)
        
        for idx, coin in enumerate(filtered_coins, 1):
            if idx % 10 == 0:
                self.logger.info(f"Step 3/6: Metrikler hesaplanıyor... ({idx}/{total})")
            
            metrics = self.calculate_coin_metrics(coin)
            if metrics:
                coins_with_metrics.append(metrics)
            
            # Rate limiting
            time.sleep(0.1)  # 100ms delay
        
        self.logger.info(f"Step 3/6: {len(coins_with_metrics)} coin için metrikler hesaplandı")
        
        if len(coins_with_metrics) == 0:
            self.logger.error("Metrik hesaplama sonrası coin kalmadı")
            return []
        
        # 4. Post-filter (volatility, technical)
        metrics_dicts = [m.to_dict() for m in coins_with_metrics]
        filtered_metrics = self.coin_filter.apply_all_filters(metrics_dicts)
        
        self.logger.info(f"Step 4/6: {len(filtered_metrics)} coin tüm filtreleri geçti")
        
        if len(filtered_metrics) == 0:
            self.logger.error("Post-filter sonrası coin kalmadı")
            return []
        
        # 5. Skorla
        coin_scores = []
        for metrics_dict in filtered_metrics:
            scores = self.scorer.score_coin(
                metrics_dict['symbol'],
                metrics_dict,
                correlations=[]  # TODO: Korelasyon hesapla
            )
            coin_scores.append(scores)
        
        self.logger.info(f"Step 5/6: {len(coin_scores)} coin skorlandı")
        
        # 6. Top N seç
        coin_scores.sort(key=lambda x: x.final_score, reverse=True)
        top_coins = coin_scores[:self.coin_count]
        selected_symbols = [c.symbol for c in top_coins]
        
        self.logger.info(f"Step 6/6: Top {len(selected_symbols)} coin seçildi")
        
        # Sonuçları kaydet
        self.save_selection_results(top_coins)
        
        duration = time.time() - start_time
        self.logger.info(
            f"Coin selection tamamlandı ({duration:.2f}s)",
            extra={'extra_data': {
                'duration_seconds': round(duration, 2),
                'total_scanned': len(all_coins),
                'selected_count': len(selected_symbols),
                'phase': self.phase
            }}
        )
        
        return selected_symbols
    
    #==================== STORAGE ====================
    
    def save_selection_results(self, coin_scores: List[CoinScores]) -> None:
        """
        Selection sonuçlarını kaydet (PostgreSQL + Redis).
        
        Args:
            coin_scores: Skorlanmış coinler
        """
        timestamp = datetime.now()
        
        # PostgreSQL'e kaydet
        try:
            for rank, scores in enumerate(coin_scores, 1):
                query = """
                    INSERT INTO coin_selections (
                        symbol, score, rank,
                        liquidity_score, volatility_score, trend_strength_score,
                        momentum_score, volume_profile_score, correlation_score,
                        selected_at, phase
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """
                params = (
                    scores.symbol,
                    scores.final_score,
                    rank,
                    scores.liquidity_score,
                    scores.volatility_score,
                    scores.trend_strength_score,
                    scores.momentum_score,
                    scores.volume_profile_score,
                    scores.correlation_score,
                    timestamp,
                    self.phase
                )
                
                self.postgres.execute(query, params, fetch=False)
            
            self.logger.info(f"{len(coin_scores)} coin PostgreSQL'e kaydedildi")
            
        except Exception as e:
            self.logger.error(f"PostgreSQL kayıt hatası: {e}")
        
        # Redis'e kaydet
        try:
            # Selected symbols
            symbols = [c.symbol for c in coin_scores]
            self.redis.set(
                self.cache_key_selected,
                json.dumps(symbols),
                ttl=self.cache_ttl
            )
            
            # Scores
            scores_dict = {c.symbol: c.to_dict() for c in coin_scores}
            self.redis.set(
                self.cache_key_scores,
                json.dumps(scores_dict),
                ttl=self.cache_ttl
            )
            
            self.logger.info("Selection sonuçları Redis'e cache'lendi")
            
        except Exception as e:
            self.logger.error(f"Redis cache hatası: {e}")
    
    def get_selected_coins_from_cache(self) -> Optional[List[str]]:
        """
        Cache'den seçili coinleri al.
        
        Returns:
            Coin sembolleri veya None
        """
        try:
            cached = self.redis.get(self.cache_key_selected)
            if cached:
                symbols = json.loads(cached) if isinstance(cached, str) else cached
                return symbols
            return None
        except Exception as e:
            self.logger.debug(f"Cache okuma hatası: {e}")
            return None
    
    def get_coin_scores_from_cache(self) -> Optional[Dict[str, Dict]]:
        """
        Cache'den coin skorlarını al.
        
        Returns:
            Skor dictionary veya None
        """
        try:
            cached = self.redis.get(self.cache_key_scores)
            if cached:
                scores = json.loads(cached) if isinstance(cached, str) else cached
                return scores
            return None
        except Exception as e:
            self.logger.debug(f"Cache okuma hatası: {e}")
            return None
    
    # ==================== PUBLIC API ====================
    
    def get_selected_coins(self, use_cache: bool = True) -> List[str]:
        """
        Seçili coinleri al.
        
        Args:
            use_cache: Cache kullan
            
        Returns:
            Coin sembolleri
        """
        if use_cache:
            cached = self.get_selected_coins_from_cache()
            if cached:
                return cached
        
        # Cache'de yok, yeni selection yap
        return self.select_coins(force_update=True)
    
    def update_selection(self) -> List[str]:
        """
        Selection'ı güncelle (force update).
        
        Returns:
            Yeni seçili coinler
        """
        return self.select_coins(force_update=True)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Agent istatistikleri.
        
        Returns:
            İstatistik dictionary
        """
        stats = {
            'phase': self.phase,
            'target_coin_count': self.coin_count,
            'cache_ttl_hours': self.cache_ttl / 3600,
            'filter_stats': self.coin_filter.get_statistics(),
        }
        
        # Cache durumu
        cached_coins = self.get_selected_coins_from_cache()
        if cached_coins:
            stats['cached_coins'] = len(cached_coins)
            stats['cache_valid'] = True
        else:
            stats['cache_valid'] = False
        
        return stats
    
    def __repr__(self) -> str:
        """String representation."""
        return f"CoinSelectionAgent(phase={self.phase}, coins={self.coin_count})"


if __name__ == "__main__":
    print("🧪 Coin Selection Agent Test")
    print("-" * 50)
    print("💡 Gerçek test için demo_faz4.py kullanın")
    print("✅ Agent class hazır!")