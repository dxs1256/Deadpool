import requests
import toml
import time
import logging
import socks
import socket
from urllib.parse import urlparse
import re
import uuid
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

LAST_DATA_FILE = "lastData.txt"  # 输出文件名

def load_config(filename: str = "config.toml") -> Dict:
    """加载配置文件"""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return toml.load(f)
    except (FileNotFoundError, toml.TomlDecodeError) as e:
        logging.error(f"加载配置文件 '{filename}' 失败: {e}")
        exit(1)

def get_remote_socks(url: str, timeout:int) -> List[str]:
    """从远程 URL 获取代理列表"""
    logging.info(f"正在从 {url} 获取代理...")
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        lines = response.text.strip().splitlines()
        proxies = [line.strip() for line in lines if line.strip()]
        logging.info(f"从 {url} 获取到 {len(proxies)} 个代理")
        return proxies
    except requests.RequestException as e:
        logging.error(f"从 {url} 获取代理失败: {e}")
        return []

def check_proxy_requests(proxy_addr: str, check_url: str, timeout:int, retries:int) -> bool:
    """使用 requests 检查代理的可用性（多次测试 + 内容验证）"""
    for _ in range(retries):
        try:
            proxies = {
                "http": f"socks5://{proxy_addr}",
                "https": f"socks5://{proxy_addr}",
            }
            response = requests.get(check_url, proxies=proxies, timeout=timeout)
            response.raise_for_status()

            # 内容验证
            if "google" in check_url.lower():
                if "Google" not in response.text:
                    logging.debug(f"代理 {proxy_addr} 内容验证失败")
                    continue
            elif "icanhazip" in check_url.lower():
                if not re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", response.text.strip()):
                    logging.debug(f"代理 {proxy_addr} 内容验证失败 (icanhazip)")
                    continue

            return True

        except requests.RequestException as e:
            logging.debug(f"代理 {proxy_addr} 不可用 (尝试 {_+1}/{retries}): {e}")
            time.sleep(0.5)

    return False

def check_proxy_requests_with_multiple_urls(proxy_addr: str, check_urls: List[str], timeout:int, retries: int) -> bool:
    """检查代理对所有 check_urls 的可用性"""
    for url in check_urls:
        if not check_proxy_requests(proxy_addr, url, timeout, retries):
            return False
    return True

def check_proxy_pysocks(proxy_addr: str, check_url:str, timeout:int, retries:int) -> bool:
    """使用 PySocks 检查 SOCKS5 代理"""
    for _ in range(retries):
        try:
            ip, port_str = proxy_addr.split(":")
            port = int(port_str)
            s = socks.socksocket()
            s.set_proxy(socks.SOCKS5, ip, port)
            s.settimeout(timeout)
            parsed_url = urlparse(check_url)
            hostname = parsed_url.hostname
            port_to_connect = parsed_url.port if parsed_url.port else (443 if parsed_url.scheme == 'https' else 80)
            s.connect((hostname, port_to_connect))
            s.close()
            return True

        except (socks.ProxyConnectionError, socket.timeout, socket.error, ValueError) as e:
            logging.debug(f"代理 {proxy_addr} 不是有效的 SOCKS5 代理: {e}")
            time.sleep(0.5)
    return False

def check_proxies(proxy_list: List[str], check_urls:List[str], max_concurrent:int, timeout:int, retries:int) -> List[str]:
    """检查代理"""
    effective_list: List[str] = []
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        future_to_proxy = {
            executor.submit(check_proxy_requests_with_multiple_urls, proxy, check_urls, timeout, retries): proxy
            for proxy in proxy_list
        }
        requests_passed_proxies = []
        for future in as_completed(future_to_proxy):
            proxy = future_to_proxy[future]
            if future.result():
                requests_passed_proxies.append(proxy)
        
        future_to_proxy = {
            executor.submit(check_proxy_pysocks, proxy, check_urls[0], timeout, retries): proxy # check_urls[0]
            for proxy in requests_passed_proxies
        }
        for future in as_completed(future_to_proxy):
            proxy = future_to_proxy[future]
            if future.result():
                effective_list.append(proxy)

    return effective_list

def write_proxies_to_file(filename: str, proxies: List[str]):
    """写入文件"""
    try:
        with open(filename, "w") as f:
            for proxy in proxies:
                f.write(proxy + "\n")
        logging.info(f"已将 {len(proxies)} 个代理写入 {filename}")
    except Exception as e:
        logging.error(f"写入文件失败: {e}")

def main():
    """主函数"""
    config = load_config()  # 加载配置

    all_proxies = []
    for url in config["remote_urls"]["urls"]:
        all_proxies.extend(get_remote_socks(url, config["check_socks"]["timeout"]))

    unique_proxies = list(set(all_proxies))
    logging.info(f"共获取到 {len(unique_proxies)} 个不重复的代理")

    valid_proxies = check_proxies(
        unique_proxies,
        config["check_socks"]["check_urls"],
        config["check_socks"]["max_concurrent_req"],
        config["check_socks"]["timeout"],
        config["check_socks"]["retries"]
    )
    logging.info(f"共有 {len(valid_proxies)} 个有效 SOCKS5 代理")

    write_proxies_to_file(LAST_DATA_FILE, valid_proxies)

if __name__ == "__main__":
    main()
