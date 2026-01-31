import os
import time
import ccxt
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator
import pandas as pd

# Configuración del exchange con fix para Spot Testnet 2026
exchange = ccxt.binance({
    'apiKey': os.getenv('BINANCE_API_KEY'),
    'secret': os.getenv('BINANCE_API_SECRET'),
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',  # spot para BTC/USDT normal
    },
})

# Forzar URLs del Spot Testnet actualizadas (soluciona Invalid API-key -2015 en peticiones privadas)
exchange.urls['api'] = {
    'public': 'https://testnet.binance.vision/api',
    'private': 'https://testnet.binance.vision/api',
    'sapi': 'https://testnet.binance.vision/sapi',  # por si se usa en algún endpoint futuro
    # Si ves errores en ws o streams, puedes agregar:
    # 'ws': 'wss://testnet.binance.vision/ws',
}

# Activar modo sandbox/demo SOLO después de forzar URLs
exchange.set_sandbox_mode(True)

# Resto de configuración (no cambies esto por ahora)
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
    try:
        balance = exchange.fetch_balance()
        print("Balance completo (debug):", balance, flush=True)  # ← Para ver todo y debuggear
        usdt = balance['USDT']['free'] if 'USDT' in balance else 0
        btc = balance['BTC']['free'] if 'BTC' in balance else 0
        return {'USDT': usdt, 'BTC': btc}
    except Exception as e:
        print(f"Error al obtener balance: {e}", flush=True)
        return {'USDT': 0, 'BTC': 0}
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
    try:
        if action == 'buy':
            order = exchange.create_market_buy_order(SYMBOL, AMOUNT)
            print(f"Compra ejecutada: {order}", flush=True)
        elif action == 'sell':
            order = exchange.create_market_sell_order(SYMBOL, AMOUNT)
            print(f"Venta ejecutada: {order}", flush=True)
    except Exception as e:
        print(f"Error en trade: {e}", flush=True)

# ... (el resto de tus funciones: get_historical_data, calculate_indicators, execute_trade, main() ...)

def main():
    while True:
        try:
            # Obtener precio actual
            price = get_price()
            print(f"Precio actual de BTC/USDT: {price}", flush=True)

            # Obtener estado de cuenta
            balance = get_account_balance()
            print(f"Estado de la cuenta: USDT: {balance['USDT']}, BTC: {balance['BTC']}", flush=True)

            # Obtener datos históricos
            df = get_historical_data()

            # Calcular indicadores
            sma_short, sma_long, rsi = calculate_indicators(df)

            # Lógica de la estrategia
            if sma_short > sma_long and rsi < RSI_OVERSOLD:
                print("Señal de COMPRA: MA corta > MA larga y RSI oversold", flush=True)
                execute_trade('buy')
            elif sma_short < sma_long and rsi > RSI_OVERBOUGHT:
                print("Señal de VENTA: MA corta < MA larga y RSI overbought", flush=True)
                execute_trade('sell')
            else:
                print("Sin señal de trade", flush=True)

        except Exception as e:
            print(f"Error: {e}", flush=True)

        time.sleep(300)  # Espera 5 minutos

if __name__ == "__main__":
    main()
