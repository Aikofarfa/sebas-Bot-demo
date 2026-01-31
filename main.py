import os
import time
import ccxt
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator
import pandas as pd
import datetime
from flask import Flask
import threading

# Mini web server dummy para pings de UptimeRobot (mantiene el bot 24/7)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive! 🚀"  # Respuesta simple para confirmar que está corriendo

def run_flask():
    app.run(host='0.0.0.0', port=os.getenv('PORT', 8080))  # Usa puerto de Railway o 8080

# Inicia Flask en un thread separado para no bloquear el loop del bot
threading.Thread(target=run_flask, daemon=True).start()

# Configuración: Usamos Binance real para precios públicos (no necesita claves)
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',
    },
})

# NO usamos sandbox para paper trading (todo simulado)

SYMBOL = 'BTC/USDT'
TIMEFRAME = '15m'  # Cambiado a 15 minutos para señales más rápidas (antes '1h')
SHORT_PERIOD = 9  # Ajustado para timeframes cortos (antes 12)
LONG_PERIOD = 13   # Ajustado para timeframes cortos (antes 26)
RSI_PERIOD = 14
RSI_OVERBOUGHT = 60  # Ajustado para ser más estricto (antes 70)
RSI_OVERSOLD = 40    # Ajustado para ser más estricto (antes 30)
AMOUNT = 0.05      # Reducido para trades frecuentes (antes 0.001)
SLEEP_TIME = 30     # Cada 1 minuto para chequeos más rápidos (antes 300)

# Simulación de portfolio
initial_balance = 100.0  # USDT inicial
usdt_balance = initial_balance
btc_balance = 0.0
last_buy_price = 0.0  # Para calcular P&L por trade
total_trades = 0
total_profit = 0.0

def get_price():
    ticker = exchange.fetch_ticker(SYMBOL)
    return ticker['last']

def get_account_balance(current_price):
    # Balance simulado
    btc_value = btc_balance * current_price
    total_value = usdt_balance + btc_value
    return {
        'USDT': usdt_balance,
        'BTC': btc_balance,
        'Total_USDT': total_value,
        'Profit_Loss_Total': total_value - initial_balance
    }

def get_historical_data():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=LONG_PERIOD + RSI_PERIOD)
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
            print("Fondos insuficientes para compra simulada.")
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
            print("No hay suficiente BTC para venta simulada.")
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
        f"Cantidad: {amount} BTC | "
        f"{'Costo' if action == 'buy' else 'Ingreso'}: {cost_revenue:.2f} USDT | "
        f"P/L operación: {profit_loss:.2f} USDT | "
        f"USDT: {balance_usdt:.2f} | "
        f"BTC: {balance_btc:.4f} | "
        f"Total valor: {total_value:.2f} | "
        f"P/L acumulado: {total_pl:.2f}\n"
    )
    
    print(message.strip(), flush=True)  # Muestra en logs de Railway
    
    # Guardar en archivo (usa volume si lo configuras en Railway)
    with open('trades.log', 'a', encoding='utf-8') as f:
        f.write(message)

def main():
    global total_profit
    while True:
        try:
            price = get_price()
            print(f"Precio actual de BTC/USDT: {price}", flush=True)

            balance = get_account_balance(price)
            print(f"Estado simulado de la cuenta: USDT: {balance['USDT']}, BTC: {balance['BTC']}, Total en USDT: {balance['Total_USDT']}, Ganancia/Pérdida total: {balance['Profit_Loss_Total']}", flush=True)

            df = get_historical_data()
            sma_short, sma_long, rsi = calculate_indicators(df)

            if sma_short > sma_long and rsi < RSI_OVERSOLD and usdt_balance > 0:
                print("Señal de COMPRA simulada", flush=True)
                simulate_trade('buy', price)
            elif sma_short < sma_long and rsi > RSI_OVERBOUGHT and btc_balance > 0:
                print("Señal de VENTA simulada", flush=True)
                simulate_trade('sell', price)
            else:
                print("Sin señal de trade", flush=True)

            print(f"Trades totales: {total_trades}, Ganancia acumulada: {total_profit}", flush=True)

        except Exception as e:
            print(f"Error: {e}", flush=True)

        time.sleep(30)  # Ajustado para chequeos más rápidos

if __name__ == "__main__":
    main()




