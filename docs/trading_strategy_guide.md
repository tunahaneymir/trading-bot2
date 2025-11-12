# Trading Stratejisi Rehberi

## 📋 İçindekiler

1. [Strateji Genel Bakış](#strateji-genel-bakış)
2. [Multi-Timeframe Analiz](#multi-timeframe-analiz)
3. [Teknik İndikatörler](#teknik-indikatörler)
4. [Sinyal Üretimi](#sinyal-üretimi)
5. [Risk Yönetimi](#risk-yönetimi)
6. [Pozisyon Yönetimi](#pozisyon-yönetimi)
7. [Backtest ve Optimizasyon](#backtest-ve-optimizasyon)
8. [Performans Metrikleri](#performans-metrikleri)

---

## Strateji Genel Bakış

### Strateji Adı
**Adaptif Multi-Timeframe Trend Following**

### Strateji Tipi
- **Trend Following:** Ana trendi takip ederek pozisyon açar
- **Multi-Timeframe:** 1h ve 15m zaman dilimlerini birleştirir
- **Momentum Onaylı:** QQE MOD ile momentum onayı alır
- **Hacim Doğrulamalı:** RVOL ile hacim kontrolü yapar

### Hedef Market
- **Kripto Para Piyasaları:** Binance Futures
- **Trading Çiftleri:** USDT marginli futures kontratları
- **Volatilite:** Orta-yüksek volatilite coinleri tercih eder

### Temel Mantık

```
1. 1 SAAT: SuperTrend ile ana trend yönünü belirle
2. 15 DAKİKA: MOST ile giriş zamanlaması bul
3. 15 DAKİKA: QQE MOD ile momentum onayı al
4. 15 DAKİKA: RVOL ile hacim kontrolü yap
5. TÜM İNDİKATÖRLER UYUŞURSA: Pozisyon aç
```

---

## Multi-Timeframe Analiz

### Neden Multi-Timeframe?

1. **Daha Güvenilir Sinyaller:** Farklı zaman dilimlerinde onay almak sinyal kalitesini artırır
2. **Noise Filtreleme:** Kısa vadeli gürültüyü filtreleyerek yanlış sinyalleri azaltır
3. **Trend Doğrulama:** Büyük zaman diliminde trend yönü küçük zaman diliminde onaylanır

### Zaman Dilimi Rolleri

#### 1 Saatlik (1h) - Ana Trend
- **İndikatör:** SuperTrend (ATR Period: 14, Multiplier: 3.0)
- **Rol:** Ana trend yönünü belirler
- **Kullanım:** Uptrend ise sadece LONG, downtrend ise sadece SHORT

#### 15 Dakikalık (15m) - Giriş Zamanlaması
- **İndikatörler:** MOST, QQE MOD, RVOL
- **Rol:** Optimal giriş noktasını belirler
- **Kullanım:** Ana trend ile uyumlu giriş sinyalleri arar

### Örnek Senaryo

```
LONG POZİSYON:
1h: SuperTrend Uptrend (✅)
15m: MOST Uptrend (✅)
15m: QQE MOD Bullish (✅)
15m: RVOL > 1.5x (✅)
→ STRONG_BUY Sinyali

SHORT POZİSYON:
1h: SuperTrend Downtrend (✅)
15m: MOST Downtrend (✅)
15m: QQE MOD Bearish (✅)
15m: RVOL > 1.5x (✅)
→ STRONG_SELL Sinyali
```

---

## Teknik İndikatörler

### 1. SuperTrend (1h)

**Amaç:** Ana trend yönünü belirlemek

**Parametreler:**
- ATR Period: 14
- Multiplier: 3.0

**Sinyal:**
- **Uptrend:** Fiyat SuperTrend çizgisinin üzerinde
- **Downtrend:** Fiyat SuperTrend çizgisinin altında

**Avantajları:**
- Güçlü trend değişimlerini yakalar
- Net al/sat sinyalleri
- Trailing stop görevi görür

**Dezavantajları:**
- Yan piyasalarda çok sinyal üretir (whipsaw)
- Geç sinyal verebilir

---

### 2. MOST (15m)

**Amaç:** Entry/exit zamanlaması için adaptif stop loss

**Parametreler:**
- Length: 9
- Percent: 2.0%
- MA Type: VAR (Variable MA)

**Sinyal:**
- **Uptrend:** Fiyat MOST çizgisinin üzerinde
- **Downtrend:** Fiyat MOST çizgisinin altında

**Avantajları:**
- SuperTrend'e göre daha hassas
- Daha hızlı trend değişimi yakalar
- Adaptif stop loss

**Kullanım:**
- 15m'de hızlı trend değişimlerini yakalar
- Entry zamanlaması için ideal

---

### 3. QQE MOD (15m)

**Amaç:** Momentum onayı ve aşırı alım/satım kontrolü

**Parametreler:**
- RSI Period: 6
- RSI Smoothing: 5
- QQE Factor: 3.0
- Threshold: 3

**Sinyal:**
- **Bullish:** QQE Line > Signal Line
- **Bearish:** QQE Line < Signal Line

**Avantajları:**
- RSI tabanlı, momentum ölçer
- Smoothed olduğu için gürültü az
- Trend içinde güçlü sinyaller

**Kullanım:**
- Trend yönünde momentum onayı
- Erken giriş için uyarı sinyali

---

### 4. RVOL (15m)

**Amaç:** Hacim onayı ile sinyal kalitesini artırma

**Parametreler:**
- Period: 20
- High Threshold: 1.5x
- Low Threshold: 0.5x

**Sinyal:**
- **Yüksek Hacim:** RVOL > 1.5x (güçlü hareket)
- **Normal Hacim:** 0.5x < RVOL < 1.5x
- **Düşük Hacim:** RVOL < 0.5x (zayıf hareket)

**Avantajları:**
- Sahte sinyalleri filtreler
- Güçlü hareketleri doğrular
- Volume confirmation ekler

**Kullanım:**
- Sadece yüksek hacimli sinyaller alınır
- Düşük hacimde pozisyon açılmaz

---

## Sinyal Üretimi

### Sinyal Tipleri

```python
STRONG_BUY:  4/4 indikatör uyuşuyor (Long)
BUY:         3/4 indikatör uyuşuyor (Long)
NEUTRAL:     Karışık sinyaller
SELL:        3/4 indikatör uyuşuyor (Short)
STRONG_SELL: 4/4 indikatör uyuşuyor (Short)
```

### Güven Seviyeleri

```python
VERY_HIGH:   4/4 indikatör (100%)
HIGH:        3/4 indikatör (75%)
MEDIUM:      2/4 indikatör (50%)
LOW:         1/4 indikatör (25%)
VERY_LOW:    0/4 indikatör (0%)
```

### Sinyal Filtreleme

**Sadece STRONG sinyaller alınır:**
- STRONG_BUY (Confidence ≥ 75%)
- STRONG_SELL (Confidence ≥ 75%)

**Filtreleme Nedenleri:**
1. Sinyal kalitesini artırır
2. Kazanma oranını yükseltir
3. Risk yönetimini kolaylaştırır
4. Whipsaw'ları azaltır

### Örnek Sinyal

```json
{
  "signal_type": "STRONG_BUY",
  "confidence": "HIGH",
  "confidence_score": 1.0,
  "entry_price": 50000.0,
  "stop_loss": 49000.0,
  "take_profit": 52000.0,
  "indicators": [
    {
      "name": "SuperTrend",
      "signal": "BUY",
      "timeframe": "1h",
      "reason": "SuperTrend uptrend (ST: 48500.00)"
    },
    {
      "name": "MOST",
      "signal": "BUY",
      "timeframe": "15m",
      "reason": "MOST uptrend (MOST: 49800.00)"
    },
    {
      "name": "QQE_MOD",
      "signal": "BUY",
      "timeframe": "15m",
      "reason": "QQE MOD bullish (QQE: 65.50 > Signal: 60.00)"
    },
    {
      "name": "RVOL",
      "signal": "BUY",
      "timeframe": "15m",
      "reason": "Yüksek hacim (RVOL: 2.30x)"
    }
  ]
}
```

---

## Risk Yönetimi

### Pozisyon Boyutlandırma

**Sabit Pozisyon Büyüklüğü:**
```python
position_size_usdt = 100.0  # Her trade için $100
quantity = position_size_usdt / entry_price
```

**Gelecek (Faz 6):**
- Kelly Criterion ile dinamik boyutlandırma
- Volatilite ayarlı pozisyon büyüklüğü
- Portföy bazlı risk yönetimi

### Stop Loss Stratejisi

**ATR Bazlı Stop Loss:**
```python
# LONG pozisyon
stop_loss = entry_price - (ATR * 2.0)

# SHORT pozisyon
stop_loss = entry_price + (ATR * 2.0)
```

**SuperTrend Bazlı Stop Loss:**
```python
# SuperTrend line doğal stop loss
stop_loss = supertrend_line
```

**Avantajları:**
- Volatilite adaptif
- Market koşullarına uygun
- Premature stop-out'u önler

### Take Profit Stratejisi

**Sabit RR Ratio:**
```python
risk = entry_price - stop_loss
reward = risk * 2.0  # 1:2 RR ratio
take_profit = entry_price + reward
```

**Gelecek (Faz 6):**
- Adaptif RR sistemi (1.1 - 1.9 arası)
- Piyasa koşullarına göre dinamik ayarlama
- RL bazlı optimizasyon

### Trailing Stop

**Aktif (Gelecek):**
```python
trailing_stop_percent = 2.0  # %2
# Fiyat yükselirken stop loss da yükselir
```

### Risk Limitleri

```python
max_risk_per_trade = 2%      # Trade başına max risk
max_total_risk = 6%           # Toplam portföy riski
max_positions = 5             # Maksimum eşzamanlı pozisyon
max_drawdown = 10%            # Maksimum düşüş limiti
```

---

## Pozisyon Yönetimi

### Pozisyon Açma

```python
# Koşullar:
1. Sinyal STRONG_BUY veya STRONG_SELL
2. Confidence ≥ 75%
3. Aktif pozisyon sayısı < max_positions
4. Current drawdown < max_drawdown
5. Risk limitleri uygun

# İşlemler:
1. Market emir gönder
2. Pozisyon kaydı oluştur
3. Stop loss ve take profit emirleri yerleştir
4. Trailing stop aktifleştir (opsiyonel)
```

### Pozisyon Güncelleme

```python
# Her döngüde:
1. Güncel fiyat ile pozisyonu güncelle
2. Unrealized PnL hesapla
3. Trailing stop güncelle
4. Highest/lowest price takibi
```

### Pozisyon Kapatma

**Exit Nedenleri:**

1. **TAKE_PROFIT:** Take profit seviyesine ulaşıldı
2. **STOP_LOSS:** Stop loss'a takıldı
3. **TRAILING_STOP:** Trailing stop tetiklendi
4. **SIGNAL:** Ters sinyal geldi
5. **MANUAL:** Manuel kapatma
6. **EMERGENCY:** Acil durum

```python
# Kapatma İşlemi:
1. Market emir gönder (reduce_only)
2. Pozisyon kaydını güncelle
3. PnL hesapla
4. İstatistikleri güncelle
5. Trade geçmişine kaydet
```

### Pozisyon State Machine

```
OPENING → OPEN → CLOSING → CLOSED
   ↓        ↓        ↓
CANCELLED CANCELLED CANCELLED
```

---

## Backtest ve Optimizasyon

### Backtest Süreci

```bash
# 1. Backtest çalıştır
python scripts/backtest_strategy.py --symbol BTCUSDT --initial-balance 10000

# 2. Sonuçları analiz et
jupyter notebook notebooks/07_backtest_sonuclari.ipynb
```

### Optimizasyon Parametreleri

**İndikatör Parametreleri:**
```python
SuperTrend:
  - atr_period: [10, 12, 14, 16]
  - multiplier: [2.5, 3.0, 3.5, 4.0]

MOST:
  - length: [7, 9, 11, 13]
  - percent: [1.5, 2.0, 2.5, 3.0]

QQE MOD:
  - rsi_period: [5, 6, 7, 8]
  - rsi_smoothing: [4, 5, 6, 7]

RVOL:
  - period: [14, 20, 26]
  - threshold_high: [1.3, 1.5, 1.7, 2.0]
```

**Risk Parametreleri:**
```python
Risk Management:
  - position_size: [50, 100, 200]
  - stop_loss_multiplier: [1.5, 2.0, 2.5, 3.0]
  - take_profit_ratio: [1.5, 2.0, 2.5, 3.0]
  - trailing_stop_percent: [1.5, 2.0, 2.5, 3.0]
```

### Walk-Forward Analysis

```
1. Eğitim: 60% veri (parametre optimizasyonu)
2. Validasyon: 20% veri (model seçimi)
3. Test: 20% veri (performans değerlendirmesi)

Yürüyen pencere ile tekrarla
```

---

## Performans Metrikleri

### Temel Metrikler

```python
Win Rate = (Kazanan Trade / Toplam Trade) * 100
Profit Factor = Toplam Kazanç / Toplam Kayıp
Net Profit = Toplam Kazanç - Toplam Kayıp
Net Profit % = (Net Profit / Initial Balance) * 100
```

### Risk Metrikleri

```python
Max Drawdown = Max((Peak - Trough) / Peak) * 100
Sharpe Ratio = (Ortalama Getiri - Risk-Free Rate) / Std Dev
Sortino Ratio = (Ortalama Getiri - Risk-Free Rate) / Downside Dev
```

### Trade Metrikleri

```python
Avg Win = Toplam Kazanç / Kazanan Trade
Avg Loss = Toplam Kayıp / Kaybeden Trade
Risk/Reward Ratio = Avg Win / Avg Loss
Win/Loss Ratio = Kazanan Trade / Kaybeden Trade
```

### Hedef Performans (6 Ay Sonunda)

```
✅ Win Rate: ≥ 55%
✅ Profit Factor: ≥ 1.5
✅ Sharpe Ratio: ≥ 1.2
✅ Max Drawdown: ≤ 8%
✅ Net Profit: ≥ 60% (yıllık)
```

---

## Uygulama Örnekleri

### Python Kullanımı

```python
from trading import (
    SignalGenerator,
    PositionManager,
    OrderExecutor,
    TradingEngine
)

# Bileşenleri oluştur
signal_gen = SignalGenerator()
pos_mgr = PositionManager()
order_exec = OrderExecutor(binance_manager)

# Trading engine
engine = TradingEngine(
    signal_generator=signal_gen,
    position_manager=pos_mgr,
    order_executor=order_exec,
    config={
        'symbols': ['BTCUSDT', 'ETHUSDT'],
        'position_size_usdt': 100.0,
        'max_positions': 5
    }
)

# Başlat
await engine.start()
```

### Backtesting

```python
from scripts.backtest_strategy import BacktestEngine

# Backtest engine
backtest = BacktestEngine(
    symbol='BTCUSDT',
    initial_balance=10000.0,
    position_size_usdt=100.0
)

# Backtest çalıştır
results = await backtest.run_backtest(data_1h, data_15m, timestamps)

# Rapor kaydet
backtest.save_report('backtest_results')
```

---

## Sonraki Fazlar

### Faz 6: Gelişmiş Risk Yönetimi
- Adaptif RR sistemi
- Dinamik pozisyon boyutlandırma
- Portföy risk metrikleri
- Shutdown manager

### Faz 7: ML/RL Entegrasyonu
- Feature engineering
- Model training
- RL agent (PPO)
- Hyperparameter optimization

### Faz 8: Dashboard ve Monitoring
- Real-time dashboard
- Performance analytics
- Learning dashboard
- Alert system

### Faz 9: Production Readiness
- Full system integration
- Paper trading test
- Live trading deployment
- Continuous monitoring

---

**Yazar:** Trading Bot Sistemi
**Versiyon:** 1.0.0
**Faz:** 5
**Tarih:** 2025-11-12
**Durum:** Tamamlandı
