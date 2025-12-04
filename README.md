SOCKS5 Proxy Checker

一个轻量级 SOCKS5 代理抓取与检测工具。自动从 GitHub 源获取代理，并根据连通性分类为 国内(Baidu)、国外(Google) 及 全能(All) 代理。

输出文件

运行后自动生成/刷新以下文件：

Baidu.txt: 可访问百度（国内业务/回国加速）
Google.txt: 可访问 Google（科学上网/爬虫）
All.txt: 双向连通（高质量全能代理）

使用方法

1. 本地运行

需 Python 3.8+ 环境：

# 安装依赖
pip install requests toml pysocks

# 运行 (自动生成 txt 文件)
python main.py

2. GitHub Actions 自动运行
机制: 每天 UTC 0:00 (北京时间 8:00) 自动执行。 结果: 检测完成后的新列表会自动 Commit 并 Push 到当前仓库。 手动触发: Actions -> Proxy Checker -> Run workflow。

配置
修改 config.toml 文件：

check_urls: 定义分类规则（包含 "baidu" 或 "google" 关键字）。

max_concurrent_req: 并发数（默认 200）。

remote_urls: 代理抓取源列表。

免责声明
仅供学习研究，请勿用于非法用途。抓取的代理来自互联网公开资源，安全性自负。
