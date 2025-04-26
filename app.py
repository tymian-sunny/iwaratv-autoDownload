# -*- coding: utf-8 -*-
import os
import time
import queue
import json
import threading # 导入 threading

from threading import Thread

from api_client import ApiClient, DOWNLOAD_DIR, THUMBNAIL_DIR # 导入ApiClient和目录常量
from http.client import IncompleteRead
from requests.exceptions import RequestException # 导入 requests 的异常

# 定义日志文件名
LOG_FILE = "download_log.json"
config_path = ""

email = "your_email@example.com"  # 替换为你的邮箱
password = "your_password"  # 替换为你的密码

# 读取账号密码
def json_read():
    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print("config.json not found")
    except json.JSONDecodeError as e:
        print(f"config.json 格式错误:{e}")
    return None

# --- 新增：JSON 日志记录函数 ---
def log_download_info(lock, video_id,avatar_name,video_title,video_numComments,video_numLikes,video_numViews,video_tagList,video_createTime,timestamp, video_path, thumbnail_path,  video_size_bytes, success):
    """
    记录视频下载信息到 JSON 文件。
    使用锁来确保线程安全。

    Args:
        lock (threading.Lock): 用于文件访问的锁。
        video_id (str): 视频ID。
        avatar_name: 视频作者
        video_title: 视频名称
        video_numComments: 评论数
        video_numLikes: 喜欢数
        video_numViews: 观看数
        video_tagList: 视频Tag列表
        video_createTime: 视频上传时间
        timestamp (float): 下载完成或失败的时间戳 (time.time())。
        video_path (str | None): 视频文件存储路径 (失败时为 None)。
        thumbnail_path (str | None): 缩略图文件存储路径 (可能为 None)。
        video_size_bytes (int): 视频文件大小 (bytes)，失败时为 0。
        success (bool): 下载是否成功。
        local_id: 本地序列号
    """
    with lock: # 获取锁，保证只有一个线程能写入文件
        try:
            # 读取现有日志数据
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, 'r', encoding='utf-8') as f:
                    try:
                        log_data = json.load(f)
                    except json.JSONDecodeError:
                        print(f"[警告] 日志文件 {LOG_FILE} 格式错误，将创建新的日志。")
                        log_data = {} # 如果文件损坏，则重置
            else:
                log_data = {} # 文件不存在，创建空字典

            # 如果查不到此条目则说明是新的条目，总数+1, 本地序列号为最新序列号
            # 如果查得到，则本地序列号不变
            if not log_data.get(video_id):
                log_data['total']['number'] += 1
                local_id = log_data['total']['number']
            else:
                local_id = log_data[video_id]['local_id']
                # 如果查得到本地序列号，则判断视频是否已经下载完成
                # 如果视频已经下载完成则直接退出
                if log_data[video_id]['success']:
                    print("视频已经下载完成，修改json文件失败")
                    return

                # 如果查得到是本地序列号，说明条目已存在，查询是否已经曾下载完成
                # 如果视频已经下载完成则直接退出
                if log_data[video_id]['success']:
                    return

            # 准备新的日志条目
            video_size_mb = round(video_size_bytes / (1024 * 1024), 1) if video_size_bytes else 0.0
            log_entry = {
                "video_id": video_id,
                "avatar_name": avatar_name,
                "video_title": video_title,
                "video_numComments": video_numComments,
                "video_numLikes": video_numLikes,
                "video_numViews": video_numViews,
                "video_tagList": video_tagList,
                "video_createTime": video_createTime,
                "download_time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp)),
                "video_path": video_path,
                "thumbnail_path": thumbnail_path,
                "video_size_mb": video_size_mb,
                "success": success,
                "local_id": local_id,
                "last_update_timestamp": timestamp # 添加原始时间戳以备将来排序或比较
            }

            # 更新或添加条目 (使用 video_id 作为 key)
            log_data[video_id] = log_entry
            print(f"[日志] 更新视频 {video_id} 的下载状态: {'成功' if success else '失败'}")

            # 写回 JSON 文件
            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, ensure_ascii=False, indent=4) # indent 参数使 JSON 文件更易读

        except IOError as e:
            print(f"[严重错误] 无法写入日志文件 {LOG_FILE}: {e}")
        except Exception as e:
            print(f"[严重错误] 记录日志时发生未知错误: {e}")

