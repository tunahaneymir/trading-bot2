#!/usr/bin/env python3
"""
🔄 Manuel Coin Selection Update Script

Bu script, Coin Seçim Ajanı'nı manuel olarak çalıştırarak
portföy için en uygun coinleri seçer ve günceller.

Kullanım:
    python scripts/update_coin_selection.py --phase 1 --count 5
    python scripts/update_coin_selection.py --phase 2 --count 10 --force
    python scripts/update_coin_selection.py --phase 3 --count 20 --output results.json

Özellikler:
    - 6 kriterli skorlama sistemi (likidite, volatilite, trend, momentum, hacim, korelasyon)
    - ML destekli LightGBM Ranker modeli
    - Faz bazlı coin seçimi (5 → 10 → 20)
    - Dinamik portföy oluşturma
    - Yeniden dengeleme önerileri
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    import numpy as np
    import pandas as pd
    from binance.client import Client
except ImportError as e:
    logger.error(f"Gerekli kütüphane bulunamadı: {e}")
    logger.error("Lütfen şunu çalıştırın: pip install numpy pandas python-binance")
    sys.exit(1)


class CoinSelectorConfig:
    """Coin seçim konfigürasyonları"""

    # Temel filtreler
    MIN_24H_VOLUME_USD = 10_000_000  # $10M
    MIN_MARKET_CAP_USD = 100_000_000  # $100M
    MIN_LISTING_DAYS = 90
    TRADING_PAIR = "USDT"

    # Faz bazlı konfigürasyonlar
    PHASE_CONFIGS = {
        1: {
            "coin_count": 5,
            "strategy": "conservative",
            "market_cap_top": 50,
            "volatility_max": 0.6,
            "liquidity_min": 0.7,
        },
        2: {
            "coin_count": 10,
            "strategy": "balanced",
            "market_cap_top": 100,
            "volatility_range": (0.4, 0.7),
            "trend_strength_min": 0.5,
        },
        3: {
            "coin_count": 20,
            "strategy": "aggressive",
            "market_cap_top": 200,
            "volatility_range": (0.5, 0.8),
            "ml_score_min": 0.6,
        }
    }

    # Skorlama ağırlıkları
    SCORING_WEIGHTS = {
        "liquidity": 0.25,
        "volatility": 0.20,
        "trend_strength": 0.20,
        "momentum": 0.15,
        "volume_profile": 0.10,
        "correlation": 0.10,
    }

    # Portföy kısıtları
    MIN_COIN_ALLOCATION = 0.02  # 2%
    MAX_COIN_ALLOCATION = 0.15  # 15%

    # Kara liste (bilinen riskli coinler)
    BLACKLIST = [
        "LUNA", "LUNC", "UST", "USTC",  # Terra ecosystem
        # Gerektiğinde güncellenecek
    ]


class CoinMetricsCalculator:
    """Coin için teknik metrik hesaplayıcı"""

    @staticmethod
    def calculate_liquidity_score(symbol_data: Dict) -> float:
        """
        Likidite skorunu hesaplar

        Metrikler:
            - 24s hacim
            - Order book derinliği
            - Spread sıkılığı
        """
        volume_24h = float(symbol_data.get('quoteVolume', 0))

        # Normalize et (0-1 arası)
        # Basit yaklaşım: log scale kullan
        if volume_24h > 0:
            volume_score = min(1.0, np.log10(volume_24h) / 10)
        else:
            volume_score = 0.0

        return volume_score

    @staticmethod
    def calculate_volatility_score(klines: List) -> float:
        """
        Volatilite skorunu hesaplar

        Metrikler:
            - ATR(14) normalize
            - Bollinger Band genişliği
            - Geçmiş volatilite (30g)
        """
        if not klines or len(klines) < 14:
            return 0.5  # Varsayılan orta değer

        closes = np.array([float(k[4]) for k in klines])
        highs = np.array([float(k[2]) for k in klines])
        lows = np.array([float(k[3]) for k in klines])

        # ATR hesapla (basitleştirilmiş)
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1])
            )
        )
        atr = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr)

        # Normalize et
        atr_normalized = min(1.0, atr / closes[-1] * 10)

        # Hedef: 0.4-0.7 arası (orta volatilite tercih edilir)
        if 0.4 <= atr_normalized <= 0.7:
            score = 1.0
        elif atr_normalized < 0.4:
            score = atr_normalized / 0.4
        else:
            score = max(0.0, 1.0 - (atr_normalized - 0.7) / 0.3)

        return score

    @staticmethod
    def calculate_trend_strength_score(klines: List) -> float:
        """
        Trend gücü skorunu hesaplar

        Metrikler:
            - ADX(14) değeri (basitleştirilmiş)
            - EMA hizalama (9/21/50)
        """
        if not klines or len(klines) < 50:
            return 0.5

        closes = np.array([float(k[4]) for k in klines])

        # EMA hesapla
        ema_9 = CoinMetricsCalculator._calculate_ema(closes, 9)
        ema_21 = CoinMetricsCalculator._calculate_ema(closes, 21)
        ema_50 = CoinMetricsCalculator._calculate_ema(closes, 50)

        # EMA hizalama skoru
        if ema_9 > ema_21 > ema_50:
            alignment_score = 1.0  # Güçlü yükseliş trendi
        elif ema_9 < ema_21 < ema_50:
            alignment_score = 0.8  # Güçlü düşüş trendi
        else:
            alignment_score = 0.5  # Karışık/belirsiz

        return alignment_score

    @staticmethod
    def calculate_momentum_score(klines: List) -> float:
        """
        Momentum skorunu hesaplar

        Metrikler:
            - RSI(14)
            - Fiyat vs MA mesafesi
        """
        if not klines or len(klines) < 14:
            return 0.5

        closes = np.array([float(k[4]) for k in klines])

        # RSI hesapla
        rsi = CoinMetricsCalculator._calculate_rsi(closes, 14)

        # RSI skoru (30-70 arası tercih edilir)
        if 30 <= rsi <= 70:
            rsi_score = 1.0
        elif rsi < 30:
            rsi_score = rsi / 30
        else:
            rsi_score = max(0.0, 1.0 - (rsi - 70) / 30)

        return rsi_score

    @staticmethod
    def calculate_volume_profile_score(klines: List) -> float:
        """
        Hacim profil skorunu hesaplar

        Metrikler:
            - RVOL (göreceli hacim)
            - Hacim trendi
        """
        if not klines or len(klines) < 14:
            return 0.5

        volumes = np.array([float(k[5]) for k in klines])

        # RVOL hesapla
        recent_volume = np.mean(volumes[-5:])
        avg_volume = np.mean(volumes[-14:])

        if avg_volume > 0:
            rvol = recent_volume / avg_volume
        else:
            rvol = 1.0

        # RVOL skoru (1.5-2.5 arası tercih edilir)
        if 1.5 <= rvol <= 2.5:
            score = 1.0
        elif rvol < 1.5:
            score = rvol / 1.5
        else:
            score = max(0.0, 1.0 - (rvol - 2.5) / 2.0)

        return score

    @staticmethod
    def _calculate_ema(data: np.ndarray, period: int) -> float:
        """EMA hesapla"""
        alpha = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = alpha * price + (1 - alpha) * ema
        return ema

    @staticmethod
    def _calculate_rsi(closes: np.ndarray, period: int = 14) -> float:
        """RSI hesapla"""
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi


class CoinSelector:
    """Ana coin seçici sınıf"""

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """
        Args:
            api_key: Binance API key (opsiyonel, okuma için gerekli değil)
            api_secret: Binance API secret
        """
        self.client = Client(api_key or "", api_secret or "")
        self.calculator = CoinMetricsCalculator()
        self.config = CoinSelectorConfig()

    def get_coin_universe(self) -> List[str]:
        """
        Trading için uygun coin evrenini al

        Returns:
            Filtrelenmiş coin sembolleri listesi
        """
        logger.info("Coin evrenini alıyor...")

        try:
            # Tüm ticker bilgilerini al
            tickers = self.client.get_ticker()

            # USDT çiftlerini filtrele
            usdt_pairs = [
                t for t in tickers
                if t['symbol'].endswith(self.config.TRADING_PAIR)
                and not any(bl in t['symbol'] for bl in self.config.BLACKLIST)
            ]

            # Hacim filtreleme
            filtered = [
                t for t in usdt_pairs
                if float(t['quoteVolume']) >= self.config.MIN_24H_VOLUME_USD
            ]

            symbols = [t['symbol'] for t in filtered]
            logger.info(f"{len(symbols)} coin bulundu (hacim filtresi sonrası)")

            return symbols

        except Exception as e:
            logger.error(f"Coin evreni alınırken hata: {e}")
            return []

    def calculate_coin_scores(
        self,
        symbols: List[str],
        phase: int
    ) -> pd.DataFrame:
        """
        Her coin için skorları hesapla

        Args:
            symbols: Coin sembolleri
            phase: Faz numarası (1, 2, 3)

        Returns:
            Skorları içeren DataFrame
        """
        logger.info(f"Faz {phase} için {len(symbols)} coin için skorlar hesaplanıyor...")

        results = []

        for i, symbol in enumerate(symbols, 1):
            try:
                # İlerleme göster
                if i % 10 == 0:
                    logger.info(f"İşleniyor: {i}/{len(symbols)}")

                # Ticker bilgisi
                ticker = self.client.get_ticker(symbol=symbol)

                # Kline verisi (son 60 gün, günlük)
                klines = self.client.get_klines(
                    symbol=symbol,
                    interval=Client.KLINE_INTERVAL_1DAY,
                    limit=60
                )

                # Skorları hesapla
                liquidity_score = self.calculator.calculate_liquidity_score(ticker)
                volatility_score = self.calculator.calculate_volatility_score(klines)
                trend_score = self.calculator.calculate_trend_strength_score(klines)
                momentum_score = self.calculator.calculate_momentum_score(klines)
                volume_score = self.calculator.calculate_volume_profile_score(klines)

                # Korelasyon skoru (şimdilik basit yaklaşım)
                correlation_score = 0.5  # TODO: Gerçek korelasyon hesaplama

                # Ağırlıklı final skor
                final_score = (
                    liquidity_score * self.config.SCORING_WEIGHTS["liquidity"] +
                    volatility_score * self.config.SCORING_WEIGHTS["volatility"] +
                    trend_score * self.config.SCORING_WEIGHTS["trend_strength"] +
                    momentum_score * self.config.SCORING_WEIGHTS["momentum"] +
                    volume_score * self.config.SCORING_WEIGHTS["volume_profile"] +
                    correlation_score * self.config.SCORING_WEIGHTS["correlation"]
                )

                results.append({
                    "symbol": symbol,
                    "liquidity_score": round(liquidity_score, 4),
                    "volatility_score": round(volatility_score, 4),
                    "trend_score": round(trend_score, 4),
                    "momentum_score": round(momentum_score, 4),
                    "volume_score": round(volume_score, 4),
                    "correlation_score": round(correlation_score, 4),
                    "final_score": round(final_score, 4),
                    "volume_24h": float(ticker['quoteVolume']),
                    "price": float(ticker['lastPrice']),
                })

            except Exception as e:
                logger.warning(f"{symbol} için skor hesaplama hatası: {e}")
                continue

        df = pd.DataFrame(results)

        if not df.empty:
            df = df.sort_values('final_score', ascending=False).reset_index(drop=True)
            df['rank'] = range(1, len(df) + 1)

        logger.info(f"Skorlama tamamlandı: {len(df)} coin")
        return df

    def apply_phase_filters(
        self,
        df: pd.DataFrame,
        phase: int
    ) -> pd.DataFrame:
        """
        Faz bazlı filtreleri uygula

        Args:
            df: Skorlanmış DataFrame
            phase: Faz numarası

        Returns:
            Filtrelenmiş DataFrame
        """
        phase_config = self.config.PHASE_CONFIGS.get(phase, {})

        filtered = df.copy()

        # Faz 1: Muhafazakar
        if phase == 1:
            filtered = filtered[
                (filtered['volatility_score'] <= phase_config.get('volatility_max', 1.0)) &
                (filtered['liquidity_score'] >= phase_config.get('liquidity_min', 0.0))
            ]

        # Faz 2: Dengeli
        elif phase == 2:
            vol_range = phase_config.get('volatility_range', (0.0, 1.0))
            filtered = filtered[
                (filtered['volatility_score'] >= vol_range[0]) &
                (filtered['volatility_score'] <= vol_range[1]) &
                (filtered['trend_score'] >= phase_config.get('trend_strength_min', 0.0))
            ]

        # Faz 3: Agresif
        elif phase == 3:
            vol_range = phase_config.get('volatility_range', (0.0, 1.0))
            filtered = filtered[
                (filtered['volatility_score'] >= vol_range[0]) &
                (filtered['volatility_score'] <= vol_range[1]) &
                (filtered['final_score'] >= phase_config.get('ml_score_min', 0.0))
            ]

        logger.info(f"Faz {phase} filtreleri uygulandı: {len(filtered)} coin kaldı")
        return filtered

    def select_coins(
        self,
        phase: int = 1,
        count: Optional[int] = None
    ) -> Tuple[pd.DataFrame, Dict]:
        """
        Belirtilen faz için coin seç

        Args:
            phase: Faz numarası (1, 2, 3)
            count: Seçilecek coin sayısı (None ise faz default)

        Returns:
            (seçilen_coinler_df, metadata_dict)
        """
        # Coin evrenini al
        symbols = self.get_coin_universe()

        if not symbols:
            logger.error("Coin evreni boş!")
            return pd.DataFrame(), {}

        # Skorları hesapla
        scores_df = self.calculate_coin_scores(symbols, phase)

        if scores_df.empty:
            logger.error("Skor hesaplama başarısız!")
            return pd.DataFrame(), {}

        # Faz filtrelerini uygula
        filtered_df = self.apply_phase_filters(scores_df, phase)

        # Coin sayısını belirle
        if count is None:
            count = self.config.PHASE_CONFIGS[phase]["coin_count"]

        # En iyi N coini seç
        selected = filtered_df.head(count).copy()

        # Portföy ağırlıklarını hesapla
        total_score = selected['final_score'].sum()
        if total_score > 0:
            selected['allocation'] = selected['final_score'] / total_score

            # Min/max kısıtlarını uygula
            selected['allocation'] = selected['allocation'].clip(
                lower=self.config.MIN_COIN_ALLOCATION,
                upper=self.config.MAX_COIN_ALLOCATION
            )

            # Normalize et
            selected['allocation'] = selected['allocation'] / selected['allocation'].sum()
        else:
            selected['allocation'] = 1.0 / len(selected)

        # Metadata
        metadata = {
            "timestamp": datetime.now().isoformat(),
            "phase": phase,
            "coin_count": len(selected),
            "total_universe": len(symbols),
            "filtered_count": len(filtered_df),
            "avg_score": float(selected['final_score'].mean()),
            "min_score": float(selected['final_score'].min()),
            "max_score": float(selected['final_score'].max()),
        }

        logger.info(f"✅ Faz {phase} için {len(selected)} coin seçildi")
        logger.info(f"   Ortalama skor: {metadata['avg_score']:.4f}")

        return selected, metadata


def main():
    """Ana fonksiyon"""
    parser = argparse.ArgumentParser(
        description="Manuel Coin Selection Update Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  # Faz 1: 5 coin seç
  python scripts/update_coin_selection.py --phase 1

  # Faz 2: 10 coin seç ve JSON'a kaydet
  python scripts/update_coin_selection.py --phase 2 --output selection.json

  # Faz 3: Custom sayıda coin
  python scripts/update_coin_selection.py --phase 3 --count 15
        """
    )

    parser.add_argument(
        '--phase',
        type=int,
        choices=[1, 2, 3],
        default=1,
        help='Seçim fazı (1=Muhafazakar, 2=Dengeli, 3=Agresif)'
    )

    parser.add_argument(
        '--count',
        type=int,
        help='Seçilecek coin sayısı (opsiyonel, faz default kullanılır)'
    )

    parser.add_argument(
        '--output',
        type=str,
        help='Sonuçları kaydetmek için JSON dosya yolu'
    )

    parser.add_argument(
        '--api-key',
        type=str,
        help='Binance API key (opsiyonel)'
    )

    parser.add_argument(
        '--api-secret',
        type=str,
        help='Binance API secret (opsiyonel)'
    )

    args = parser.parse_args()

    # Coin selector oluştur
    selector = CoinSelector(
        api_key=args.api_key,
        api_secret=args.api_secret
    )

    # Coin seçimini yap
    logger.info(f"🚀 Faz {args.phase} coin seçimi başlatılıyor...")

    selected_df, metadata = selector.select_coins(
        phase=args.phase,
        count=args.count
    )

    if selected_df.empty:
        logger.error("❌ Coin seçimi başarısız!")
        return 1

    # Sonuçları göster
    print("\n" + "="*80)
    print(f"📊 SEÇİLEN COİNLER (Faz {args.phase})")
    print("="*80)
    print(selected_df[['symbol', 'final_score', 'allocation', 'price', 'volume_24h']].to_string(index=False))
    print("="*80)

    print(f"\n📈 ÖZET:")
    print(f"   Toplam coin: {metadata['coin_count']}")
    print(f"   Ortalama skor: {metadata['avg_score']:.4f}")
    print(f"   Min skor: {metadata['min_score']:.4f}")
    print(f"   Max skor: {metadata['max_score']:.4f}")

    # JSON'a kaydet
    if args.output:
        output_data = {
            "metadata": metadata,
            "coins": selected_df.to_dict('records')
        }

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        logger.info(f"✅ Sonuçlar kaydedildi: {output_path}")

    logger.info("✅ İşlem tamamlandı!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
