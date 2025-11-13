"""
Risk Management System - Phase 6
=================================

Adaptive Risk-Reward (RR) System ve Risk Yönetimi modülleri.

Modules:
--------
- adaptive_rr_system : Adaptif RR hesaplama ve öğrenme sistemi
- risk_manager : Pozisyon başına risk kontrolü
- portfolio_manager : Portföy seviyesinde risk yönetimi
- shutdown_manager : Güvenli kapatma ve kill-switch sistemi

Faz: 6
Versiyon: 1.0.0
"""

from .adaptive_rr_system import (
    AdaptiveRRSystem,
    RRWeights,
    RRLearningRecord
)

from .risk_manager import (
    RiskManager,
    RiskLimits,
    RiskMetrics
)

from .portfolio_manager import (
    PortfolioManager,
    PortfolioRisk,
    ExposureLimits
)

from .shutdown_manager import (
    ShutdownManager,
    ShutdownReason,
    ShutdownReport
)

__all__ = [
    # Adaptive RR System
    'AdaptiveRRSystem',
    'RRWeights',
    'RRLearningRecord',

    # Risk Manager
    'RiskManager',
    'RiskLimits',
    'RiskMetrics',

    # Portfolio Manager
    'PortfolioManager',
    'PortfolioRisk',
    'ExposureLimits',

    # Shutdown Manager
    'ShutdownManager',
    'ShutdownReason',
    'ShutdownReport',
]

__version__ = '1.0.0'
__phase__ = 6