# --- 修改：下载工作线程函数 ---
def download_worker(client, video_id, failed_queue, log_lock,avatar_name,video_title,video_numComments,video_numLikes,video_numViews,video_tagList,video_createTime):
    """
    单个视频的下载工作线程，包括缩略图下载、视频下载、重试和日志记录。

    Args:
        client (ApiClient): API 客户端实例。
        video_id (str): 要下载的视频ID。
        failed_queue (queue.Queue): 用于存放需要外部重试的任务。
        log_lock (threading.Lock): 用于日志文件写入的锁。
    """
    thumbnail_path = None # 初始化缩略图路径
    video_path = None     # 初始化视频路径
    video_size_bytes = 0  # 初始化视频大小
    success = False       # 初始化成功状态

    try:
        # 1. 尝试下载缩略图 (不影响视频下载流程，但记录结果)
        try:
            thumbnail_path = client.download_video_thumbnail(video_id)
            if thumbnail_path:
                print(f"缩略图 {video_id} 下载成功: {thumbnail_path}")
            else:
                print(f"缩略图 {video_id} 下载失败或已跳过")
        except Exception as thumb_e:
            # 即使缩略图下载失败，也继续尝试下载视频
            print(f"[错误] 下载缩略图 {video_id} 时发生异常: {thumb_e}")

        # 2. 尝试下载视频 (包含内部重试逻辑)
        # 注意：download_video_byAi... 现在返回 (路径, 大小) 或抛出异常
        download_result = client.download_video_byAi_timeoutRetransmission_queue(video_id)

        # 如果下载函数成功返回 (没有抛出异常)
        video_path, video_size_bytes = download_result
        print(f"视频 {video_id} 下载成功，大小: {video_size_bytes} bytes")
        success = True

    except (IncompleteRead, RequestException, ConnectionError) as e: # 处理预期的网络和请求错误
        # 这些错误通常是临时的，适合放入外部重试队列
        print(f"下载视频 {video_id} 失败 (可重试错误): {e}")
        # 加入外部重试队列，10秒后重试
        print(f"下载视频 {video_id} 失败，加入外部重试队列")
        failed_queue.put((video_id, time.time() + 10))
        success = False # 标记为失败，稍后记录日志

    except Exception as e:
        # 处理 download_video... 内部重试失败后抛出的最终异常
        # 或者其他意外错误 (如获取视频信息失败、无下载链接等)
        print(f"下载视频 {video_id} 最终失败: {e}")
        # 检查是否包含特定可重试消息 (虽然内部已重试，但有时API会要求更长时间等待)
        if "需稍后重试" in str(e):
            print(f"检测到“需稍后重试”，加入外部重试队列")
            failed_queue.put((video_id, time.time() + 10)) # 放入外部队列进行更长时间的等待
        # 对于其他最终失败情况，不再放入队列
        success = False # 标记为失败

    finally:
        # 3. 记录日志 (无论成功还是失败)
        # 只有在确定最终状态后才记录日志
        # 如果 success 为 True，则 video_path 和 video_size_bytes 应该有值
        # 如果 success 为 False，则 video_path 为 None, video_size_bytes 为 0
        log_download_info(log_lock, video_id,avatar_name,video_title,video_numComments,video_numLikes,video_numViews,video_tagList,video_createTime,time.time(), video_path, thumbnail_path,  video_size_bytes, success)


