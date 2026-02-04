import os
import time
import ccxt
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
import pandas as pd
import datetime
from flask import Flask
import threading

# Flask para UptimeRobot
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive! 🚀"

def run_flask():
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

threading.Thread(target=run_flask, daemon=True).start()

# Configuración Binance pública
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'},
})

SYMBOL = 'BTC/JPY'           # Cambiado a BTC/JPY para mayor ganancia
TIMEFRAME = '5m'             # Rápido
SHORT_EMA = 7                # Más sensible
LONG_EMA = 21
RSI_PERIOD = 9               # RSI más corto para adaptarse rápido
RSI_BUY_LEVEL = 40           # Compra si RSI < 40 (más entradas)
RSI_SELL_LEVEL = 60          # Vende si RSI > 60 (más salidas)
RISK_PERCENT = 0.10          # Riesgo máximo 10% del balance por trade
SLEEP_TIME = 30              # Chequea cada 30 segundos
COOLDOWN_AFTER_TRADE = 30    # 30 segundos cooldown
MAX_POSITION_TIME = 600      # 10 minutos máximo en posición (venta forzada)
STOP_LOSS_PCT = -0.8         # Cierra si pierde 0.8%
TAKE_PROFIT_PCT = 1.5        # Cierra si gana 1.5% o más

# Portfolio simulado
initial_balance = 100.0
usdt_balance = initial_balance
btc_balance = 0.0
last_buy_price = 0.0
total_trades = 0
total_profit = 0.0
last_trade_time = 0

def get_price():
    try:
        return exchange.fetch_ticker(SYMBOL)['last']
    except Exception as e:
        print(f"Error precio: {e}", flush=True)
        return 0.0

def get_account_balance(current_price):
    btc_value = btc_balance * current_price
    total_value = usdt_balance + btc_value
    return {
        'USDT': usdt_balance,
        'BTC': btc_balance,
        'Total_USDT': total_value,
        'Profit_Loss_Total': total_value - initial_balance
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
        return 0.0, 0.0, 50.0
    ema_short = EMAIndicator(df['close'], window=SHORT_EMA).ema_indicator().iloc[-1]
    ema_long = EMAIndicator(df['close'], window=LONG_EMA).ema_indicator().iloc[-1]
    rsi = RSIIndicator(df['close'], window=RSI_PERIOD).rsi().iloc[-1]
    return ema_short, ema_long, rsi

def simulate_trade(action, price):
    global usdt_balance, btc_balance, last_buy_price, total_trades, total_profit, last_trade_time

    now = time.time()
    if now - last_trade_time < COOLDOWN_AFTER_TRADE:
        print("Cooldown activo...", flush=True)
        return

    # Calcular cantidad para apuntar a ~1 USD o más de ganancia
    target_gain_usd = 1.0  # Mínimo 1 USD por operación
    target_pct = TAKE_PROFIT_PCT / 100
    amount = (target_gain_usd / target_pct) / price  # cantidad BTC para ganar ~1 USD al TP

    profit_loss = 0.0
    cost_revenue = 0.0

    if action == 'buy':
        cost = amount * price
        fee = cost * 0.001
        net_cost = cost + fee
        if usdt_balance >= net_cost:
            usdt_balance -= net_cost
            btc_balance += amount
            last_buy_price = price
            total_trades += 1
            last_trade_time = now
            log_trade('buy', price, amount, net_cost)
        else:
            print(f"Sin fondos para compra: {usdt_balance:.2f} < {net_cost:.2f}", flush=True)

    elif action == 'sell':
        if btc_balance >= amount:
            revenue = amount * price
            fee = revenue * 0.001
            net_revenue = revenue - fee
            profit_loss = net_revenue - (amount * last_buy_price)
            usdt_balance += net_revenue
            btc_balance -= amount
            total_trades += 1
            total_profit += profit_loss
            last_trade_time = now
            log_trade('sell', price, amount, net_revenue, profit_loss)
        else:
            print(f"Sin BTC para venta: {btc_balance:.6f} < {amount}", flush=True)

def log_trade(action, price, amount, net_cost_revenue, profit_loss=0.0):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_total = usdt_balance + btc_balance * price
    message = (
        f"[{now}] {action.upper()} | Precio: {price:.2f} | Cantidad: {amount:.6f} BTC | "
        f"{'Costo' if action == 'buy' else 'Ingreso'}: {net_cost_revenue:.2f} USDT | "
        f"P/L op: {profit_loss:.2f} | USDT: {usdt_balance:.2f} | BTC: {btc_balance:.6f} | "
        f"Total: {current_total:.2f} | P/L total: {current_total - initial_balance:.2f}\n"
    )

    print(message.strip(), flush=True)

    log_path = '/data/trades.log'
    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(message)
        print(f"Guardado en {log_path}", flush=True)
    except Exception as e:
        print(f"Error guardando: {e}", flush=True)

def main():
    global total_profit
    while True:
        try:
            price = get_price()
            print(f"Precio BTC/JPY: {price:.2f}", flush=True)

            balance = get_account_balance(price)
            print(f"Balance: USDT {balance['USDT']:.2f} | BTC {balance['BTC']:.6f} | Total {balance['Total_USDT']:.2f} | P/L {balance['Profit_Loss_Total']:.2f}", flush=True)

            df = get_historical_data()
            ema_short, ema_long, rsi = calculate_indicators(df)

            print(f"DEBUG → EMA9: {ema_short:.2f} | EMA21: {ema_long:.2f} | RSI: {rsi:.2f}", flush=True)

            if ema_short > ema_long and rsi < RSI_BUY_LEVEL and usdt_balance > 0:
                print(">>> COMPRA SIMULADA <<<", flush=True)
                simulate_trade('buy', price)
            elif ema_short < ema_long and rsi > RSI_SELL_LEVEL and btc_balance > 0:
                print(">>> VENTA SIMULADA <<<", flush=True)
                simulate_trade('sell', price)
            else:
                print("Sin señal", flush=True)

            print(f"Trades: {total_trades} | Ganancia acumulada: {total_profit:.2f}\n", flush=True)

            # Mostrar últimos trades
            try:
                with open('/data/trades.log', 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if lines:
                        print("Últimos trades:\n" + ''.join(lines[-3:]), flush=True)
            except FileNotFoundError:
                print("Aún sin trades en /data/trades.log\n", flush=True)
            except Exception as e:
                print(f"Error leyendo log: {e}\n", flush=True)

        except Exception as e:
            print(f"Error: {e}", flush=True)

        time.sleep(15)

if __name__ == "__main__":
    main()





