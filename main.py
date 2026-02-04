import os
import time
import ccxt
import pandas as pd
import datetime
from flask import Flask
import threading

# Flask para mantener el bot 24/7 con UptimeRobot
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

SYMBOL = 'BTC/JPY'  # Par ajustado
SLEEP_TIME = 30     # Chequea cada 30 segundos

# Grid parameters (ajustados al precio actual de BTC/JPY ~11.5M JPY)
GRID_LOWER = 11200000.0   # Precio inferior del rango (JPY)
GRID_UPPER = 12000000.0   # Precio superior del rango (JPY)
NUM_GRIDS = 107           # Cantidad de grids (como en tu captura)
GRID_MODE = 'arithmetic'  # Modo aritmético
TRAILING_UP = True        # Trailing ascending (ajusta rango si precio sube)
GRID_INVEST_PCT = 0.05    # 5% del balance disponible para todo el grid

# Risk management
RISK_PER_TRADE = 0.10     # 10% max por trade individual
STOP_LOSS_PCT = -1.2      # -1.2% desde precio de entrada
TAKE_PROFIT_PCT = 1.5     # +1.5% desde precio de entrada
BINANCE_FEE = 0.001       # 0.1% fee por lado
COOLDOWN_AFTER_TRADE = 60 # 1 min cooldown

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

# Grid state
grid_levels = []
grid_orders = {}  # {level: {'type': 'buy/sell', 'amount': amt, 'executed': False}}

def initialize_grid():
    global grid_levels, grid_orders
    grid_levels = []
    step = (GRID_UPPER - GRID_LOWER) / NUM_GRIDS
    current = GRID_LOWER
    while current <= GRID_UPPER:
        grid_levels.append(round(current, 2))
        current += step

    grid_orders = {}
    for level in grid_levels:
        grid_orders[level] = {'type': 'buy' if level < get_price() else 'sell', 'amount': 0.0, 'executed': False}

def adjust_trailing_up(price):
    global GRID_LOWER, GRID_UPPER, grid_levels
    if TRAILING_UP and price > GRID_UPPER * 1.01:  # Si sube 1% por encima del upper
        shift = price - GRID_UPPER
        GRID_LOWER += shift
        GRID_UPPER += shift
        initialize_grid()  # Reconstruir rejilla

def get_price():
    try:
        return exchange.fetch_ticker(SYMBOL)['last']
    except Exception as e:
        print(f"Error precio: {e}", flush=True)
        return 0.0

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

def simulate_grid_trade(price):
    global usdt_balance, btc_balance, total_trades, total_profit, last_trade_time
    adjust_trailing_up(price)

    for level in grid_levels:
        order = grid_orders.get(level, None)
        if not order or order['executed']:
            continue

        if order['type'] == 'buy' and price <= level:
            amount = (usdt_balance * RISK_PER_TRADE) / level
            cost = amount * level
            fee = cost * BINANCE_FEE
            net_cost = cost + fee
            if net_cost <= usdt_balance:
                usdt_balance -= net_cost
                btc_balance += amount
                order['executed'] = True
                order['amount'] = amount
                total_trades += 1
                last_trade_time = time.time()
                log_trade('BUY GRID', level, amount, net_cost)

        elif order['type'] == 'sell' and price >= level:
            amount = order['amount']
            if btc_balance >= amount:
                revenue = amount * level
                fee = revenue * BINANCE_FEE
                net_revenue = revenue - fee
                profit_loss = net_revenue - (amount * level)
                usdt_balance += net_revenue
                btc_balance -= amount
                total_trades += 1
                total_profit += profit_loss
                order['executed'] = True
                last_trade_time = time.time()
                log_trade('SELL GRID', level, amount, net_revenue, profit_loss)

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
    initialize_grid()  # Crea la rejilla al iniciar
    while True:
        try:
            price = get_price()
            print(f"Precio BTC/JPY: {price:.2f}", flush=True)

            balance = get_account_balance(price)
            print(f"Balance → USDT: {balance['USDT']:.2f} | BTC: {balance['BTC']:.6f} | Total: {balance['Total']:.2f} | P/L: {balance['P/L']:.2f}", flush=True)

            simulate_grid_trade(price)

            print(f"Trades totales: {total_trades} | Ganancia acumulada: {total_profit:.2f}\n", flush=True)

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
            print(f"Error principal: {e}", flush=True)

        time.sleep(30)

if __name__ == "__main__":
    main()           




