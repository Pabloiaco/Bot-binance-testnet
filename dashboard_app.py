from flask import Flask, render_template, jsonify
import csv
import os
import threading
import time
from binance.client import Client
from binance.enums import *
import pandas as pd
import numpy as np
from datetime import datetime

app = Flask(__name__)

LOG_FILE = 'bot_log.csv'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def data():
    operations = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                operations.append(row)
    return jsonify(operations)

def log_operation(op_type, price, result=''):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([now, op_type, round(price, 2), result])

def get_data():
    df = pd.DataFrame(client.get_klines(symbol=symbol, interval=interval, limit=100))
    df = df.iloc[:, :6]
    df.columns = ['Time','Open','High','Low','Close','Volume']
    df.set_index('Time', inplace=True)
    df = df.astype(float)
    return df

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    gain = pd.Series(gain).rolling(window=period).mean()
    loss = pd.Series(loss).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_signal(df):
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA50'] = df['Close'].rolling(50).mean()
    df['RSI'] = compute_rsi(df['Close'], 14)
    df['VolMean5'] = df['Volume'].rolling(5).mean()
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if (prev['MA10'] < prev['MA50'] and last['MA10'] > last['MA50'] and
        45 < last['RSI'] < 60 and last['Volume'] > last['VolMean5']):
        return 'BUY'
    if (prev['MA10'] > prev['MA50'] and last['MA10'] < last['MA50']) or last['RSI'] > 70:
        return 'SELL'
    return 'HOLD'

def get_current_price():
    ticker = client.get_symbol_ticker(symbol=symbol)
    return float(ticker['price'])

def place_order(order_type):
    try:
        if order_type == 'BUY':
            order = client.order_market_buy(symbol=symbol, quantity=quantity)
            return float(order['fills'][0]['price'])
        elif order_type == 'SELL':
            order = client.order_market_sell(symbol=symbol, quantity=quantity)
            return float(order['fills'][0]['price'])
    except Exception as e:
        print("Error ejecutando orden:", e)
        return None

def bot_worker():
    global in_position, entry_price, max_price
    while True:
        try:
            df = get_data()
            signal = get_signal(df)
            price_now = get_current_price()
            if not in_position and signal == 'BUY':
                entry_price = place_order('BUY')
                if entry_price:
                    in_position = True
                    max_price = entry_price
                    log_operation('BUY', entry_price)
                    print(f"Comprado a: {entry_price}")
            elif in_position:
                if price_now > max_price:
                    max_price = price_now
                trailing_stop_price = max_price * (1 - TRAILING_STOP_PERCENT)
                if price_now <= trailing_stop_price:
                    sell_price = place_order('SELL')
                    if sell_price:
                        change = ((sell_price - entry_price) / entry_price) * 100
                        log_operation('SELL', sell_price, f"{change:+.2f}%")
                    in_position = False
                    entry_price = 0.0
                    max_price = 0.0
                elif signal == 'SELL':
                    sell_price = place_order('SELL')
                    if sell_price:
                        change = ((sell_price - entry_price) / entry_price) * 100
                        log_operation('SELL', sell_price, f"{change:+.2f}%")
                    in_position = False
                    entry_price = 0.0
                    max_price = 0.0
            else:
                print(f"Esperando señal... ({signal})")
        except Exception as e:
            print(f"Error en el bot: {e}")
        time.sleep(3600)  # Cada 1 hora

if __name__ == '__main__':
    # Inicializar estado
    in_position = False
    entry_price = 0.0
    max_price = 0.0
    TRAILING_STOP_PERCENT = 0.015
    symbol = 'ETHUSDT'
    quantity = 0.01
    interval = '1h'

    # Cliente Binance Testnet
    API_KEY = os.getenv("BINANCE_API_KEY")
    API_SECRET = os.getenv("BINANCE_API_SECRET")
    client = Client(API_KEY, API_SECRET)
    client.API_URL = 'https://testnet.binance.vision/api'

    # Crear archivo de log si no existe
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['time', 'type', 'price', 'result'])

    # Iniciar hilo del bot
    threading.Thread(target=bot_worker, daemon=True).start()

    # Lanzar dashboard Flask
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
