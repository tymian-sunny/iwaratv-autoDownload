# iwara视频爬取脚本

> 参考项目：https://github.com/xiatg/iwara-python-api

## 开始

修改config.json中的邮箱和密码

```json
{
  "email": "邮箱账号",
  "password": "密码"
}
```

## 参数

```python
'''
batch_download_videos(email, password, sort='date', rating='all', page=0, limit=32, subscribed=False):
        email (str): 登录邮箱。
        password (str): 登录密码。
        sort (str): 排序方式: date, trending, popularity, views, likes / 最新，流行，人气，最多人观看，最多赞。
        rating (str): 视频分级: all, general, ecchi
        page (int): 页码。
        limit (int): 每页数量。
        subscribed (bool): 是否只下载订阅的视频。
'''
```