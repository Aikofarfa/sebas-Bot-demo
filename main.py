import os
import time
import ccxt
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import VolumeWeightedAveragePrice
import pandas as pd
import datetime
from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive! 🚀"

def run_flask():
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

threading.Thread(target=run_flask, daemon=True).start()

exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'},
})

SYMBOL = 'BTC/USDT'
TIMEFRAME = '5m'
SLEEP_TIME = 60

# Parámetros de riesgo
AMOUNT_PERCENT = 0.05        # 5% del capital por trade
COOLDOWN_AFTER_TRADE = 120   # segundos
STOP_LOSS_PCT = -1.0         # -1%
TAKE_PROFIT_PCT = 1.5        # +1.5%
BINANCE_FEE = 0.001          # 0.1%

# Portfolio
initial_balance = 100.0
usdt_balance = initial_balance
btc_balance = 0.0
position_open = False
entry_price = 0.0
last_trade_time = 0
total_trades = 0
winning_trades = 0
losing_trades = 0
total_profit = 0.0
max_drawdown = 0.0

# Grid parameters (para Grid Trading)
GRID_LEVELS = 5
GRID_RANGE_PCT = 2.0  # 2% rango alrededor del precio actual

def get_price():
    return exchange.fetch_ticker(SYMBOL)['last']

def get_account_balance(current_price):
    total_value = usdt_balance + btc_balance * current_price
    drawdown = (initial_balance - total_value) / initial_balance * 100 if initial_balance > 0 else 0
    global max_drawdown
    max_drawdown = max(max_drawdown, drawdown)
    return {
        'USDT': usdt_balance,
        'BTC': btc_balance,
        'Total': total_value,
        'P/L': total_value - initial_balance,
        'Drawdown': drawdown,
        'Max DD': max_drawdown
    }

def get_historical_data(limit=200):
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    return df

def calculate_indicators(df):
    ema9 = EMAIndicator(df['close'], 9).ema_indicator().iloc[-1]
    ema21 = EMAIndicator(df['close'], 21).ema_indicator().iloc[-1]
    rsi = RSIIndicator(df['close'], 14).rsi().iloc[-1]
    rsi_prev = RSIIndicator(df['close'], 14).rsi().iloc[-2]
    bb = BollingerBands(df['close'], window=20, window_dev=2)
    bb_lower = bb.bollinger_lband().iloc[-1]
    bb_upper = bb.bollinger_hband().iloc[-1]
    macd = MACD(df['close'])
    macd_line = macd.macd().iloc[-1]
    macd_signal = macd.macd_signal().iloc[-1]
    vwap = VolumeWeightedAveragePrice(high=df['high'], low=df['low'], close=df['close'], volume=df['volume']).volume_weighted_average_price().iloc[-1]
    atr = AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range().iloc[-1]
    volume_mean = df['volume'].rolling(20).mean().iloc[-1]
    return {
        'ema9': ema9,
        'ema21': ema21,
        'rsi': rsi,
        'rsi_prev': rsi_prev,
        'bb_lower': bb_lower,
        'bb_upper': bb_upper,
        'macd_line': macd_line,
        'macd_signal': macd_signal,
        'vwap': vwap,
        'atr': atr,
        'volume_mean': volume_mean
    }

def check_stop_loss_take_profit(current_price):
    global usdt_balance, btc_balance, position_open, total_profit, winning_trades, losing_trades
    if not position_open:
        return False

    pnl_pct = (current_price - entry_price) / entry_price * 100

    if pnl_pct <= STOP_LOSS_PCT or pnl_pct >= TAKE_PROFIT_PCT:
        revenue = btc_balance * current_price
        fee = revenue * BINANCE_FEE
        net_revenue = revenue - fee
        profit_loss = net_revenue - (btc_balance * entry_price)
        usdt_balance += net_revenue
        total_profit += profit_loss
        total_trades += 1
        if profit_loss >= 0: winning_trades += 1
        else: losing_trades += 1
        log_trade('SELL (SL/TP)', current_price, btc_balance, net_revenue, profit_loss)
        btc_balance = 0
        position_open = False
        return True

    return False

