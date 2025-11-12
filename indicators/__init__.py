"""
Teknik İndikatörler Paketi
==========================

Çok zaman dilimli trading stratejileri için teknik indikatör koleksiyonu.

Faz 5 İndikatörleri:
===================

Temel İndikatörler:
------------------
- BaseIndicator: Soyut temel sınıf (tüm indikatörler için)
- ATR: Average True Range (volatilite ölçümü)

Trend İndikatörleri:
-------------------
- MOST: Moving Stop Loss (adaptif trend takibi)
- SuperTrend: ATR bazlı trend takibi

Momentum İndikatörleri:
----------------------
- QQE MOD: Quantum Qualitative Estimation Modified (momentum)

Hacim İndikatörleri:
-------------------
- RVOL: Relative Volume (hacim onayı)

Kullanım Örneği:
---------------
```python
from indicators import calculate_atr, calculate_supertrend, calculate_most

# ATR hesapla
atr = calculate_atr(high, low, close, period=14)

# SuperTrend hesapla
st, trend = calculate_supertrend(high, low, close, atr_period=10, multiplier=3.0)

# MOST hesapla
most, trend = calculate_most(close, length=9, percent=2.0)
```

Mimari:
-------
```
indicators/
├── base_indicator.py      # Temel sınıf
├── atr.py                 # ATR indikatörü
├── most.py                # MOST indikatörü
├── supertrend.py          # SuperTrend indikatörü
├── qqe_mod.py             # QQE MOD indikatörü
├── rvol.py                # RVOL indikatörü
└── __init__.py            # Bu dosya
```

Yazar: Trading Bot Sistemi
Versiyon: 1.0.0
Faz: 5
"""

# Temel sınıflar
from .base_indicator import (
    BaseIndicator,
    MultiOutputIndicator,
    InsufficientDataError
)

# ATR İndikatörü
from .atr import (
    ATR,
    calculate_atr,
    calculate_atr_stop_loss
)

# MOST İndikatörü
from .most import (
    calculate_most,
    get_most_signal,
    most_with_signal
)

# SuperTrend İndikatörü
from .supertrend import (
    calculate_supertrend,
    calculate_atr as supertrend_calculate_atr,  # Alias to avoid conflict
    calculate_true_range,
    get_supertrend_signal,
    supertrend_with_signal
)

# QQE MOD İndikatörü (Faz 4'ten)
from .qqe_mod import (
    QQEMod,
    qqe_mod,
    qqe_signal
)

# RVOL İndikatörü (Faz 4'ten)
from .rvol import (
    RVOL,
    rvol,
    rvol_signal
)


# Public API
__all__ = [
    # Temel sınıflar
    'BaseIndicator',
    'MultiOutputIndicator',
    'InsufficientDataError',
    
    # ATR
    'ATR',
    'calculate_atr',
    'calculate_atr_stop_loss',
    
    # MOST
    'calculate_most',
    'get_most_signal',
    'most_with_signal',
    
    # SuperTrend
    'calculate_supertrend',
    'calculate_true_range',
    'get_supertrend_signal',
    'supertrend_with_signal',
    
    # QQE MOD
    'QQEMod',
    'qqe_mod',
    'qqe_signal',
    
    # RVOL
    'RVOL',
    'rvol',
    'rvol_signal',
]

# Paket metadata
__version__ = '1.0.0'
__author__ = 'Trading Bot Sistemi'
__phase__ = 5
__description__ = 'Çok zaman dilimli trading stratejileri için teknik indikatör koleksiyonu'


# İndikatör bilgileri
INDICATORS_INFO = {
    'base': {
        'BaseIndicator': {
            'type': 'abstract',
            'description': 'Tüm indikatörler için soyut temel sınıf',
            'required_length': None
        },
        'ATR': {
            'type': 'volatility',
            'description': 'Average True Range - Volatilite ölçümü',
            'default_period': 14,
            'smoothing_methods': ['RMA', 'SMA', 'EMA', 'WMA']
        }
    },
    'trend': {
        'MOST': {
            'type': 'trend',
            'description': 'Moving Stop Loss - Adaptif trend takibi',
            'default_period': 9,
            'default_percent': 2.0,
            'ma_types': ['VAR', 'EMA', 'HULL', 'T3', 'SMA', 'WMA'],
            'timeframe': '15m'
        },
        'SuperTrend': {
            'type': 'trend',
            'description': 'ATR bazlı trend takibi',
            'default_period': 10,
            'default_multiplier': 3.0,
            'timeframe': '1h'
        }
    },
    'momentum': {
        'QQE_MOD': {
            'type': 'momentum',
            'description': 'Quantum Qualitative Estimation Modified',
            'default_rsi_period': 6,
            'default_rsi_smoothing': 5,
            'timeframe': '15m'
        }
    },
    'volume': {
        'RVOL': {
            'type': 'volume',
            'description': 'Relative Volume - Hacim onayı',
            'default_period': 20,
            'timeframe': '15m'
        }
    }
}


def get_indicator_info(indicator_name: str = None) -> dict:
    """
    İndikatör bilgilerini getir.
    
    Parametreler:
    ------------
    indicator_name : str, optional
        İndikatör adı (None ise tüm indikatörler)
    
    Returns:
    --------
    dict
        İndikatör bilgileri
    
    Örnek:
    ------
    >>> info = get_indicator_info('MOST')
    >>> print(info['description'])
    Moving Stop Loss - Adaptif trend takibi
    """
    if indicator_name is None:
        return INDICATORS_INFO
    
    # İndikatörü ara
    for category, indicators in INDICATORS_INFO.items():
        if indicator_name in indicators:
            return indicators[indicator_name]
    
    return None


def list_indicators() -> dict:
    """
    Tüm mevcut indikatörleri listele.
    
    Returns:
    --------
    dict
        Kategorilere göre indikatör listesi
    
    Örnek:
    ------
    >>> indicators = list_indicators()
    >>> print(indicators['trend'])
    ['MOST', 'SuperTrend']
    """
    result = {}
    for category, indicators in INDICATORS_INFO.items():
        result[category] = list(indicators.keys())
    return result


def get_version_info() -> dict:
    """
    Paket versiyon bilgilerini getir.
    
    Returns:
    --------
    dict
        Versiyon bilgileri
    """
    return {
        'version': __version__,
        'author': __author__,
        'phase': __phase__,
        'description': __description__,
        'indicators_count': sum(len(inds) for inds in INDICATORS_INFO.values())
    }


if __name__ == "__main__":
    print("📦 Teknik İndikatörler Paketi")
    print("=" * 60)
    
    # Versiyon bilgileri
    version_info = get_version_info()
    print(f"\n✅ Versiyon: {version_info['version']}")
    print(f"✅ Faz: {version_info['phase']}")
    print(f"✅ Toplam İndikatör: {version_info['indicators_count']}")
    
    # İndikatör listesi
    print("\n📊 Mevcut İndikatörler:")
    print("-" * 60)
    
    indicators = list_indicators()
    for category, inds in indicators.items():
        print(f"\n{category.upper()}:")
        for ind in inds:
            info = get_indicator_info(ind)
            if info:
                print(f"  • {ind}: {info.get('description', 'N/A')}")
    
    print("\n" + "=" * 60)
    print("✅ Paket hazır!")