import os
import time
import ccxt
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator
import pandas as pd

# Configuración
exchange = ccxt.binance({
    'apiKey': os.getenv('BINANCE_API_KEY'),
    'secret': os.getenv('BINANCE_API_SECRET'),
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',  # Cambia a 'future' si quieres futuros
    },
})
exchange.set_sandbox_mode(True)  # Activa modo testnet

SYMBOL = 'BTC/USDT'
TIMEFRAME = '1h'  # Intervalo de velas: 1 hora
SHORT_PERIOD = 12  # Media móvil corta
LONG_PERIOD = 26  # Media móvil larga
RSI_PERIOD = 14  # Período RSI
RSI_OVERBOUGHT = 70  # Vender si RSI > 70
RSI_OVERSOLD = 30  # Comprar si RSI < 30
AMOUNT = 0.001  # Cantidad de BTC a operar (ajusta según fondos demo)

def get_price():
    ticker = exchange.fetch_ticker(SYMBOL)
    return ticker['last']

def get_account_balance():
    balance = exchange.fetch_balance()
    usdt = balance['USDT']['free'] if 'USDT' in balance else 0
    btc = balance['BTC']['free'] if 'BTC' in balance else 0
    return {'USDT': usdt, 'BTC': btc}

def get_historical_data():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=LONG_PERIOD + RSI_PERIOD)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    return df

def calculate_indicators(df):
    sma_short = SMAIndicator(df['close'], window=SHORT_PERIOD).sma_indicator()
    sma_long = SMAIndicator(df['close'], window=LONG_PERIOD).sma_indicator()
    rsi = RSIIndicator(df['close'], window=RSI_PERIOD).rsi()
    return sma_short.iloc[-1], sma_long.iloc[-1], rsi.iloc[-1]

def execute_trade(action):
    if action == 'buy':
        order = exchange.create_market_buy_order(SYMBOL, AMOUNT)
        print(f"Compra ejecutada: {order}")
    elif action == 'sell':
        order = exchange.create_market_sell_order(SYMBOL, AMOUNT)
        print(f"Venta ejecutada: {order}")

def main():
    while True:
        try:
            # Obtener precio actual
            price = get_price()
            print(f"Precio actual de BTC/USDT: {price}")

            # Obtener estado de cuenta
            balance = get_account_balance()
            print(f"Estado de la cuenta: USDT: {balance['USDT']}, BTC: {balance['BTC']}")

            # Obtener datos históricos
            df = get_historical_data()

            # Calcular indicadores
            sma_short, sma_long, rsi = calculate_indicators(df)

            # Lógica de la estrategia
            if sma_short > sma_long and rsi < RSI_OVERSOLD:
                print("Señal de COMPRA: MA corta > MA larga y RSI oversold")
                execute_trade('buy')
            elif sma_short < sma_long and rsi > RSI_OVERBOUGHT:
                print("Señal de VENTA: MA corta < MA larga y RSI overbought")
                execute_trade('sell')
            else:
                print("Sin señal de trade")

        except Exception as e:
            print(f"Error: {e}")

        time.sleep(300)  # Espera 5 minutos (ajusta según timeframe)

if __name__ == "__main__":
    main()