"""
Position Manager Testleri
=========================

PositionManager ve Position sınıflarının kapsamlı testleri.

Test Kategorileri:
-----------------
1. Position sınıfı testleri
2. PositionManager açma/kapama
3. Risk hesaplamaları
4. Stop loss / take profit
5. Trailing stop
6. İstatistikler
7. Error handling

Yazar: Trading Bot Sistemi
Versiyon: 1.0.0
Faz: 5
"""

import pytest
import asyncio
from datetime import datetime, timezone
from typing import List
import sys
from pathlib import Path

# position_manager modülünü import et
sys.path.insert(0, str(Path(__file__).parent.parent / "outputs"))

from position_manager import (
    Position,
    PositionManager,
    PositionState,
    PositionSide,
    CloseReason
)


@pytest.fixture
def sample_position_data():
    """Örnek pozisyon verisi."""
    return {
        'position_id': 'test-position-1',
        'symbol': 'BTCUSDT',
        'side': PositionSide.LONG,
        'state': PositionState.OPEN,
        'entry_price': 50000.0,
        'quantity': 0.1,
        'entry_time': datetime.now(timezone.utc),
        'entry_signal_type': 'STRONG_BUY',
        'entry_signal_confidence': 0.85,
        'stop_loss': 49000.0,
        'take_profit': 52000.0,
        'trailing_stop_percent': 2.0
    }


@pytest.fixture
def position_manager():
    """PositionManager instance."""
    return PositionManager()


