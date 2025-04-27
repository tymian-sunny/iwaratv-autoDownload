# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import requests, hashlib, os
import urllib3
from http.client import IncompleteRead # 引入 IncompleteRead 以便在 app.py 中捕获
from requests.exceptions import RequestException # 导入 requ

BASE_DATA_DIR = "/srv/video_downloader/data"

# 定义下载目录
DOWNLOAD_DIR = os.path.join(BASE_DATA_DIR, "downloads")
# 定义缩略图存储目录 (视频目录下的 thumbnails 子目录)
THUMBNAIL_DIR = os.path.join(DOWNLOAD_DIR, "thumbnails")
# 最大重试次数
MAX_RETRIES = 5

# import cloudscraper
# from requests_html import HTMLSession
# from bs4 import BeautifulSoup
# html_url = 'https://iwara.tv'

api_url = 'https://api.iwara.tv'
file_url = 'https://files.iwara.tv'

# 忽略SSH验证
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class BearerAuth(requests.auth.AuthBase):
    '''
    Bearer Authentication
    身份验证
    '''
    def __init__(self, token):
        self.token = token

    def __call__(self, r):
        r.headers['Authorization'] = 'Bearer ' + self.token
        return r

class ApiClient:
    def __init__(self, email, password):
        self.email = email
        self.password = password

        # API
        self.api_url = api_url
        self.file_url = file_url
        self.timeout = 30
        # self.max_retries = 5 # 内部重试在下载方法中处理
        self.download_timeout = 300 # 单次下载请求的超时时间
        self.token = None

    def login(self) -> requests.Response:
        url = self.api_url + '/user/login'
        json = {'email': self.email, 'password': self.password}
        try:
            r = requests.post(url, json=json, timeout=self.timeout)
            r.raise_for_status() # 检查HTTP错误
            self.token = r.json()['token']
            print('API 登录成功， '+self.token)
        except requests.exceptions.RequestException as e:
            print(f'API 登录失败: {e}')
            # 如果登录失败，可能需要抛出异常或采取其他措施
            raise ConnectionError(f"API登录失败: {e}") # 抛出异常阻止后续操作
        except Exception as e:
            print(f'API 登录失败，解析响应错误: {e}')
            raise ConnectionError(f"API登录失败，解析响应错误: {e}") # 抛出异常

        return r # 即使失败也可能需要返回响应对象，但上面已改为抛异常

    def get_video(self, video_id) -> requests.Response:
        url = self.api_url + '/video/' + video_id
        try:
            r = requests.get(url, auth=BearerAuth(self.token), timeout=self.timeout) if self.token else requests.get(url, timeout=self.timeout)
            r.raise_for_status() # 检查HTTP错误
            print(f"[DEBUG] get_video {video_id} 响应: {r.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"[错误] 获取视频信息 {video_id} 失败: {e}")
            raise # 将异常向上抛出，以便调用者处理
        return r

    # def check_videos(self,videos_response):
    #     try:
    #         videos = videos_response.json().get('results', [])  # 安全获取 results
    #         if not videos:
    #             print("未找到任何视频。")
    #             return
    #     except RequestException as e:
    #         print(f"获取视频列表失败: {e}")
    #         return
    #     except Exception as e:  # 包括可能的 JSONDecodeError
    #         print(f"处理视频列表响应时出错: {e}")
    #         return

    # limit query is not working
    def get_videos(self, sort = 'date', rating = 'all', page = 0, limit = 32, subscribed = False) -> requests.Response:
        '''
        Get new videos from iwara.tv
        从iwara.tv获取视频
        :param sort: date, trending, popularity, views, likes / 最新，流行，人气，最多人观看，最多赞
        :param rating: all, general, ecchi / 所有，普通，H
        :param page: 页码
        :param limit: 每页数量
        :param subscribed: 是否订阅
        :return: requests.Response 响应对象
        '''
        url = self.api_url + '/videos'
        params = {'sort': sort,
                  'rating': rating,
                  'page': page,
                  'limit': limit,
                  'subscribed': 'true' if subscribed else 'false',
                  }
        try:
            if self.token is None:
                # 尝试在没有token的情况下获取，如果API需要则可能失败
                print("[警告] 尝试在未登录状态下获取视频列表")
                r = requests.get(url, params=params, timeout=self.timeout)
            else:
                r = requests.get(url, params=params, auth=BearerAuth(self.token), timeout=self.timeout)
            r.raise_for_status() # 检查HTTP错误
            print(f"[DEBUG] get_videos 响应: {r.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"[错误] 获取视频列表失败: {e}")
            raise # 将异常向上抛出

        # r = self.check_videos(r)

        return r

    def download_video_thumbnail(self, video_id) -> str | None:
        '''
        Download video thumbnail from iwara.tv
        从iwara.tv下载视频缩略图
        :param video_id: 视频id
        :return: 缩略图文件的完整路径，如果下载失败则返回 None
        '''
        thumbnail_path = None # 初始化返回路径
        try:
            video_info = self.get_video(video_id).json()

            file_id = video_info.get('file', {}).get('id')
            thumbnail_id = video_info.get('thumbnail')

            if not file_id or thumbnail_id is None: # 检查是否成功获取到必要信息
                 print(f"[错误] 视频 {video_id} 信息不完整，无法获取缩略图 ID。")
                 return None

            url = f"{self.file_url}/image/original/{file_id}/thumbnail-{thumbnail_id:02d}.jpg"

            # 确保缩略图目录存在
            os.makedirs(THUMBNAIL_DIR, exist_ok=True)

            # 定义缩略图文件名和完整路径
            thumbnail_file_name = f"{video_id}.jpg"
            thumbnail_path = os.path.join(THUMBNAIL_DIR, thumbnail_file_name)

            if (os.path.exists(thumbnail_path)):
                print(f"视频 {video_id} 的缩略图已存在于 {thumbnail_path}，跳过下载。")
                return thumbnail_path

            print(f"开始下载视频 {video_id} 的缩略图...")
            with requests.get(url, stream=True, timeout=self.timeout, verify=False) as r_thumb:
                r_thumb.raise_for_status() # 检查下载请求是否成功
                with open(thumbnail_path, "wb") as f:
                    for chunk in r_thumb.iter_content(chunk_size=8192): # 使用更大的块大小
                        if chunk:
                            f.write(chunk)
                            # f.flush() # 通常不需要手动 flush
            print(f"视频 {video_id} 的缩略图下载完成，保存至 {thumbnail_path}")
            return thumbnail_path

        except requests.exceptions.RequestException as e:
            print(f"[错误] 下载视频 {video_id} 的缩略图失败 (请求错误): {e}")
            # 如果下载失败，尝试删除可能已创建的不完整文件
            if thumbnail_path and os.path.exists(thumbnail_path):
                try:
                    os.remove(thumbnail_path)
                except OSError as oe:
                    print(f"[警告] 删除不完整的缩略图文件 {thumbnail_path} 失败: {oe}")
            return None # 返回 None 表示失败
        except KeyError as e:
            print(f"[错误] 解析视频 {video_id} 信息以下载缩略图时出错 (缺少键: {e})")
            return None
        except Exception as e:
            print(f"[错误] 下载视频 {video_id} 的缩略图时发生未知错误: {e}")
             # 同上，尝试删除不完整文件
            if thumbnail_path and os.path.exists(thumbnail_path):
                try:
                    os.remove(thumbnail_path)
                except OSError as oe:
                    print(f"[警告] 删除不完整的缩略图文件 {thumbnail_path} 失败: {oe}")
            return None

    def download_video_byAi_timeoutRetransmission_queue(self, video_id) -> tuple[str, int] | None:
        '''
        从iwara.tv下载视频，拥有超时重传和队列存储功能（队列功能在app.py实现）。
        :param video_id: 视频ID
        :return: 成功时返回包含 (视频文件路径, 文件大小bytes) 的元组，失败时返回 None 或抛出异常。
        '''
        try:
            video = self.get_video(video_id).json() # 获取视频信息
        except Exception as e:
            # 注意：这里抛出的异常应该在调用处（如 download_worker）被捕获
            raise Exception(f"无法获取视频 {video_id} 的信息，错误: {e}")

        url = video.get('fileUrl')
        file_info = video.get('file')
        if not url or not file_info or 'id' not in file_info:
             raise Exception(f"视频 {video_id} 信息不完整，缺少 fileUrl 或 file.id")

        file_id = file_info['id']
        # 解析 expires (更健壮的方式)
        try:
            query_params = urllib3.util.parse_url(url).query
            expires = dict(p.split('=') for p in query_params.split('&')).get('expires')
            if not expires:
                raise ValueError("无法从 fileUrl 中解析 expires 参数")
        except Exception as e:
             raise Exception(f"解析视频 {video_id} 的 fileUrl 出错: {e}")

        SHA_postfix = "_5nFp9kmbNnHdAFhaqMvt"
        SHA_key = file_id + "_" + expires + SHA_postfix
        hash_val = hashlib.sha1(SHA_key.encode('utf-8')).hexdigest() # 使用 hash_val 避免覆盖内置函数 hash
        headers = {"X-Version": hash_val}

        try:
            # 获取下载资源链接
            resources_resp = requests.get(url, headers=headers, auth=BearerAuth(self.token), timeout=self.timeout)
            resources_resp.raise_for_status()
            resources = resources_resp.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"获取视频 {video_id} 下载资源链接失败: {e}")
        except Exception as e: # 包括 JSONDecodeError
            raise Exception(f"解析视频 {video_id} 下载资源响应失败: {e}")

        download_link = None
        file_type = 'mp4' # 默认文件类型
        # 优先寻找 Source 清晰度
        for resource in resources:
            if resource.get('name') == 'Source' and resource.get('src', {}).get('download'):
                download_link = "https:" + resource['src']['download']
                if 'type' in resource and '/' in resource['type']:
                    file_type = resource['type'].split('/')[1]
                break

        # 如果没有 Source，尝试寻找其他可用链接 (这里可以根据需要扩展逻辑，例如选择最高分辨率)
        if not download_link and resources:
             # 简单地选择第一个找到的链接作为备选
             first_resource = resources[0]
             if first_resource.get('src', {}).get('download'):
                 download_link = "https:" + first_resource['src']['download']
                 if 'type' in first_resource and '/' in first_resource['type']:
                    file_type = first_resource['type'].split('/')[1]
                 print(f"[警告] 未找到 {video_id} 的 Source 清晰度，将下载其他可用清晰度。")

        if not download_link:
            raise Exception(f"视频 {video_id} 未找到可用的下载链接")

        # 使用 DOWNLOAD_DIR 拼接完整文件路径
        video_file_name = os.path.join(DOWNLOAD_DIR, f"{video_id}.{file_type}")

        print(f"[DEBUG] 视频 {video_id} 下载链接: {download_link}")
        print(f"[DEBUG] 视频 {video_id} 保存路径: {video_file_name}")

        # 确保下载目录存在
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        # --- 断点续传和下载逻辑 ---
        resume_byte_pos = 0
        if os.path.exists(video_file_name):
            resume_byte_pos = os.path.getsize(video_file_name)
            print(f"文件 {video_file_name} 已存在，大小: {resume_byte_pos} bytes。尝试断点续传。")

        headers_download = {'Range': f'bytes={resume_byte_pos}-'} if resume_byte_pos > 0 else {}
        headers_download['User-Agent'] = 'Mozilla/5.0' # 添加 User-Agent 可能有助于避免某些服务器阻止

        max_retries = MAX_RETRIES # 下载重试次数
        downloaded_size = resume_byte_pos # 初始化已下载大小
        total_size = None # 初始化总大小

        for attempt in range(max_retries):
            print(f"尝试下载视频 {video_id}，第 {attempt + 1}/{max_retries} 次...")
            try:
                with requests.get(download_link, headers=headers_download, stream=True, timeout=self.download_timeout, verify=False) as response:

                    # 处理 416 Range Not Satisfiable
                    if response.status_code == 416:
                        print(f"收到 416 状态码，服务器不支持请求的范围 (可能文件已完整或 Range={resume_byte_pos}- 无效)")
                        # 检查文件是否真的完整
                        try:
                            head_resp = requests.head(download_link, timeout=self.timeout, verify=False, allow_redirects=True)
                            server_total_size = int(head_resp.headers.get('Content-Length', 0))
                            if server_total_size > 0 and resume_byte_pos >= server_total_size or server_total_size == 0:
                                print(f"文件 {video_file_name} 已完整 (本地 {resume_byte_pos} >= 服务器 {server_total_size})。")
                                return video_file_name, resume_byte_pos # 返回现有文件路径和大小
                            else:
                                print(f"文件不完整或服务器报告大小为0/未知，将重新下载。删除本地文件...")
                                os.remove(video_file_name)
                                resume_byte_pos = 0
                                downloaded_size = 0
                                headers_download = {'User-Agent': 'Mozilla/5.0'} # 重置 headers
                                continue # 进入下一次尝试（无 Range）
                        except Exception as head_err:
                             print(f"[警告] 检查文件总大小失败: {head_err}。假设文件已完成。")
                             return video_file_name, resume_byte_pos # 乐观地假设完成

                    # 检查其他错误状态码
                    response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)

                    # 尝试获取总大小 (Content-Range 优先于 Content-Length for 206 Partial Content)
                    if 'Content-Range' in response.headers:
                        try:
                            total_size = int(response.headers['Content-Range'].split('/')[-1])
                        except:
                            print("[警告] 无法从 Content-Range 解析总大小。")
                            total_size = None
                    elif 'Content-Length' in response.headers and response.status_code == 200: # 只有 200 状态码的 CL 才代表完整文件大小
                        total_size = int(response.headers.get('Content-Length', 0))

                    if total_size:
                         print(f"文件: {video_file_name}, 预期总大小: {total_size / 1024:.1f} KB ({total_size / 1024 / 1024:.1f} MB)")
                    else:
                        print(f"文件: {video_file_name}, 未能从响应头获取准确总大小。")


                    mode = "ab" if resume_byte_pos > 0 and response.status_code == 206 else "wb" # 只有在续传成功时才用 'ab'
                    if mode == "wb": # 如果是重新下载，重置 downloaded_size
                        downloaded_size = 0

                    chunk_count = 0
                    last_print_time = time.time()
                    with open(video_file_name, mode) as f:
                        for chunk in response.iter_content(chunk_size=8192 * 4): # 增加 chunk 大小
                            if chunk:
                                f.write(chunk)
                                downloaded_size += len(chunk)
                                chunk_count += 1
                                # 简单的进度显示 (可选, 每秒或每下载一定量数据打印一次)
                                current_time = time.time()
                                if current_time - last_print_time > 60: # 每 60 秒打印一次进度
                                    if total_size:
                                        progress = (downloaded_size / total_size) * 100
                                        print(f"  下载中 {video_id}: {downloaded_size / 1024 / 1024:.1f} / {total_size / 1024 / 1024:.1f} MB ({progress:.1f}%)")
                                    else:
                                        print(f"  下载中 {video_id}: {downloaded_size / 1024 / 1024:.1f} MB")
                                    last_print_time = current_time
                                # f.flush() # 通常不需要手动 flush

                    # 下载循环结束后检查完整性
                    # 获取最终文件大小
                    final_file_size = os.path.getsize(video_file_name)
                    if total_size is not None:
                        if final_file_size < total_size:
                            # 注意：这里不应该直接 raise Exception，因为这会阻止重试
                            print(f"[警告] 下载 {video_id} 可能不完整：预期 {total_size} 字节，实际 {final_file_size} 字节。将在下次重试继续。")
                            # 更新续传位置，准备下一次重试
                            resume_byte_pos = final_file_size
                            headers_download['Range'] = f'bytes={resume_byte_pos}-'
                            time.sleep(2) # 等待一下再重试
                            continue # 继续到下一个 attempt
                        else:
                            print(f"视频 {video_id} 下载完成并校验大小成功，保存为 {video_file_name}")
                            return video_file_name, final_file_size # 成功返回
                    else:
                        # 如果无法获取总大小，则认为下载循环无异常即成功
                        print(f"视频 {video_id} 下载完成 (未进行大小校验)，保存为 {video_file_name}")
                        return video_file_name, final_file_size # 成功返回

            except IncompleteRead as e:
                 # IncompleteRead 通常发生在连接意外关闭时，适合重试
                 print(f"[错误] 下载视频 {video_id} 时发生 IncompleteRead (尝试 {attempt + 1}/{max_retries}): {e}")
                 print(f"  部分数据可能已下载 ({e.partial} bytes). 等待后重试...")
                 # 更新续传位置
                 if os.path.exists(video_file_name):
                      resume_byte_pos = os.path.getsize(video_file_name)
                 else:
                      resume_byte_pos = 0 # 如果文件不存在，从头开始
                 downloaded_size = resume_byte_pos # 更新已下载大小计数器
                 headers_download['Range'] = f'bytes={resume_byte_pos}-'
                 time.sleep(5 * (attempt + 1)) # 增加等待时间重试

            except requests.exceptions.RequestException as e:
                print(f"[错误] 下载视频 {video_id} 时发生网络或HTTP错误 (尝试 {attempt + 1}/{max_retries}): {e}")
                # 更新续传位置
                if os.path.exists(video_file_name):
                    resume_byte_pos = os.path.getsize(video_file_name)
                else:
                    resume_byte_pos = 0
                downloaded_size = resume_byte_pos
                headers_download['Range'] = f'bytes={resume_byte_pos}-'
                time.sleep(5) # 等待后重试

            except Exception as e:
                # 其他未知错误，可能不适合重试，直接抛出让上层处理
                print(f"[严重错误] 下载视频 {video_id} 时发生未知错误 (尝试 {attempt + 1}/{max_retries}): {e}")
                # 检查是否是特定可重试的消息
                if "需稍后重试" in str(e) and attempt < max_retries - 1:
                     print("检测到“需稍后重试”消息，将进行重试...")
                     time.sleep(10) # 等待较长时间
                     # 更新续传位置
                     if os.path.exists(video_file_name):
                        resume_byte_pos = os.path.getsize(video_file_name)
                     else:
                        resume_byte_pos = 0
                     downloaded_size = resume_byte_pos
                     headers_download['Range'] = f'bytes={resume_byte_pos}-'
                     continue # 继续下一次重试
                else:
                    # 对于其他未知错误或达到最大重试次数，向上抛出
                    raise Exception(f"视频 {video_id} 下载失败，发生未知错误或达到最大重试次数: {e}")

        # 如果循环结束仍未成功返回，则表示所有重试都失败了
        raise Exception(f"视频 {video_id} 下载失败，已达到最大重试次数 ({max_retries}次)。")