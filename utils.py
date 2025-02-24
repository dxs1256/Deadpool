import requests
import toml
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Union, Any  # 导入类型提示

# 全局变量 (尽可能减少全局变量的使用)
# socks_list 和 effective_list 现在只在函数内部使用，因此不再是全局变量
TIMEOUT = 10  # 默认超时时间, 可以直接定义为常量
LAST_DATA_FILE = "lastData.txt"  # 默认文件名


def load_config(filename: str = "config.toml") -> Dict:
    """加载配置文件"""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return toml.load(f)
    except FileNotFoundError:
        logging.error(f"配置文件 '{filename}' 未找到。")
        exit(1)
    except toml.TomlDecodeError as e:
        logging.error(f"解析配置文件 '{filename}' 失败: {e}")
        exit(1)


def fetch_content(url: str, method: str = "GET", headers: Optional[Dict] = None,
                  params: Optional[Dict] = None, data: Optional[Dict] = None,
                  json_data: Optional[Dict] = None) -> Optional[str]:
    """发送 HTTP 请求并获取响应内容"""
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        elif method.upper() == "POST":
            if json_data:
                response = requests.post(url, headers=headers, json=json_data, timeout=TIMEOUT)
            else:
                response = requests.post(url, headers=headers, data=data, timeout=TIMEOUT)
        else:
            raise ValueError(f"不支持的 HTTP 方法: {method}")

        response.raise_for_status()  # 检查 HTTP 状态码
        return response.text
    except requests.RequestException as e:
        logging.error(f"请求失败: {e}")
        return None


def get_remote_socks(url: str) -> List[str]:
    """从远程 URL 获取代理列表"""
    logging.info(f"正在从 {url} 获取代理...")
    try:
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        lines = response.text.strip().splitlines()
        # 简单地假设每行都是一个代理，格式为 ip:port
        proxies = [line.strip() for line in lines if line.strip()]
        logging.info(f"从 {url} 获取到 {len(proxies)} 个代理")
        return proxies
    except requests.RequestException as e:
        logging.error(f"从 {url} 获取代理失败: {e}")
        return []
    

def check_proxy(proxy_addr: str, check_url: str, timeout: int) -> bool:
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
        logging.debug(f"代理 {proxy_addr} 不可用")
        return False

def check_proxies(proxy_list: List[str], check_url: str, max_concurrent: int, timeout_sec: int) -> List[str]:
    """
    使用线程池并发检查代理列表的可用性。
    """
    effective_list: List[str] = []  # 使用局部变量
    logging.info(f"开始检查代理可用性，最大并发数：{max_concurrent}，超时时间：{timeout_sec}秒")
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        future_to_proxy = {
            executor.submit(check_proxy, proxy, check_url, timeout_sec): proxy
            for proxy in proxy_list
        }
        for future in as_completed(future_to_proxy):
            proxy = future_to_proxy[future]
            try:
                if future.result():
                    effective_list.append(proxy)
                    print(f"代理 {proxy} 可用")  # 保留，方便查看
                    logging.info(f"代理 {proxy} 可用")
                else:
                    logging.info(f"代理 {proxy} 不可用")
            except Exception as exc:
                print(f"代理 {proxy} 检查出错: {exc}")  # 保留
                logging.error(f"代理 {proxy} 检查出错: {exc}")

    logging.info(f"代理检查完成，共有 {len(effective_list)} 个代理可用")
    return effective_list


def write_proxies_to_file(filename: str, proxies: List[str]):
    """将代理列表写入文件"""
    logging.info(f"正在将 {len(proxies)} 个代理写入文件 {filename}...")
    try:
        with open(filename, "w") as f:
            for proxy in proxies:
                f.write(proxy + "\n")
        logging.info(f"写入文件 {filename} 完成")
    except Exception as e:
        logging.error(f"写入文件 {filename} 失败: {e}")
