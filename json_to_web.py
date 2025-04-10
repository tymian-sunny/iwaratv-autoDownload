# server.py
from flask import Flask, jsonify
import json
from flask_cors import CORS
from app import LOG_FILE  # 导入ApiClient和目录常量


app = Flask(__name__)
CORS(app)
@app.route('/ecchiData')
def get_data():
    with open(LOG_FILE, encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)  # 不建议用3306端口

