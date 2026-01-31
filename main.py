import os
import time
import ccxt
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import BollingerBands
import pandas as pd
import datetime
from flask import Flask
import threading

# Flask para mantener vivo el bot (UptimeRobot)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive! 🚀"

def run_flask():
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

threading.Thread(target=run_flask, daemon=True).start()

# Configuración Binance (solo datos públicos)
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'},
})

SYMBOL = 'BTC/USDT'
TIMEFRAME = '5m'
SLEEP_TIME = 15             # segundos

# --- Parámetros de riesgo y protección ---
RISK_PER_TRADE = 0.10       # 10% del capital disponible por operación
COOLDOWN_AFTER_TRADE = 120  # segundos después de trade
STOP_LOSS_PCT = -1.2        # -1.2% desde precio de entrada
TAKE_PROFIT_PCT = 2.0       # +2.0% desde precio de entrada
BINANCE_SPOT_FEE = 0.001    # 0.1% fee aproximado por lado (maker/taker)

# --- Portfolio simulado ---
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
    return exchange.fetch_ticker(SYMBOL)['last']

def get_account_balance(current_price):
    total_value = usdt_balance + btc_balance * current_price
    drawdown = (initial_balance - total_value) / initial_balance * 100
    global max_drawdown
    if drawdown > max_drawdown:
        max_drawdown = drawdown
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
    # EMA rápidas
    ema9 = EMAIndicator(df['close'], window=9).ema_indicator().iloc[-1]
    ema21 = EMAIndicator(df['close'], window=21).ema_indicator().iloc[-1]
    ema20 = EMAIndicator(df['close'], window=20).ema_indicator().iloc[-1]
    ema200 = EMAIndicator(df['close'], window=200).ema_indicator().iloc[-1]

    # RSI
    rsi = RSIIndicator(df['close'], window=14).rsi()
    rsi_now = rsi.iloc[-1]
    rsi_prev = rsi.iloc[-2] if len(rsi) > 1 else rsi_now

    # Bollinger Bands
    bb = BollingerBands(df['close'], window=20, window_dev=2)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]
    bb_mid = bb.bollinger_mavg().iloc[-1]

    # MACD
    macd = MACD(df['close'])
    macd_line = macd.macd().iloc[-1]
    macd_signal = macd.macd_signal().iloc[-1]

    return {
        'ema9': ema9,
        'ema21': ema21,
        'ema20': ema20,
        'ema200': ema200,
        'rsi': rsi_now,
        'rsi_prev': rsi_prev,
        'bb_upper': bb_upper,
        'bb_lower': bb_lower,
        'bb_mid': bb_mid,
        'macd_line': macd_line,
        'macd_signal': macd_signal
    }

def check_stop_loss_take_profit(current_price):
    global usdt_balance, btc_balance, position_open, total_profit, winning_trades, losing_trades
    if not position_open:
        return False

    pnl_pct = (current_price - entry_price) / entry_price * 100

    if pnl_pct <= STOP_LOSS_PCT:
        revenue = btc_balance * current_price
        gross_pl = revenue - (btc_balance * entry_price)
        fee = revenue * BINANCE_SPOT_FEE
        net_pl = gross_pl - fee
        usdt_balance += revenue - fee
        total_profit += net_pl
        if net_pl >= 0: winning_trades += 1
        else: losing_trades += 1
        log_trade('SELL (STOP LOSS)', current_price, btc_balance, revenue, net_pl)
        btc_balance = 0
        position_open = False
        return True

    if pnl_pct >= TAKE_PROFIT_PCT:
        revenue = btc_balance * current_price
        gross_pl = revenue - (btc_balance * entry_price)
        fee = revenue * BINANCE_SPOT_FEE
        net_pl = gross_pl - fee
        usdt_balance += revenue - fee
        total_profit += net_pl
        winning_trades += 1
        log_trade('SELL (TAKE PROFIT)', current_price, btc_balance, revenue, net_pl)
        btc_balance = 0
        position_open = False
        return True

    return False