class TestPositionClass:
    """Position sınıfı testleri."""
    
    def test_position_creation(self, sample_position_data):
        """Pozisyon oluşturma testi."""
        position = Position(**sample_position_data)
        
        assert position.position_id == 'test-position-1'
        assert position.symbol == 'BTCUSDT'
        assert position.side == PositionSide.LONG
        assert position.state == PositionState.OPEN
        assert position.entry_price == 50000.0
        assert position.quantity == 0.1
    
    def test_position_from_dict(self, sample_position_data):
        """Dictionary'den pozisyon oluşturma."""
        position = Position(**sample_position_data)
        position_dict = position.to_dict()
        
        # Dict'ten geri oluştur
        new_position = Position.from_dict(position_dict)
        
        assert new_position.position_id == position.position_id
        assert new_position.symbol == position.symbol
        assert new_position.entry_price == position.entry_price
    
    def test_update_price_long(self, sample_position_data):
        """Long pozisyon fiyat güncelleme."""
        position = Position(**sample_position_data)
        
        # Fiyat artışı
        position.update_price(51000.0)
        
        assert position.last_price == 51000.0
        assert position.highest_price == 51000.0
        assert position.unrealized_pnl > 0  # Kar
        assert position.unrealized_pnl_percent > 0
    
    def test_update_price_short(self, sample_position_data):
        """Short pozisyon fiyat güncelleme."""
        sample_position_data['side'] = PositionSide.SHORT
        position = Position(**sample_position_data)
        
        # Fiyat düşüşü (short için kar)
        position.update_price(49000.0)
        
        assert position.last_price == 49000.0
        assert position.lowest_price == 49000.0
        assert position.unrealized_pnl > 0  # Kar
    
    def test_unrealized_pnl_calculation_long(self, sample_position_data):
        """Long pozisyon unrealized PnL hesaplama."""
        position = Position(**sample_position_data)
        
        # Entry: 50000, Current: 51000, Qty: 0.1
        # PnL = (51000 - 50000) * 0.1 = 100 USDT
        position.update_price(51000.0)
        
        assert abs(position.unrealized_pnl - 100.0) < 0.01
        assert abs(position.unrealized_pnl_percent - 2.0) < 0.01
    
    def test_unrealized_pnl_calculation_short(self, sample_position_data):
        """Short pozisyon unrealized PnL hesaplama."""
        sample_position_data['side'] = PositionSide.SHORT
        position = Position(**sample_position_data)
        
        # Entry: 50000, Current: 49000, Qty: 0.1
        # PnL = (50000 - 49000) * 0.1 = 100 USDT
        position.update_price(49000.0)
        
        assert abs(position.unrealized_pnl - 100.0) < 0.01
        assert abs(position.unrealized_pnl_percent - 2.0) < 0.01
    
    def test_close_position_long(self, sample_position_data):
        """Long pozisyon kapatma."""
        position = Position(**sample_position_data)
        
        # Kar ile kapat
        position.close_position(52000.0, CloseReason.TAKE_PROFIT, 10.4)
        
        assert position.state == PositionState.CLOSED
        assert position.exit_price == 52000.0
        assert position.exit_reason == CloseReason.TAKE_PROFIT
        assert position.realized_pnl > 0  # Kar
    
    def test_close_position_short(self, sample_position_data):
        """Short pozisyon kapatma."""
        sample_position_data['side'] = PositionSide.SHORT
        position = Position(**sample_position_data)
        
        # Kar ile kapat (fiyat düştü)
        position.close_position(48000.0, CloseReason.TAKE_PROFIT, 9.6)
        
        assert position.state == PositionState.CLOSED
        assert position.exit_price == 48000.0
        assert position.realized_pnl > 0  # Kar
    
    def test_realized_pnl_with_fees(self, sample_position_data):
        """Komisyonlu realized PnL hesaplama."""
        position = Position(**sample_position_data)
        position.entry_fee = 10.0  # Entry komisyonu
        
        # Exit: 52000, Entry fee: 10, Exit fee: 10.4
        # Gross PnL = (52000 - 50000) * 0.1 = 200
        # Net PnL = 200 - 10 - 10.4 = 179.6
        position.close_position(52000.0, CloseReason.TAKE_PROFIT, 10.4)
        
        expected_net_pnl = 200.0 - 10.0 - 10.4
        assert abs(position.realized_pnl - expected_net_pnl) < 0.01
    
    def test_should_stop_loss_long(self, sample_position_data):
        """Long pozisyon stop loss kontrolü."""
        position = Position(**sample_position_data)
        
        # Stop loss: 49000
        assert position.should_stop_loss(48500.0) == True   # Altında
        assert position.should_stop_loss(49000.0) == True   # Eşit
        assert position.should_stop_loss(49500.0) == False  # Üstünde
    
    def test_should_stop_loss_short(self, sample_position_data):
        """Short pozisyon stop loss kontrolü."""
        sample_position_data['side'] = PositionSide.SHORT
        sample_position_data['stop_loss'] = 51000.0
        position = Position(**sample_position_data)
        
        # Stop loss: 51000
        assert position.should_stop_loss(51500.0) == True   # Üstünde
        assert position.should_stop_loss(51000.0) == True   # Eşit
        assert position.should_stop_loss(50500.0) == False  # Altında
    
    def test_should_take_profit_long(self, sample_position_data):
        """Long pozisyon take profit kontrolü."""
        position = Position(**sample_position_data)
        
        # Take profit: 52000
        assert position.should_take_profit(52500.0) == True   # Üstünde
        assert position.should_take_profit(52000.0) == True   # Eşit
        assert position.should_take_profit(51500.0) == False  # Altında
    
    def test_should_take_profit_short(self, sample_position_data):
        """Short pozisyon take profit kontrolü."""
        sample_position_data['side'] = PositionSide.SHORT
        sample_position_data['take_profit'] = 48000.0
        position = Position(**sample_position_data)
        
        # Take profit: 48000
        assert position.should_take_profit(47500.0) == True   # Altında
        assert position.should_take_profit(48000.0) == True   # Eşit
        assert position.should_take_profit(48500.0) == False  # Üstünde
    
    def test_trailing_stop_long(self, sample_position_data):
        """Long pozisyon trailing stop."""
        position = Position(**sample_position_data)
        
        # Başlangıç SL: 49000
        initial_sl = position.stop_loss
        
        # Fiyat yükseldi
        position.update_price(52000.0)
        position.update_trailing_stop(52000.0)
        
        # Yeni SL = 52000 * (1 - 0.02) = 50960
        expected_sl = 52000.0 * 0.98
        assert position.stop_loss > initial_sl
        assert abs(position.stop_loss - expected_sl) < 0.01
    
    def test_trailing_stop_short(self, sample_position_data):
        """Short pozisyon trailing stop."""
        sample_position_data['side'] = PositionSide.SHORT
        sample_position_data['stop_loss'] = 51000.0
        position = Position(**sample_position_data)
        
        initial_sl = position.stop_loss
        
        # Fiyat düştü (short için iyi)
        position.update_price(48000.0)
        position.update_trailing_stop(48000.0)
        
        # Yeni SL = 48000 * (1 + 0.02) = 48960
        expected_sl = 48000.0 * 1.02
        assert position.stop_loss < initial_sl
        assert abs(position.stop_loss - expected_sl) < 0.01
    
    def test_get_position_size_usdt(self, sample_position_data):
        """Pozisyon büyüklüğü USDT."""
        position = Position(**sample_position_data)
        
        # Entry: 50000, Qty: 0.1
        # Size = 50000 * 0.1 = 5000 USDT
        assert abs(position.get_position_size_usdt() - 5000.0) < 0.01
    
    def test_get_risk_amount_usdt(self, sample_position_data):
        """Risk miktarı USDT."""
        position = Position(**sample_position_data)
        
        # Entry: 50000, SL: 49000, Qty: 0.1
        # Risk = (50000 - 49000) * 0.1 = 100 USDT
        risk = position.get_risk_amount_usdt()
        assert abs(risk - 100.0) < 0.01
    
    def test_get_reward_amount_usdt(self, sample_position_data):
        """Beklenen kazanç miktarı USDT."""
        position = Position(**sample_position_data)
        
        # Entry: 50000, TP: 52000, Qty: 0.1
        # Reward = (52000 - 50000) * 0.1 = 200 USDT
        reward = position.get_reward_amount_usdt()
        assert abs(reward - 200.0) < 0.01


