import os
import time
import ccxt
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator
import pandas as pd

# Configuración: Usamos Binance real para precios públicos (no necesita claves)
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',
    },
})

# NO usamos sandbox para paper trading (todo simulado)

SYMBOL = 'BTC/USDT'
TIMEFRAME = '1h'  # Intervalo para datos históricos
SHORT_PERIOD = 12
LONG_PERIOD = 26
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
AMOUNT = 0.001  # Cantidad de BTC por trade (ajusta si quieres)

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
    if action == 'buy':
        cost = AMOUNT * price
        if usdt_balance >= cost:
            usdt_balance -= cost
            btc_balance += AMOUNT
            last_buy_price = price
            total_trades += 1
            print(f"Simulación COMPRA: {AMOUNT} BTC a {price} USDT. Costo: {cost} USDT.")
        else:
            print("Fondos insuficientes para compra simulada.")
            return 0.0
    elif action == 'sell':
        if btc_balance >= AMOUNT:
            revenue = AMOUNT * price
            usdt_balance += revenue
            btc_balance -= AMOUNT
            total_trades += 1
            profit_loss = revenue - (AMOUNT * last_buy_price)
            total_profit += profit_loss
            print(f"Simulación VENTA: {AMOUNT} BTC a {price} USDT. Ingreso: {revenue} USDT. Ganancia/Pérdida esta operación: {profit_loss} USDT.")
        else:
            print("No hay suficiente BTC para venta simulada.")
            return 0.0
    return profit_loss

def main():
    global total_profit
    while True:
        try:
            price = get_price()
            print(f"Precio actual de BTC/USDT: {price}")

            balance = get_account_balance(price)
            print(f"Estado simulado de la cuenta: USDT: {balance['USDT']}, BTC: {balance['BTC']}, Total en USDT: {balance['Total_USDT']}, Ganancia/Pérdida total: {balance['Profit_Loss_Total']}")

            df = get_historical_data()
            sma_short, sma_long, rsi = calculate_indicators(df)

            if sma_short > sma_long and rsi < RSI_OVERSOLD and usdt_balance > 0:
                print("Señal de COMPRA simulada")
                simulate_trade('buy', price)
            elif sma_short < sma_long and rsi > RSI_OVERBOUGHT and btc_balance > 0:
                print("Señal de VENTA simulada")
                simulate_trade('sell', price)
            else:
                print("Sin señal de trade")

            print(f"Trades totales: {total_trades}, Ganancia acumulada: {total_profit}")

        except Exception as e:
            print(f"Error: {e}")

        time.sleep(300)  # 5 minutos

if __name__ == "__main__":
    main()

