# server.py
import os
from flask import Flask, jsonify
import json
from flask_cors import CORS
from app import LOG_FILE  # 导入ApiClient和目录常量
import socket


app = Flask(__name__)
CORS(app)

def ipconfig():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]

@app.route('/getIp',methods = ['GET'])
def get_ip():
    return jsonify({"id": ipconfig() })


@app.route('/ecchiData')
def get_data():
    base_path = os.path.dirname(os.path.abspath(__file__))
    LOG_FILE = os.path.join(base_path,'download_log.json')
    with open(LOG_FILE, encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)  # 不建议用3306端口

