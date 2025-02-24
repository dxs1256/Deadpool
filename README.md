**功能：**

*   从远程 URL 获取 SOCKS5 代理。
*   多线程检查代理可用性。
*   去重、保存有效代理。
*   可选：定时更新。

**依赖：**

*   `requests`
*   `PySocks`
*   `toml`
*   `schedule` (可选)

**安装：**

```bash
pip install -r requirements.txt
Use code with caution.
Markdown
配置 (config.toml):

[remote_urls]
urls = ["url1", "url2"]  # 代理 URL 列表

[check_socks]
max_concurrent_req = 50  # 并发数
timeout = 10             # 超时 (秒)
check_url = "https://www.google.com"  # 检查 URL

[task] # 定时任务，留空则不启用
periodic_checking = ""  # 检查周期 (cron 表达式)
periodic_get_socks = "" # 获取周期 (cron 表达式)
Use code with caution.
Toml
```

** 用法：**

*  配置 config.toml。

*  运行 python main.py。

** 输出：**

*  控制台日志。

*  有效代理保存至 lastData.txt。

** TODO (未来可能的改进):** 

*  添加更多的代理来源。

*  更精细的代理检查（例如，检查延迟、地理位置等）。

*  支持多种代理协议（HTTP、HTTPS、SOCKS4）。

*  提供 Web 界面。

*  实现SOCKS5服务器功能。