def simulate_buy(price):
    global usdt_balance, btc_balance, entry_price, last_trade_time, position_open, total_trades
    now = time.time()
    if now - last_trade_time < COOLDOWN_AFTER_TRADE:
        return

    max_usdt = usdt_balance * AMOUNT_PERCENT
    amount = max_usdt / price
    cost = amount * price
    fee = cost * BINANCE_FEE
    net_cost = cost + fee

    if net_cost <= usdt_balance:
        usdt_balance -= net_cost
        btc_balance += amount
        entry_price = price
        total_trades += 1
        position_open = True
        last_trade_time = now
        log_trade('BUY', price, amount, net_cost)
    else:
        print("Fondos insuficientes", flush=True)

def simulate_sell(price):
    global usdt_balance, btc_balance, total_profit, winning_trades, losing_trades, position_open, last_trade_time
    now = time.time()
    if now - last_trade_time < COOLDOWN_AFTER_TRADE:
        return

    revenue = btc_balance * price
    fee = revenue * BINANCE_FEE
    net_revenue = revenue - fee
    profit_loss = net_revenue - (btc_balance * entry_price)
    usdt_balance += net_revenue
    total_profit += profit_loss
    total_trades += 1
    if profit_loss >= 0: winning_trades += 1
    else: losing_trades += 1
    log_trade('SELL', price, btc_balance, net_revenue, profit_loss)
    btc_balance = 0
    position_open = False
    last_trade_time = now

def log_trade(action, price, amount, net_cost_revenue, profit_loss=0.0):
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_value = usdt_balance + btc_balance * price
    message = (
        f"[{now_str}] {action} | Precio: {price:.2f} | Cant: {amount:.6f} | Neto: {net_cost_revenue:.2f} | P/L: {profit_loss:.2f} | "
        f"USDT: {usdt_balance:.2f} | BTC: {btc_balance:.6f} | Total: {total_value:.2f} | P/L total: {total_value - initial_balance:.2f}\n"
    )
    print(message.strip(), flush=True)

    try:
        with open('/data/trades.log', 'a', encoding='utf-8') as f:
            f.write(message)
    except Exception as e:
        print(f"Error log: {e}", flush=True)

def main():
    global total_profit
    while True:
        try:
            price = get_price()
            print(f"Precio: {price:.2f}", flush=True)

            balance = get_account_balance(price)
            print(f"Balance → USDT: {balance['USDT']:.2f} | BTC: {balance['BTC']:.6f} | Total: {balance['Total']:.2f} | P/L: {balance['P/L']:.2f}", flush=True)

            if check_stop_loss_take_profit(price):
                print("SL/TP ejecutado", flush=True)

            df = get_historical_data(200)
            indicators = calculate_indicators(df)

            print(f"DEBUG → EMA9: {indicators['ema9']:.2f} | EMA21: {indicators['ema21']:.2f} | RSI: {indicators['rsi']:.2f} | BB lower: {indicators['bb_lower']:.2f}", flush=True)

            buy_signal = False
            sell_signal = False

            # Estrategias combinadas
            if indicators['ema9'] > indicators['ema21'] and indicators['rsi'] < RSI_BUY_LEVEL:
                buy_signal = True
            if indicators['rsi'] < 30 and indicators['rsi'] > indicators['rsi_prev']:
                buy_signal = True
            if price < indicators['bb_lower'] and indicators['rsi'] < 40:
                buy_signal = True
            if indicators['macd_line'] > indicators['macd_signal'] and indicators['macd_line'] > 0:
                buy_signal = True

            if indicators['ema9'] < indicators['ema21'] and indicators['rsi'] > RSI_SELL_LEVEL:
                sell_signal = True
            if indicators['rsi'] > 70 and indicators['rsi'] < indicators['rsi_prev']:
                sell_signal = True
            if price > indicators['bb_upper']:
                sell_signal = True
            if indicators['macd_line'] < indicators['macd_signal'] and indicators['macd_line'] < 0:
                sell_signal = True

            if buy_signal and not position_open:
                print(">>> COMPRA <<<", flush=True)
                simulate_buy(price)
            elif sell_signal and position_open:
                print(">>> VENTA <<<", flush=True)
                simulate_sell(price)

            winrate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            print(f"Trades: {total_trades} | Winrate: {winrate:.1f}% | P/L: {total_profit:.2f}", flush=True)

            # Mostrar últimos trades
            try:
                with open('/data/trades.log', 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if lines:
                        print("Últimos:\n" + ''.join(lines[-3:]), flush=True)
            except:
                print("Sin trades aún", flush=True)

        except Exception as e:
            print(f"Error: {e}", flush=True)

        time.sleep(60)

if __name__ == "__main__":
    main()