class TestPositionManager:
    """PositionManager sınıfı testleri."""
    
    @pytest.mark.asyncio
    async def test_position_manager_creation(self, position_manager):
        """PositionManager oluşturma."""
        assert position_manager is not None
        assert position_manager.active_positions == {}
        assert position_manager.total_positions_opened == 0
    
    @pytest.mark.asyncio
    async def test_open_position(self, position_manager):
        """Pozisyon açma."""
        position = await position_manager.open_position(
            symbol='BTCUSDT',
            side=PositionSide.LONG,
            entry_price=50000.0,
            quantity=0.1,
            stop_loss=49000.0,
            take_profit=52000.0,
            signal_type='STRONG_BUY',
            signal_confidence=0.85
        )
        
        assert position.symbol == 'BTCUSDT'
        assert position.side == PositionSide.LONG
        assert position.entry_price == 50000.0
        assert len(position_manager.active_positions) == 1
        assert position_manager.total_positions_opened == 1
    
    @pytest.mark.asyncio
    async def test_close_position(self, position_manager):
        """Pozisyon kapatma."""
        # Pozisyon aç
        position = await position_manager.open_position(
            symbol='BTCUSDT',
            side=PositionSide.LONG,
            entry_price=50000.0,
            quantity=0.1,
            stop_loss=49000.0,
            take_profit=52000.0
        )
        
        position_id = position.position_id
        
        # Pozisyonu kapat
        closed = await position_manager.close_position(
            position_id=position_id,
            exit_price=52000.0,
            exit_reason=CloseReason.TAKE_PROFIT
        )
        
        assert closed.state == PositionState.CLOSED
        assert closed.realized_pnl > 0
        assert len(position_manager.active_positions) == 0
        assert position_manager.total_positions_closed == 1
    
    @pytest.mark.asyncio
    async def test_update_position(self, position_manager):
        """Pozisyon güncelleme."""
        # Pozisyon aç
        position = await position_manager.open_position(
            symbol='BTCUSDT',
            side=PositionSide.LONG,
            entry_price=50000.0,
            quantity=0.1
        )
        
        # Güncelle
        updated = await position_manager.update_position(
            position.position_id,
            51000.0
        )
        
        assert updated.last_price == 51000.0
        assert updated.unrealized_pnl > 0
    
    @pytest.mark.asyncio
    async def test_check_exit_conditions_stop_loss(self, position_manager):
        """Stop loss exit koşulu."""
        # Pozisyon aç
        position = await position_manager.open_position(
            symbol='BTCUSDT',
            side=PositionSide.LONG,
            entry_price=50000.0,
            quantity=0.1,
            stop_loss=49000.0
        )
        
        # Stop loss kontrolü
        exit_reason = await position_manager.check_exit_conditions(
            position.position_id,
            48500.0  # Stop loss'un altında
        )
        
        assert exit_reason == CloseReason.STOP_LOSS
    
    @pytest.mark.asyncio
    async def test_check_exit_conditions_take_profit(self, position_manager):
        """Take profit exit koşulu."""
        # Pozisyon aç
        position = await position_manager.open_position(
            symbol='BTCUSDT',
            side=PositionSide.LONG,
            entry_price=50000.0,
            quantity=0.1,
            take_profit=52000.0
        )
        
        # Take profit kontrolü
        exit_reason = await position_manager.check_exit_conditions(
            position.position_id,
            52500.0  # Take profit'in üstünde
        )
        
        assert exit_reason == CloseReason.TAKE_PROFIT
    
    @pytest.mark.asyncio
    async def test_get_active_positions(self, position_manager):
        """Aktif pozisyonları getirme."""
        # 2 pozisyon aç
        await position_manager.open_position(
            symbol='BTCUSDT',
            side=PositionSide.LONG,
            entry_price=50000.0,
            quantity=0.1
        )
        
        await position_manager.open_position(
            symbol='ETHUSDT',
            side=PositionSide.LONG,
            entry_price=3000.0,
            quantity=1.0
        )
        
        # Tüm pozisyonlar
        all_positions = position_manager.get_active_positions()
        assert len(all_positions) == 2
        
        # Sembol filtresi
        btc_positions = position_manager.get_active_positions(symbol='BTCUSDT')
        assert len(btc_positions) == 1
        assert btc_positions[0].symbol == 'BTCUSDT'
    
    @pytest.mark.asyncio
    async def test_calculate_total_exposure(self, position_manager):
        """Toplam exposure hesaplama."""
        # 2 pozisyon aç
        await position_manager.open_position(
            symbol='BTCUSDT',
            side=PositionSide.LONG,
            entry_price=50000.0,
            quantity=0.1  # 5000 USDT
        )
        
        await position_manager.open_position(
            symbol='ETHUSDT',
            side=PositionSide.LONG,
            entry_price=3000.0,
            quantity=1.0  # 3000 USDT
        )
        
        # Toplam exposure = 5000 + 3000 = 8000 USDT
        total = position_manager.calculate_total_exposure()
        assert abs(total - 8000.0) < 0.01
    
    @pytest.mark.asyncio
    async def test_calculate_total_risk(self, position_manager):
        """Toplam risk hesaplama."""
        # 2 pozisyon aç
        await position_manager.open_position(
            symbol='BTCUSDT',
            side=PositionSide.LONG,
            entry_price=50000.0,
            quantity=0.1,
            stop_loss=49000.0  # Risk: 100 USDT
        )
        
        await position_manager.open_position(
            symbol='ETHUSDT',
            side=PositionSide.LONG,
            entry_price=3000.0,
            quantity=1.0,
            stop_loss=2900.0  # Risk: 100 USDT
        )
        
        # Toplam risk = 100 + 100 = 200 USDT
        total_risk = position_manager.calculate_total_risk()
        assert abs(total_risk - 200.0) < 0.01
    
    @pytest.mark.asyncio
    async def test_get_statistics(self, position_manager):
        """İstatistikleri getirme."""
        # Pozisyon aç ve kapat
        position = await position_manager.open_position(
            symbol='BTCUSDT',
            side=PositionSide.LONG,
            entry_price=50000.0,
            quantity=0.1,
            stop_loss=49000.0,
            take_profit=52000.0
        )
        
        await position_manager.close_position(
            position.position_id,
            52000.0,
            CloseReason.TAKE_PROFIT
        )
        
        # Stats
        stats = position_manager.get_statistics()
        
        assert stats['total_opened'] == 1
        assert stats['total_closed'] == 1
        assert stats['active_positions'] == 0
        assert stats['total_profit'] > 0
        assert stats['net_profit'] > 0
    
    @pytest.mark.asyncio
    async def test_trailing_stop_integration(self, position_manager):
        """Trailing stop entegrasyonu."""
        # Trailing stop'lu pozisyon aç
        position = await position_manager.open_position(
            symbol='BTCUSDT',
            side=PositionSide.LONG,
            entry_price=50000.0,
            quantity=0.1,
            stop_loss=49000.0,
            trailing_stop_percent=2.0
        )
        
        initial_sl = position.stop_loss
        
        # Fiyat güncelle (yükseldi)
        await position_manager.update_position(position.position_id, 52000.0)
        
        # Trailing stop güncellenmeli
        assert position.stop_loss > initial_sl
    
    @pytest.mark.asyncio
    async def test_position_not_found_error(self, position_manager):
        """Pozisyon bulunamadı hatası."""
        with pytest.raises(ValueError):
            await position_manager.update_position('non-existent-id', 50000.0)
        
        with pytest.raises(ValueError):
            await position_manager.close_position(
                'non-existent-id',
                50000.0,
                CloseReason.MANUAL
            )


