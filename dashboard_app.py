
from flask import Flask, render_template, jsonify
import csv
import os

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

if __name__ == '__main__':
    app.run(debug=True)
