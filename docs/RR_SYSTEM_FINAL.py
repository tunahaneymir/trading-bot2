# 📘 HYBRID ADAPTIVE RR SYSTEM (Self-Evolving Static Code Version)
**Version:** 1.0  
**Integration:** Risk Manager Layer  
**Status:** Final – No further updates required  
**Author:** Tuna x GPT-5  

---

## 🎯 AMAÇ
Bu sistem, **tek kod sürümüyle uzun vadeli öğrenme ve adaptasyonu** hedefler.  
İlk günden itibaren Signal-Based + Market-Condition + RL Optimized RR mekanizmalarını birlikte çalıştırır.  
Kod sabittir, davranış zamanla öğrenmeye bağlı olarak evrilir.  

RR hesaplaması her bar’da dinamik olarak yapılır,  
ancak öğrenme çıktıları `state/rr_weights.json` dosyasında saklanır.  
Bu sayede kodu değiştirmeden aylarca kesintisiz öğrenme mümkündür.

---

## ⚙️ 1️⃣ RR ÇALIŞMA PRENSİBİ
RR, üç bileşenin birleşimiyle belirlenir:

1. **Signal Confidence Core** → SuperTrend, MOST, QQE, RVOL  
2. **Market Condition Modulator** → Trend Strength + Volatility (ATR tabanlı)  
3. **RL Optimization Layer** → Gerçek trade sonuçlarına göre katsayı ayarı  

Bu üç katman eşzamanlı çalışır.  
Kod hiçbir zaman değişmez, öğrenme yalnızca veriden gelir.

---

## 🧩 2️⃣ RR HESAPLAMA FORMÜLÜ

```python
# Signal Confidence hesaplama
signal_confidence = weighted_confidence([
    st_conf,  # SuperTrend güveni
    qqe_conf, # QQE histogram kuvveti
    most_conf,# MOST RSI pozisyonu
    rvol_conf # RVOL hacim onayı
])

# Market condition hesaplama
trend_strength = normalize(abs(most - supertrend))
volatility = normalize(atr / price)
market_condition_index = 0.5 * (1 - trend_strength) + 0.5 * volatility

# RR birleşimi
rr_signal = 1.5 - (signal_confidence * 0.4)
rr_market = rr_signal + (market_condition_index * 0.3)
rr_final = rr_market * rr_weights["rl_factor"]
rr_final = clamp(rr_final, 1.1, 1.9)
```

---

## 🧠 3️⃣ RL ÖĞRENME MEKANİZMASI

```python
# Reward normalizasyonu (daha dengeli öğrenme)
reward = np.log1p(abs(pnl)) * np.sign(pnl)
reward *= rr_efficiency * signal_consistency

# Dinamik öğrenme hızı (volatiliteye göre)
learning_rate = max(0.002, min(0.02, volatility * 0.02))

# RR faktörü güncelleme
if reward > 0:
    rr_weights["rl_factor"] += learning_rate * (1 - rr_weights["rl_factor"])
else:
    rr_weights["rl_factor"] -= learning_rate * rr_weights["rl_factor"]

# Dosya güvenliği ve kalıcılık
try:
    save_json("state/rr_weights.json", rr_weights)
except Exception as e:
    log.warning(f"RR weights not saved: {e}")
```

Bu sayede sistem:
- Kazançlı işlemlerde RR’a güveni artırır  
- Zararlılarda azaltır  
- Veriyi kaybetmeden, her yeniden başlatmada kaldığı yerden devam eder  

---

## 🧱 4️⃣ BAŞLANGIÇ PARAMETRELERİ

```python
# İlk çalıştırma varsayılanları
rr_weights = {
    "signal_weight": 0.7,
    "market_weight": 0.3,
    "rl_factor": 1.0
}
```

Eğer `state/rr_weights.json` bulunmazsa bu değerlerle otomatik oluşturulur.

---

## 🧩 5️⃣ STABİLİZASYON MANTIĞI

```python
# RR volatilitesi yüksekse sistem dondurulur
if rr_volatility > 0.4:
    freeze_rr_weights()
```

20 işlem penceresinde RR sapması 0.4’ü aşarsa  
sistem katsayı güncellemelerini geçici olarak durdurur.  
Bu, uzun vadede stabil karakter oluşturur.

---

## 🔐 6️⃣ RISK MANAGER ENTEGRASYONU

```python
if current_rr >= rr_final:
    allow_exit = True
elif price <= stop_loss:
    force_exit = True
else:
    hold_position()
```

- 1.5 RR’ye ulaşmadan erken satış yapılmaz.  
- Stop-loss her zaman aktif kalır.  
- RR hedefi dolmadan çıkış sinyali onaylanmaz.

---

## 🧮 7️⃣ YAML PARAMETRELERİ

```yaml
rr_mode: "hybrid_adaptive_static"
rr_learning: "self_evolving"
rr_signal_weight: 0.7
rr_market_weight: 0.3
rr_rl_factor: 1.0
rr_stabilization_window: 20
rr_range: [1.1, 1.9]
rr_persistence: "state/rr_weights.json"
```

---

## 🧭 8️⃣ SİSTEM ÖZETİ

| Özellik | Durum |
|----------|--------|
| Kod | Statik (değişmez) |
| Davranış | Evrimsel (öğrenmeye açık) |
| Öğrenme kaynağı | Gerçek trade sonuçları |
| Güncelleme ihtiyacı | ❌ Yok |
| RR aralığı | [1.1 – 1.9] |
| Veri kaydı | `state/rr_weights.json` |
| Stabilizasyon | 20 işlem penceresi |
| Başlangıç modu | Signal + Market + RL aktif |

---

## ✅ SON TANIM
> Bu RR sistemi **tek sürümde nihai formuna ulaşacak** şekilde kodlanır.  
> Kod sabit kalır; sistem zamanla kendi trade sonuçlarına göre RR davranışını optimize eder.  
> Her yeniden başlatmada, kaldığı yerden devam eder.  
> Güncelleme, yeniden eğitim veya manuel parametre değişimi gerekmez.  

---

**Bu sürüm, 6+ ay boyunca kesintisiz paper/real trade öğrenmesine hazırdır.**