def simulate_buy(price):
    global usdt_balance, btc_balance, entry_price, last_trade_time, total_trades, position_open
    now = time.time()
    if now - last_trade_time < COOLDOWN_AFTER_TRADE:
        return

    max_usdt = usdt_balance * AMOUNT_PERCENT
    amount = max_usdt / price
    cost = amount * price
    fee = cost * BINANCE_SPOT_FEE

    if cost + fee <= usdt_balance:
        usdt_balance -= cost + fee
        btc_balance += amount
        entry_price = price
        total_trades += 1
        position_open = True
        last_trade_time = now
        log_trade('BUY', price, amount, cost + fee)
    else:
        print("Fondos insuficientes para el riesgo permitido", flush=True)

def simulate_sell(price, reason='Señal'):
    global usdt_balance, btc_balance, total_profit, winning_trades, losing_trades, position_open, last_trade_time
    now = time.time()
    if now - last_trade_time < COOLDOWN_AFTER_TRADE:
        return

    revenue = btc_balance * price
    gross_pl = revenue - (btc_balance * entry_price)
    fee = revenue * BINANCE_SPOT_FEE
    net_pl = gross_pl - fee
    usdt_balance += revenue - fee
    total_profit += net_pl
    total_trades += 1
    if net_pl >= 0: winning_trades += 1
    else: losing_trades += 1
    log_trade(f'SELL ({reason})', price, btc_balance, revenue - fee, net_pl)
    btc_balance = 0
    position_open = False
    last_trade_time = now

