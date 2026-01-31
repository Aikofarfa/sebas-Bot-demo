import os
import time
import ccxt
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
import pandas as pd
import datetime
from flask import Flask
import threading

# Flask para UptimeRobot (mantiene 24/7)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive! 🚀"

def run_flask():
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

threading.Thread(target=run_flask, daemon=True).start()

# Configuración Binance (datos públicos)
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'},
})

SYMBOL = 'BTC/USDT'
TIMEFRAME = '5m'
SHORT_EMA = 9
LONG_EMA = 21
RSI_PERIOD = 14
RSI_BUY_LEVEL = 35
RSI_SELL_LEVEL = 65
AMOUNT_PERCENT = 0.10       # Riesgo máximo 10% del capital por trade
SLEEP_TIME = 60             # Cada 1 minuto

# Stop Loss y Take Profit
STOP_LOSS_PCT = -1.0        # -1%
TAKE_PROFIT_PCT = 1.8       # +1.8%
BINANCE_FEE = 0.001         # 0.1% por lado
COOLDOWN_AFTER_TRADE = 300  # 5 min cooldown
MAX_POSITION_TIME = 1800    # 30 min máximo en posición (venta forzada)

# Portfolio simulado
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

def get_price():
    try:
        return exchange.fetch_ticker(SYMBOL)['last']
    except Exception as e:
        print(f"Error precio: {e}", flush=True)
        return 0.0

def get_account_balance(current_price):
    total_value = usdt_balance + btc_balance * current_price
    drawdown = ((initial_balance - total_value) / initial_balance) * 100 if initial_balance > 0 else 0
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

def get_historical_data():
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=LONG_EMA + RSI_PERIOD + 10)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df
    except Exception as e:
        print(f"Error datos: {e}", flush=True)
        return pd.DataFrame()

def calculate_indicators(df):
    if df.empty:
        return 0.0, 0.0, 50.0, 0.0
    ema_short = EMAIndicator(df['close'], window=SHORT_EMA).ema_indicator().iloc[-1]
    ema_long = EMAIndicator(df['close'], window=LONG_EMA).ema_indicator().iloc[-1]
    rsi = RSIIndicator(df['close'], window=RSI_PERIOD).rsi().iloc[-1]
    ema_200 = EMAIndicator(df['close'], window=200).ema_indicator().iloc[-1]
    return ema_short, ema_long, rsi, ema_200

def check_stop_loss_take_profit(current_price):
    global usdt_balance, btc_balance, position_open, total_profit, winning_trades, losing_trades, last_trade_time
    if not position_open:
        return False

    pnl_pct = (current_price - entry_price) / entry_price * 100

    if pnl_pct <= STOP_LOSS_PCT:
        revenue = btc_balance * current_price
        fee = revenue * BINANCE_FEE
        net_revenue = revenue - fee
        profit_loss = net_revenue - (btc_balance * entry_price)
        usdt_balance += net_revenue
        total_profit += profit_loss
        total_trades += 1
        if profit_loss >= 0: winning_trades += 1
        else: losing_trades += 1
        log_trade('SELL (SL)', current_price, btc_balance, net_revenue, profit_loss)
        btc_balance = 0
        position_open = False
        last_trade_time = time.time()
        return True

    if pnl_pct >= TAKE_PROFIT_PCT:
        revenue = btc_balance * current_price
        fee = revenue * BINANCE_FEE
        net_revenue = revenue - fee
        profit_loss = net_revenue - (btc_balance * entry_price)
        usdt_balance += net_revenue
        total_profit += profit_loss
        winning_trades += 1
        log_trade('SELL (TP)', current_price, btc_balance, net_revenue, profit_loss)
        btc_balance = 0
        position_open = False
        last_trade_time = time.time()
        return True

    # Salida forzada por tiempo
    if time.time() - last_trade_time > MAX_POSITION_TIME:
        revenue = btc_balance * current_price
        fee = revenue * BINANCE_FEE
        net_revenue = revenue - fee
        profit_loss = net_revenue - (btc_balance * entry_price)
        usdt_balance += net_revenue
        total_profit += profit_loss
        total_trades += 1
        if profit_loss >= 0: winning_trades += 1
        else: losing_trades += 1
        log_trade('SELL (Time Exit)', current_price, btc_balance, net_revenue, profit_loss)
        btc_balance = 0
        position_open = False
        last_trade_time = time.time()
        return True

    return False