class TestRiskCalculations:
    """Risk hesaplama testleri."""
    
    def test_risk_reward_ratio_calculation(self, sample_position_data):
        """Risk/Reward oranı hesaplama."""
        position = Position(**sample_position_data)
        
        # Entry: 50000, SL: 49000, TP: 52000
        # Risk: 1000, Reward: 2000
        # RR Ratio = 2.0
        risk = position.get_risk_amount_usdt()
        reward = position.get_reward_amount_usdt()
        
        rr_ratio = reward / risk if risk > 0 else 0
        assert abs(rr_ratio - 2.0) < 0.01
    
    @pytest.mark.asyncio
    async def test_max_risk_per_position(self, position_manager):
        """Pozisyon başına maksimum risk."""
        # Risk %2 ile pozisyon
        account_balance = 10000.0  # USDT
        max_risk_percent = 2.0     # %2
        max_risk_amount = account_balance * (max_risk_percent / 100)  # 200 USDT
        
        # Position hesapla
        entry_price = 50000.0
        stop_loss = 49000.0
        risk_per_unit = entry_price - stop_loss  # 1000
        quantity = max_risk_amount / risk_per_unit  # 0.2
        
        position = await position_manager.open_position(
            symbol='BTCUSDT',
            side=PositionSide.LONG,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss
        )
        
        # Risk kontrolü
        actual_risk = position.get_risk_amount_usdt()
        assert abs(actual_risk - max_risk_amount) < 0.01


if __name__ == "__main__":
    print("Position Manager Testleri")
    print("=" * 60)
    print("\nTestleri çalıştırmak için:")
    print("pytest test_position_manager.py -v")
    print("\nTek bir test çalıştırmak için:")
    print("pytest test_position_manager.py::TestPositionClass::test_position_creation -v")
    print("\n" + "=" * 60)