def log_trade(action, price, amount, net_cost_revenue, profit_loss=0.0):
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_value = usdt_balance + btc_balance * price
    message = (
        f"[{now_str}] {action} | Precio: {price:.2f} | Cant: {amount:.6f} | "
        f"Neto: {net_cost_revenue:.2f} USDT | P/L op: {profit_loss:.2f} | "
        f"USDT: {usdt_balance:.2f} | BTC: {btc_balance:.6f} | "
        f"Total: {total_value:.2f} | P/L total: {total_value - initial_balance:.2f}\n"
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
            print(f"Balance → USDT: {balance['USDT']:.2f} | BTC: {balance['BTC']:.6f} | "
                  f"Total: {balance['Total']:.2f} | P/L: {balance['P/L']:.2f} | "
                  f"DD: {balance['Drawdown']:.2f}%", flush=True)

            if check_stop_loss_take_profit(price):
                print("SL/TP ejecutado", flush=True)

            df = get_historical_data(200)
            indicators = calculate_indicators(df)

            print(f"DEBUG → EMA9: {indicators['ema9']:.2f} | EMA21: {indicators['ema21']:.2f} | "
                  f"RSI: {indicators['rsi']:.2f} | EMA200: {indicators['ema200']:.2f}", flush=True)

            buy_signal = False
            sell_signal = False

            # 1. EMA 9/21 + RSI (tu estrategia original)
            if indicators['ema9'] > indicators['ema21'] and indicators['rsi'] < RSI_BUY_LEVEL:
                buy_signal = True
            if indicators['ema9'] < indicators['ema21'] and indicators['rsi'] > RSI_SELL_LEVEL:
                sell_signal = True

            # 2. RSI Rebound (mejorado)
            if indicators['rsi'] < 30 and indicators['rsi'] > indicators['rsi_prev']:
                buy_signal = True
            if indicators['rsi'] > 70 and indicators['rsi'] < indicators['rsi_prev']:
                sell_signal = True

            # 3. Bollinger Bands
            if price < indicators['bb_lower'] and indicators['rsi'] < 40:
                buy_signal = True
            if price > indicators['bb_upper']:
                sell_signal = True

            # 4. MACD + EMA
            if indicators['macd_line'] > indicators['macd_signal'] and indicators['macd_line'] > 0 and price > indicators['ema200']:
                buy_signal = True
            if indicators['macd_line'] < indicators['macd_signal'] and indicators['macd_line'] < 0:
                sell_signal = True

            # 5. EMA 200 filtro + EMA rápida
            if price > indicators['ema200'] and indicators['ema9'] > indicators['ema21']:
                buy_signal = True
            if price < indicators['ema200'] and indicators['ema9'] < indicators['ema21']:
                sell_signal = True

            # Ejecutar
            if buy_signal and not position_open:
                print(">>> COMPRA (multi-estrategia) <<<", flush=True)
                simulate_buy(price)
            elif sell_signal and position_open:
                print(">>> VENTA (multi-estrategia) <<<", flush=True)
                simulate_sell(price)

            winrate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            print(f"Trades: {total_trades} | Winrate: {winrate:.1f}% | "
                  f"P/L acum: {total_profit:.2f} | Max DD: {balance['Max DD']:.2f}%\n", flush=True)

            # Mostrar últimos trades
            try:
                with open('/data/trades.log', 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if lines:
                        print("Últimos 3 trades:\n" + ''.join(lines[-3:]), flush=True)
            except FileNotFoundError:
                print("Aún sin trades\n", flush=True)
            except Exception as e:
                print(f"Error log: {e}\n", flush=True)

        except Exception as e:
            print(f"Error principal: {e}", flush=True)

        time.sleep(SLEEP_TIME)


            balance = get_account_balance(price)
            print(f"Balance → USDT: {balance['USDT']:.2f} | BTC: {balance['BTC']:.6f} | "
                  f"Total: {balance['Total']:.2f} | P/L: {balance['P/L']:.2f} | "
                  f"DD: {balance['Drawdown']:.2f}%", flush=True)

            if check_stop_loss_take_profit(price):
                print("SL/TP ejecutado", flush=True)

            df = get_historical_data(200)
            indicators = calculate_indicators(df)

            print(f"DEBUG → EMA9: {indicators['ema9']:.2f} | EMA21: {indicators['ema21']:.2f} | "
                  f"RSI: {indicators['rsi']:.2f} | EMA200: {indicators['ema200']:.2f}", flush=True)

            buy_signal = False
            sell_signal = False

            # 1. EMA 9/21 + RSI (tu estrategia original)
            if indicators['ema9'] > indicators['ema21'] and indicators['rsi'] < RSI_BUY_LEVEL:
                buy_signal = True
            if indicators['ema9'] < indicators['ema21'] and indicators['rsi'] > RSI_SELL_LEVEL:
                sell_signal = True

            # 2. RSI Rebound (mejorado)
            if indicators['rsi'] < 30 and indicators['rsi'] > indicators['rsi_prev']:
                buy_signal = True
            if indicators['rsi'] > 70 and indicators['rsi'] < indicators['rsi_prev']:
                sell_signal = True

            # 3. Bollinger Bands
            if price < indicators['bb_lower'] and indicators['rsi'] < 40:
                buy_signal = True
            if price > indicators['bb_upper']:
                sell_signal = True

            # 4. MACD + EMA
            if indicators['macd_line'] > indicators['macd_signal'] and indicators['macd_line'] > 0 and price > indicators['ema200']:
                buy_signal = True
            if indicators['macd_line'] < indicators['macd_signal'] and indicators['macd_line'] < 0:
                sell_signal = True

            # 5. EMA 200 filtro + EMA rápida
            if price > indicators['ema200'] and indicators['ema9'] > indicators['ema21']:
                buy_signal = True
            if price < indicators['ema200'] and indicators['ema9'] < indicators['ema21']:
                sell_signal = True

            # Ejecutar
            if buy_signal and not position_open:
                print(">>> COMPRA (multi-estrategia) <<<", flush=True)
                simulate_buy(price)
            elif sell_signal and position_open:
                print(">>> VENTA (multi-estrategia) <<<", flush=True)
                simulate_sell(price)

            winrate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            print(f"Trades: {total_trades} | Winrate: {winrate:.1f}% | "
                  f"P/L acum: {total_profit:.2f} | Max DD: {balance['Max DD']:.2f}%\n", flush=True)

            # Mostrar últimos trades
            try:
                with open('/data/trades.log', 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if lines:
                        print("Últimos 3 trades:\n" + ''.join(lines[-3:]), flush=True)
            except FileNotFoundError:
                print("Aún sin trades\n", flush=True)
            except Exception as e:
                print(f"Error log: {e}\n", flush=True)

        except Exception as e:
            print(f"Error principal: {e}", flush=True)

        time.sleep(60)