def simulate_trade(action, price):
    global usdt_balance, btc_balance, last_buy_price, total_trades, total_profit, position_open, entry_price, last_trade_time

    now = time.time()
    if now - last_trade_time < COOLDOWN_AFTER_TRADE:
        print("Cooldown activo...", flush=True)
        return

    if action == 'buy' and not position_open:
        max_usdt = usdt_balance * RISK_PER_TRADE
        amount = max_usdt / price
        cost = amount * price
        fee = cost * BINANCE_FEE
        net_cost = cost + fee
        if net_cost <= usdt_balance:
            usdt_balance -= net_cost
            btc_balance += amount
            entry_price = price
            last_buy_price = price
            total_trades += 1
            position_open = True
            last_trade_time = now
            log_trade('BUY', price, amount, net_cost)
        else:
            print(f"Sin fondos para {RISK_PER_TRADE*100}% del capital", flush=True)

    elif action == 'sell' and position_open:
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
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_value = usdt_balance + btc_balance * price
    message = (
        f"[{now}] {action} | Precio: {price:.2f} | Cant: {amount:.6f} | Neto: {net_cost_revenue:.2f} | "
        f"P/L op: {profit_loss:.2f} | USDT: {usdt_balance:.2f} | BTC: {btc_balance:.6f} | "
        f"Total: {total_value:.2f} | P/L total: {total_value - initial_balance:.2f}\n"
    )
    print(message.strip(), flush=True)

    log_path = '/data/trades.log'
    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(message)
        print(f"Guardado en {log_path} ✅", flush=True)
    except Exception as e:
        print(f"Error log: {e}", flush=True)

def main():
    global total_profit
    while True:
        try:
            price = get_price()
            if price == 0.0:
                print("No se pudo obtener precio, reintentando...", flush=True)
                time.sleep(10)
                continue

            print(f"Precio BTC/USDT: {price:.2f}", flush=True)

            balance = get_account_balance(price)
            print(f"Balance → USDT: {balance['USDT']:.2f} | BTC: {balance['BTC']:.6f} | "
                  f"Total: {balance['Total']:.2f} | P/L: {balance['P/L']:.2f} | "
                  f"DD: {balance['Drawdown']:.2f}% | Max DD: {balance['Max DD']:.2f}%", flush=True)

            if check_stop_loss_take_profit(price):
                print("SL/TP o Time Exit ejecutado", flush=True)

            df = get_historical_data()
            ema_short, ema_long, rsi, ema_200 = calculate_indicators(df)

            print(f"DEBUG → EMA9: {ema_short:.2f} | EMA21: {ema_long:.2f} | RSI: {rsi:.2f} | EMA200: {ema_200:.2f}", flush=True)

            buy_signal = False
            sell_signal = False

            # Estrategia principal
            if ema_short > ema_long and rsi < RSI_BUY_LEVEL and price > ema_200 and usdt_balance > 0:
                buy_signal = True
            if ema_short < ema_long and rsi > RSI_SELL_LEVEL and btc_balance > 0:
                sell_signal = True

            if buy_signal and not position_open:
                print(">>> SEÑAL DE COMPRA <<<", flush=True)
                simulate_trade('buy', price)
            elif sell_signal and position_open:
                print(">>> SEÑAL DE VENTA <<<", flush=True)
                simulate_trade('sell', price)
            else:
                print("Sin señal válida", flush=True)

            winrate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            print(f"Trades: {total_trades} | Winrate: {winrate:.1f}% | Ganancia acumulada: {total_profit:.2f}\n", flush=True)

            # Mostrar últimos trades
            try:
                with open('/data/trades.log', 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if lines:
                        print("Últimos trades:\n" + ''.join(lines[-3:]), flush=True)
                    else:
                        print("Aún no hay trades en /data/trades.log", flush=True)
            except FileNotFoundError:
                print("Aún no existe /data/trades.log (se creará en el primer trade)", flush=True)
            except Exception as e:
                print(f"Error leyendo log: {e}", flush=True)

        except Exception as e:
            print(f"Error en ciclo principal: {e}", flush=True)

        time.sleep(50)

if __name__ == "__main__":
    main()

