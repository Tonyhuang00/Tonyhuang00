import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from binance.client import Client


@dataclass
class BotConfig:
    api_key: str
    api_secret: str
    symbol: str
    interval: str
    leverage: int
    base_order_usdt: float
    ema_fast: int
    ema_slow: int
    take_profit_pct: float
    stop_loss_pct: float
    lose_streak_cooldown: int
    cooldown_minutes: int
    win_streak_increase: int
    win_increase_factor: float
    min_order_usdt: float
    use_testnet: bool


@dataclass
class PositionState:
    side: Optional[str] = None
    entry_price: Optional[float] = None
    quantity: Optional[float] = None


class FuturesBot:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.client = Client(config.api_key, config.api_secret)
        if config.use_testnet:
            self.client.FUTURES_URL = "https://testnet.binancefuture.com/fapi"
        self.position = PositionState()
        self.win_streak = 0
        self.lose_streak = 0
        self.cooldown_until: Optional[datetime] = None

    def get_account_balance(self) -> float:
        balances = self.client.futures_account_balance()
        usdt_balance = next(
            (float(item["balance"]) for item in balances if item["asset"] == "USDT"),
            0.0,
        )
        return usdt_balance

    def get_mark_price(self) -> float:
        data = self.client.futures_mark_price(symbol=self.config.symbol)
        return float(data["markPrice"])

    def get_klines(self, limit: int) -> list[float]:
        klines = self.client.futures_klines(
            symbol=self.config.symbol,
            interval=self.config.interval,
            limit=limit,
        )
        return [float(kline[4]) for kline in klines]

    def ema(self, prices: list[float], period: int) -> float:
        multiplier = 2 / (period + 1)
        ema_value = prices[0]
        for price in prices[1:]:
            ema_value = (price - ema_value) * multiplier + ema_value
        return ema_value

    def calculate_order_usdt(self, balance: float) -> float:
        if balance < self.config.base_order_usdt:
            return max(balance * 0.9, self.config.min_order_usdt)
        if self.win_streak >= self.config.win_streak_increase:
            factor = 1 + (self.win_streak - self.config.win_streak_increase + 1) * self.config.win_increase_factor
            return self.config.base_order_usdt * factor
        return self.config.base_order_usdt

    def place_order(self, side: str, quantity: float) -> None:
        self.client.futures_change_leverage(
            symbol=self.config.symbol,
            leverage=self.config.leverage,
        )
        self.client.futures_create_order(
            symbol=self.config.symbol,
            side=side,
            type="MARKET",
            quantity=quantity,
        )

    def open_position(self, side: str, price: float, balance: float) -> None:
        order_usdt = self.calculate_order_usdt(balance)
        quantity = math.floor((order_usdt * self.config.leverage) / price * 1000) / 1000
        if quantity <= 0:
            return
        self.place_order(side, quantity)
        self.position = PositionState(side=side, entry_price=price, quantity=quantity)

    def close_position(self) -> float:
        if not self.position.side or not self.position.quantity:
            return 0.0
        close_side = "SELL" if self.position.side == "BUY" else "BUY"
        self.place_order(close_side, self.position.quantity)
        exit_price = self.get_mark_price()
        pnl = 0.0
        if self.position.side == "BUY":
            pnl = (exit_price - self.position.entry_price) * self.position.quantity
        else:
            pnl = (self.position.entry_price - exit_price) * self.position.quantity
        self.position = PositionState()
        return pnl

    def update_streaks(self, pnl: float) -> None:
        if pnl > 0:
            self.win_streak += 1
            self.lose_streak = 0
        elif pnl < 0:
            self.lose_streak += 1
            self.win_streak = 0
        if self.lose_streak >= self.config.lose_streak_cooldown:
            self.cooldown_until = datetime.utcnow() + timedelta(minutes=self.config.cooldown_minutes)
            self.lose_streak = 0

    def in_cooldown(self) -> bool:
        if not self.cooldown_until:
            return False
        if datetime.utcnow() >= self.cooldown_until:
            self.cooldown_until = None
            return False
        return True

    def should_close(self, current_price: float) -> bool:
        if not self.position.side or not self.position.entry_price:
            return False
        if self.position.side == "BUY":
            tp = self.position.entry_price * (1 + self.config.take_profit_pct)
            sl = self.position.entry_price * (1 - self.config.stop_loss_pct)
            return current_price >= tp or current_price <= sl
        tp = self.position.entry_price * (1 - self.config.take_profit_pct)
        sl = self.position.entry_price * (1 + self.config.stop_loss_pct)
        return current_price <= tp or current_price >= sl

    def get_signal(self) -> Optional[str]:
        prices = self.get_klines(limit=self.config.ema_slow + 5)
        ema_fast = self.ema(prices[-self.config.ema_fast :], self.config.ema_fast)
        ema_slow = self.ema(prices[-self.config.ema_slow :], self.config.ema_slow)
        if ema_fast > ema_slow:
            return "BUY"
        if ema_fast < ema_slow:
            return "SELL"
        return None

    def print_status(self, balance: float, mark_price: float) -> None:
        cooldown_text = "冷靜期中" if self.in_cooldown() else "交易中"
        position_text = "無持倉"
        if self.position.side:
            position_text = f"{self.position.side} @ {self.position.entry_price:.2f}"
        print(
            f"[{datetime.utcnow().isoformat()}] 資金: {balance:.2f} USDT | "
            f"狀態: {cooldown_text} | 持倉: {position_text} | 現價: {mark_price:.2f} | "
            f"連勝: {self.win_streak} 連輸: {self.lose_streak}"
        )

    def run(self) -> None:
        while True:
            balance = self.get_account_balance()
            mark_price = self.get_mark_price()
            self.print_status(balance, mark_price)

            if self.position.side and self.should_close(mark_price):
                pnl = self.close_position()
                self.update_streaks(pnl)

            if not self.position.side and not self.in_cooldown():
                signal = self.get_signal()
                if signal:
                    self.open_position(signal, mark_price, balance)

            time.sleep(5)


def load_config(path: str) -> BotConfig:
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    return BotConfig(**data)


if __name__ == "__main__":
    config = load_config("config.json")
    bot = FuturesBot(config)
    bot.run()
