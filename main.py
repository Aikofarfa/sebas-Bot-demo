import os
import time
import ccxt
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator
import pandas as pd
import datetime
from flask import Flask
import threading

# Mini servidor Flask para mantener el bot vivo con UptimeRobot
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive! 🚀"

def run_flask():
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# Iniciar Flask en hilo separado
threading.Thread(target=run_flask, daemon=True).start()

# Configuración de Binance (solo datos públicos)
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',
    },
})

SYMBOL = 'BTC/USDT'
TIMEFRAME = '15m'
SHORT_PERIOD = 9
LONG_PERIOD = 13
RSI_PERIOD = 14
RSI_OVERBOUGHT = 60
RSI_OVERSOLD = 40
AMOUNT = 0.0005      # ← Ajustado a valor realista (antes 0.05 era imposible con 100 USDT)
SLEEP_TIME = 30

# Portfolio simulado
initial_balance = 100.0
usdt_balance = initial_balance
btc_balance = 0.0
last_buy_price = 0.0
total_trades = 0
total_profit = 0.0

def get_price():
    ticker = exchange.fetch_ticker(SYMBOL)
    return ticker['last']

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
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=LONG_PERIOD + RSI_PERIOD + 10)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    return df

def calculate_indicators(df):
    sma_short = SMAIndicator(df['close'], window=SHORT_PERIOD).sma_indicator()
    sma_long = SMAIndicator(df['close'], window=LONG_PERIOD).sma_indicator()
    rsi = RSIIndicator(df['close'], window=RSI_PERIOD).rsi()
    return sma_short.iloc[-1], sma_long.iloc[-1], rsi.iloc[-1]

def simulate_trade(action, price):
    global usdt_balance, btc_balance, last_buy_price, total_trades, total_profit
    profit_loss = 0.0
    cost_revenue = 0.0

    if action == 'buy':
        cost_revenue = AMOUNT * price
        if usdt_balance >= cost_revenue:
            usdt_balance -= cost_revenue
            btc_balance += AMOUNT
            last_buy_price = price
            total_trades += 1
            log_trade('buy', price, AMOUNT, cost_revenue)
        else:
            print(f"Fondos insuficientes para compra: {usdt_balance:.2f} < {cost_revenue:.2f}", flush=True)
            return 0.0

    elif action == 'sell':
        if btc_balance >= AMOUNT:
            cost_revenue = AMOUNT * price
            usdt_balance += cost_revenue
            btc_balance -= AMOUNT
            total_trades += 1
            profit_loss = cost_revenue - (AMOUNT * last_buy_price)
            total_profit += profit_loss
            log_trade('sell', price, AMOUNT, cost_revenue, profit_loss)
        else:
            print(f"No hay suficiente BTC para venta: {btc_balance:.6f} < {AMOUNT}", flush=True)
            return 0.0

    return profit_loss

def log_trade(action, price, amount, cost_revenue, profit_loss=0.0):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    balance_usdt = usdt_balance
    balance_btc = btc_balance
    total_value = balance_usdt + (balance_btc * price)
    total_pl = total_value - initial_balance

    message = (
        f"[{now}] {action.upper()} | "
        f"Precio: {price:.2f} | "
        f"Cantidad: {amount:.6f} BTC | "
        f"{'Costo' if action == 'buy' else 'Ingreso'}: {cost_revenue:.2f} USDT | "
        f"P/L operación: {profit_loss:.2f} USDT | "
        f"USDT: {balance_usdt:.2f} | "
        f"BTC: {balance_btc:.6f} | "
        f"Total valor: {total_value:.2f} | "
        f"P/L acumulado: {total_pl:.2f}\n"
    )

    print(message.strip(), flush=True)

    # Guardado en volumen persistente
    log_path = '/data/trades.log'
    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(message)
        print(f"→ Trade guardado en {log_path}", flush=True)
    except Exception as e:
        print(f"Error escribiendo en {log_path}: {e}", flush=True)

def main():
    global total_profit
    while True:
        try:
            price = get_price()
            print(f"Precio actual BTC/USDT: {price:.2f}", flush=True)

            balance = get_account_balance(price)
            print(f"Estado simulado → USDT: {balance['USDT']:.2f} | BTC: {balance['BTC']:.6f} | Total: {balance['Total_USDT']:.2f} | P/L: {balance['Profit_Loss_Total']:.2f}", flush=True)

            df = get_historical_data()
            sma_short, sma_long, rsi = calculate_indicators(df)

            print(f"DEBUG → SMA corta: {sma_short:.2f} | SMA larga: {sma_long:.2f} | RSI: {rsi:.2f}", flush=True)

            if sma_short > sma_long and rsi < RSI_OVERSOLD and usdt_balance > 0:
                print(">>> SEÑAL DE COMPRA SIMULADA <<<", flush=True)
                simulate_trade('buy', price)
            elif sma_short < sma_long and rsi > RSI_OVERBOUGHT and btc_balance > 0:
                print(">>> SEÑAL DE VENTA SIMULADA <<<", flush=True)
                simulate_trade('sell', price)
            else:
                print("Sin señal válida", flush=True)

            print(f"Trades totales: {total_trades} | Ganancia acumulada: {total_profit:.2f}", flush=True)

            # Mostrar últimos trades guardados
            log_path = '/data/trades.log'
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if lines:
                        last_5 = ''.join(lines[-5:]).strip()
                        print(f"Últimos 5 trades:\n{last_5}\n", flush=True)
                    else:
                        print(f"{log_path} existe pero está vacío.\n", flush=True)
            except FileNotFoundError:
                print(f"Aún no existe {log_path} (se creará al primer trade)\n", flush=True)
            except IsADirectoryError:
                print(f"ERROR: {log_path} es un directorio, no archivo. Revisa configuración del volumen.\n", flush=True)
            except Exception as e:
                print(f"Error leyendo {log_path}: {e}\n", flush=True)

        except Exception as e:
            print(f"Error en ciclo principal: {e}", flush=True)

        time.sleep(60)

if __name__ == "__main__":
    main()