# --- 修改：批量下载主函数 ---
def batch_download_videos(client,email, password, sort='date', rating='all', page=0, limit=32, subscribed=False):
    """
    批量下载视频的主函数。

    Args:
        email (str): 登录邮箱。
        password (str): 登录密码。
        sort (str): 排序方式: date, trending, popularity, views, likes / 最新，流行，人气，最多人观看，最多赞。
        rating (str): 视频分级: all, general, ecchi
        page (int): 页码。
        limit (int): 每页数量。
        subscribed (bool): 是否只下载订阅的视频。
    """


    try:
        videos_response = client.get_videos(sort=sort, rating=rating, page=page, limit=limit, subscribed=subscribed)
        videos = videos_response.json().get('results', []) # 安全获取 results
        if not videos:
            print("未找到任何视频。")
            return
    except RequestException as e:
         print(f"获取视频列表失败: {e}")
         return
    except Exception as e: # 包括可能的 JSONDecodeError
        print(f"处理视频列表响应时出错: {e}")
        return

    failed_queue = queue.Queue()  # 存储失败任务的队列 (用于外部重试)
    log_lock = threading.Lock()  # 创建日志文件锁
    threads = []

    print(f"开始处理 {len(videos)} 个视频的下载任务...")

    # 处理初始下载任务
    for video in videos:
        video_id = video.get('id')
        avatar_name = video.get('user')['name']
        video_title = video.get('title')
        video_numComments = video.get('numComments')
        video_numLikes = video.get('numLikes')
        video_numViews = video.get('numViews')
        video_tagList = [tag['id'] for tag in video.get('tags')]
        video_createTime = video.get('createdAt')
        if not video_id:
            print(f"[警告] 视频信息缺少 ID: {video}")
            continue # 跳过缺少 ID 的视频

        # 启动下载工作线程，传入锁
        t = Thread(target=download_worker,
                   args=(client, video_id, failed_queue, log_lock,avatar_name,video_title,video_numComments,video_numLikes,video_numViews,video_tagList,video_createTime))
        threads.append(t)
        t.start()
        time.sleep(0.1) # 短暂休眠，避免瞬间启动过多线程可能带来的问题

    # 等待所有初始任务的线程完成
    print("等待所有初始下载线程完成...")
    for t in threads:
        t.join()
    print("所有初始下载线程已结束。")

    # 处理失败任务的重试 (外部重试循环)
    retry_threads = [] # 用于管理重试线程
    while not failed_queue.empty():
        video_id, retry_time = failed_queue.get()
        current_time = time.time()
        wait_time = retry_time - current_time
        if wait_time > 0:
            print(f"等待 {wait_time:.1f} 秒后重试视频 {video_id}...")
            time.sleep(wait_time)

        print(f"开始重试下载视频 {video_id}...")
        # 重新启动 download_worker 进行重试，同样传入锁
        # 注意：这里的重试不会无限循环，因为 worker 内部有次数限制，
        # 并且只有特定错误才会再次放入 failed_queue
        # 为了避免无限重试循环，可以在这里加入一个最大外部重试次数的逻辑（可选）
        t = Thread(target=download_worker,
                   args=(client, video_id, failed_queue, log_lock,avatar_name,video_title,video_numComments,video_numLikes,video_numViews,video_tagList,video_createTime))
        retry_threads.append(t)
        t.start()
        # 为了简化，让重试任务也并发执行，如果需要严格顺序执行，则去掉 threading，直接调用 worker
        # t.join() # 如果需要顺序执行重试任务，取消这行注释并移除 retry_threads 列表

    # 等待所有重试任务的线程完成 (如果使用并发重试)
    if retry_threads:
        print("等待所有重试线程完成...")
        for t in retry_threads:
            t.join()
        print("所有重试线程已结束。")

    print("批量下载任务处理完毕。")

# --- 使用示例 ---
if __name__ == "__main__":
    # 确保下载目录和缩略图目录存在 (虽然下载函数会创建，但预先创建更好)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)

    # 获取文件路径
    base_path = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_path, 'config.json')
    LOG_FILE = os.path.join(base_path, 'download_log.json')
    print(f"config.json路径为: {config_path}\ndownload_log.json路径为: {LOG_FILE}")

    data = json_read()
    if data is None:
        print("配置文件读取失败，程序中止")
        exit(1)

    email = data['email']
    password = data['password']

    if email == "your_email@example.com" or password == "your_password":
        print("请在 config.json 中替换你的邮箱和密码！")
    else:
        # 下载最新的3页32个视频/页共96个视频
        try:
            client = ApiClient(email=email, password=password)
            client.login()  # 登录，如果失败会抛出 ConnectionError
        except ConnectionError as e:
            print(f"无法继续下载，登录失败: {e}")

        for k in range(0, 1):
            style = True if range == 0 else False
            for i in range(0, 3):
                for j in range(1, 5):
                    batch_download_videos(client, email, password, sort='trending', rating='all', page=i, limit=j * 8,
                                          subscribed=style)