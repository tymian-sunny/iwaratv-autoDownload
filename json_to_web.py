# server.py
import queue
import threading

from flask import Flask, jsonify, request
import json
from flask_cors import CORS
from app import LOG_FILE  # 导入ApiClient和目录常量
from api_client import ApiClient
from app import json_read,download_worker
from threading import Thread
import socket
app = Flask(__name__)
CORS(app)

@app.route('/downloadVideoById', methods=['GET'])
def download_video_by_id():
    id = request.args.get('id')
    global client
    result = ""
    data = ""
    data = json_read()

    # 登录
    email = data['email']
    password = data['password']
    try:
        client = ApiClient(email=email, password=password)
        client.login()  # 登录，如果失败会抛出 ConnectionError
    except ConnectionError as e:
        result = f"无法继续下载，登录失败: {e}"


    try:
        # 获取视频数据并下载
        data = client.get_video(id)
        # 安全获取 results
        video = data.text
        video = json.loads(video)
        video_id = video.get('id')

        log_lock = threading.Lock()  # 创建日志文件锁
        failed_queue = queue.Queue()

        avatar_name = video.get('user')['name']
        video_title = video.get('title')
        video_numComments = video.get('numComments')
        video_numLikes = video.get('numLikes')
        video_numViews = video.get('numViews')
        video_tagList = [tag['id'] for tag in video.get('tags')]
        video_createTime = video.get('createdAt')

        t = Thread(target=download_worker,
                   args=(client, id, failed_queue, log_lock, avatar_name, video_title, video_numComments,
                         video_numLikes, video_numViews, video_tagList, video_createTime))
        t.start()

    except Exception as e:
        result = e

    return result

def ipconfig():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]

@app.route('/getIp',methods = ['GET'])
def get_ip():
    return jsonify({"id": ipconfig() })


@app.route('/ecchiData')
def get_data():
    with open(LOG_FILE, encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)  # 不建议用3306端口