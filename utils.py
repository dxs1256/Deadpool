import requests
import toml
import base64
import json
import socks  # PySocks
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import log # 导入 log 包

# 全局变量
socks_list = []
effective_list = []
timeout = 10  # 默认超时时间
last_data_file = "lastData.txt" #你可以选择保留或删除

def load_config(filename="config.toml"):
    """加载配置文件"""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            config = toml.load(f)
            return config
    except FileNotFoundError:
        print(f"Error: 配置文件 '{filename}' 未找到。")
        exit(1)
    except toml.TomlDecodeError as e:
        print(f"Error: 解析配置文件 '{filename}' 失败: {e}")
        exit(1)


def fetch_content(url, method="GET", headers=None, params=None, data=None, json_data=None):
    """发送 HTTP 请求并获取响应内容"""
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, params=params, timeout=timeout)
        elif method.upper() == "POST":
            if json_data:
                response = requests.post(url, headers=headers, json=json_data, timeout=timeout)
            else:
                response = requests.post(url, headers=headers, data=data, timeout=timeout)
        else:
            raise ValueError(f"不支持的 HTTP 方法: {method}")

        response.raise_for_status()  # 检查 HTTP 状态码
        return response.text
    except requests.RequestException as e:
        print(f"请求失败: {e}")
        return None


def get_remote_socks(url):
    """从远程 URL 获取代理列表"""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        lines = response.text.strip().splitlines()
        # 简单地假设每行都是一个代理，格式为 ip:port
        return [line.strip() for line in lines if line.strip()]
    except requests.RequestException as e:
        print(f"从 {url} 获取代理失败: {e}")
        return []

def check_proxy(proxy_addr, check_url, timeout):
    """检查单个代理的可用性"""
    try:
        proxies = {
            "http": f"socks5://{proxy_addr}",
            "https": f"socks5://{proxy_addr}",
        }
        response = requests.get(check_url, proxies=proxies, timeout=timeout)
        response.raise_for_status()
        return True  # 如果请求成功，认为代理可用
    except requests.RequestException:
        return False

def check_proxies(proxy_list, check_url, max_concurrent, timeout_sec):
    """
    使用线程池并发检查代理列表的可用性。

    Args:
        proxy_list: 要检查的代理列表（例如：['127.0.0.1:1080', '192.168.1.1:8080']）。
        check_url: 用于检查代理可用性的 URL。
        max_concurrent: 最大并发检查数。

    Returns:
        一个包含有效代理的列表。
    """
    global effective_list
    effective_list = []  # 清空全局有效列表
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        future_to_proxy = {
            executor.submit(check_proxy, proxy, check_url, timeout_sec): proxy
            for proxy in proxy_list
        }
        for future in as_completed(future_to_proxy):
            proxy = future_to_proxy[future]
            try:
                if future.result():
                    effective_list.append(proxy) #添加到全局列表
                    print(f"代理 {proxy} 可用")
            except Exception as exc:
                print(f"代理 {proxy} 检查出错: {exc}")
    return effective_list #返回局部列表


def write_proxies_to_file(filename, proxies):
    """将代理列表写入文件"""
    with open(filename, "w") as f:
        for proxy in proxies:
            f.write(proxy + "\n")
