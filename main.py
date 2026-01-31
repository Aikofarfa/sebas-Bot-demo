import os
import time
import ccxt
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
import pandas as pd
import datetime
from flask import Flask
import threading

# Flask para mantener el bot vivo con UptimeRobot
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive! 🚀"

def run_flask():
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

threading.Thread(target=run_flask, daemon=True).start()

# Configuración de Binance (datos públicos)
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
AMOUNT = 0.0003          # Realista: ~25 USDT con BTC ~84k
SLEEP_TIME = 60          # Cada 1 minuto - buen equilibrio

# Portfolio simulado
initial_balance = 100.0
usdt_balance = initial_balance
btc_balance = 0.0
last_buy_price = 0.0
total_trades = 0
total_profit = 0.0
last_trade_time = 0
COOLDOWN = 300           # 5 minutos cooldown después de trade

def get_price():
    try:
        ticker = exchange.fetch_ticker(SYMBOL)
        return ticker['last']
    except Exception as e:
        print(f"Error obteniendo precio: {e}", flush=True)
        return 0.0

def get_account_balance(current_price):
    try:
        btc_value = btc_balance * current_price
        total_value = usdt_balance + btc_value
        return {
            'USDT': usdt_balance,
            'BTC': btc_balance,
            'Total_USDT': total_value,
            'Profit_Loss_Total': total_value - initial_balance
        }
    except Exception as e:
        print(f"Error calculando balance: {e}", flush=True)
        return {
            'USDT': usdt_balance,
            'BTC': btc_balance,
            'Total_USDT': 0.0,
            'Profit_Loss_Total': 0.0
        }

def get_historical_data():
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=LONG_EMA + RSI_PERIOD + 10)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df
    except Exception as e:
        print(f"Error obteniendo datos históricos: {e}", flush=True)
        return pd.DataFrame()

def calculate_indicators(df):
    if df.empty:
        return 0.0, 0.0, 50.0  # Valores neutros por defecto
    
    ema_short = EMAIndicator(df['close'], window=SHORT_EMA).ema_indicator().iloc[-1]
    ema_long = EMAIndicator(df['close'], window=LONG_EMA).ema_indicator().iloc[-1]
    rsi = RSIIndicator(df['close'], window=RSI_PERIOD).rsi().iloc[-1]
    
    return ema_short, ema_long, rsi

def simulate_trade(action, price):
    global usdt_balance, btc_balance, last_buy_price, total_trades, total_profit, last_trade_time
    
    now = time.time()
    if now - last_trade_time < COOLDOWN:
        print("Cooldown activo, esperando...", flush=True)
        return

    profit_loss = 0.0
    cost_revenue = 0.0

    if action == 'buy':
        cost_revenue = AMOUNT * price
        if usdt_balance >= cost_revenue:
            usdt_balance -= cost_revenue
            btc_balance += AMOUNT
            last_buy_price = price
            total_trades += 1
            last_trade_time = now
            log_trade('buy', price, AMOUNT, cost_revenue)
        else:
            print(f"Sin fondos para compra: {usdt_balance:.2f} < {cost_revenue:.2f}", flush=True)
    
    elif action == 'sell':
        if btc_balance >= AMOUNT:
            cost_revenue = AMOUNT * price
            usdt_balance += cost_revenue
            btc_balance -= AMOUNT
            total_trades += 1
            profit_loss = cost_revenue - (AMOUNT * last_buy_price)
            total_profit += profit_loss
            last_trade_time = now
            log_trade('sell', price, AMOUNT, cost_revenue, profit_loss)
        else:
            print(f"Sin BTC para venta: {btc_balance:.6f} < {AMOUNT}", flush=True)

def log_trade(action, price, amount, cost_revenue, profit_loss=0.0):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_total = usdt_balance + btc_balance * price
    message = (
        f"[{now}] {action.upper()} | Precio: {price:.2f} | Cantidad: {amount:.6f} BTC | "
        f"{'Costo' if action == 'buy' else 'Ingreso'}: {cost_revenue:.2f} USDT | "
        f"P/L operación: {profit_loss:.2f} USDT | "
        f"USDT: {usdt_balance:.2f} | BTC: {btc_balance:.6f} | "
        f"Total valor: {current_total:.2f} | P/L acumulado: {current_total - initial_balance:.2f}\n"
    )
    
    print(message.strip(), flush=True)
    
    log_path = '/data/trades.log'
    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(message)
        print(f"Trade guardado en {log_path} ✅", flush=True)
    except Exception as e:
        print(f"Error al guardar en {log_path}: {e}", flush=True)

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
            print(f"Estado simulado → USDT: {balance['USDT']:.2f} | BTC: {balance['BTC']:.6f} | "
                  f"Total: {balance['Total_USDT']:.2f} | P/L total: {balance['Profit_Loss_Total']:.2f}", flush=True)

            df = get_historical_data()
            ema_short, ema_long, rsi = calculate_indicators(df)

            print(f"DEBUG → EMA9: {ema_short:.2f} | EMA21: {ema_long:.2f} | RSI: {rsi:.2f}", flush=True)

            if ema_short > ema_long and rsi < RSI_BUY_LEVEL and usdt_balance > 0:
                print(">>> SEÑAL DE COMPRA SIMULADA <<<", flush=True)
                simulate_trade('buy', price)
            elif ema_short < ema_long and rsi > RSI_SELL_LEVEL and btc_balance > 0:
                print(">>> SEÑAL DE VENTA SIMULADA <<<", flush=True)
                simulate_trade('sell', price)
            else:
                print("Sin señal de trade", flush=True)

            print(f"Trades totales: {total_trades} | Ganancia acumulada: {total_profit:.2f}\n", flush=True)

            # Mostrar últimos trades guardados
            try:
                with open('/data/trades.log', 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if lines:
                        last_lines = ''.join(lines[-3:])
                        print(f"Últimos trades:\n{last_lines}", flush=True)
                    else:
                        print("Aún no hay trades guardados en /data/trades.log", flush=True)
            except FileNotFoundError:
                print("Aún no existe /data/trades.log (se creará en el primer trade)", flush=True)
            except Exception as e:
                print(f"Error leyendo log: {e}", flush=True)

        except Exception as e:
            print(f"Error en ciclo principal: {e}", flush=True)

        time.sleep(60)

if __name__ == "__main__":
    main()    
