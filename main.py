import requests
import toml
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
import socks
import socket
from urllib.parse import urlparse
import re

# 配置日志记录，输出到标准输出，GitHub Actions 会捕获标准输出
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

TIMEOUT = 10
LAST_DATA_FILE = "lastData.txt"  # 确保文件名正确

def load_config(filename: str = "config.toml") -> Dict:
    """加载配置文件"""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return toml.load(f)
    except FileNotFoundError:
        logging.error(f"配置文件 '{filename}' 未找到。")
        exit(1)  # 在 GitHub Actions 中，exit(1) 会导致工作流失败
    except toml.TomlDecodeError as e:
        logging.error(f"解析配置文件 '{filename}' 失败: {e}")
        exit(1)

def get_remote_socks(url: str) -> List[str]:
    """从远程 URL 获取代理列表"""
    logging.info(f"正在从 {url} 获取代理...")
    try:
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        lines = response.text.strip().splitlines()
        proxies = [line.strip() for line in lines if line.strip()]
        logging.info(f"从 {url} 获取到 {len(proxies)} 个代理")
        return proxies
    except requests.RequestException as e:
        logging.error(f"从 {url} 获取代理失败: {e}")  # 记录异常对象
        return []

def check_proxy_requests(proxy_addr: str, check_url: str, timeout: int, retries: int = 3) -> bool:
    """使用 requests 检查代理的可用性（多次测试 + 内容验证）"""
    for _ in range(retries):
        try:
            proxies = {
                "http": f"socks5://{proxy_addr}",
                "https": f"socks5://{proxy_addr}",
            }
            response = requests.get(check_url, proxies=proxies, timeout=timeout)
            response.raise_for_status()

            # 内容验证 (根据需要添加)
            if "google" in check_url.lower():
                if "Google" not in response.text:
                    logging.debug(f"代理 {proxy_addr} 内容验证失败")
                    continue  # 进行下一次重试
            elif "icanhazip" in check_url.lower():
                if not re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", response.text.strip()):
                    logging.debug(f"代理 {proxy_addr} 内容验证失败 (icanhazip)")
                    continue

            return True  # 一次成功就返回True

        except requests.RequestException as e:
            logging.debug(f"代理 {proxy_addr} 不可用 (尝试 {_+1}/{retries}): {e}") # 记录异常
            time.sleep(0.5)  # 短暂延迟后重试

    return False  # 所有尝试都失败

def check_proxy_requests_with_multiple_urls(proxy_addr: str, check_urls: List[str], timeout: int, retries: int) -> bool:
    """检查代理对所有 check_urls 的可用性"""
    for url in check_urls:
        if not check_proxy_requests(proxy_addr, url, timeout, retries):
            return False
    return True


def check_proxy_pysocks(proxy_addr: str, check_url: str, timeout: int, retries: int = 3) -> bool:
    """使用 PySocks 检查 SOCKS5 代理"""
    for _ in range(retries):
        try:
            ip, port_str = proxy_addr.split(":")
            port = int(port_str)

            # 创建 SOCKS5 socket
            s = socks.socksocket()
            s.set_proxy(socks.SOCKS5, ip, port)
            s.settimeout(timeout)

            # 连接到目标地址
            # 提取check_url中的host和port

            parsed_url = urlparse(check_url)
            hostname = parsed_url.hostname
            port_to_connect = parsed_url.port if parsed_url.port else (443 if parsed_url.scheme == 'https' else 80)

            s.connect((hostname, port_to_connect))  # 使用hostname和port
            s.close()  # 连接成功后立即关闭, 我们只需要知道能不能连上

            return True  # 连接成功，是 SOCKS5 代理

        except (socks.ProxyConnectionError, socket.timeout, socket.error, ValueError) as e:
            logging.debug(f"代理 {proxy_addr} 不是有效的 SOCKS5 代理: {e}")
            time.sleep(0.5)
    return False

def check_proxies(proxy_list: List[str], check_urls: List[str], max_concurrent: int, timeout_sec: int, retries:int) -> List[str]:
    """
    使用线程池并发检查代理列表的可用性。
    先用 requests 快速筛选, 再用 PySocks 确认。
    """
    effective_list: List[str] = []
    logging.info(f"开始检查代理可用性，最大并发数：{max_concurrent}，超时时间：{timeout_sec}秒, 重试次数:{retries}")
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        # 第一阶段：requests 初筛
        future_to_proxy = {
            executor.submit(check_proxy_requests_with_multiple_urls, proxy, check_urls, timeout_sec, retries): proxy
            for proxy in proxy_list
        }
        requests_passed_proxies = []
        for future in as_completed(future_to_proxy):
            proxy = future_to_proxy[future]
            try:
                if future.result():
                    requests_passed_proxies.append(proxy)
                    logging.info(f"代理 {proxy} 通过 requests 初步检查")

                else:
                    logging.info(f"代理 {proxy} 未通过 requests 检查")
            except Exception as e:
                logging.error(f"代理 {proxy} requests 检查出错: {e}") # 记录异常

        # 第二阶段：PySocks 确认
        logging.info(f"开始 PySocks 确认，共有 {len(requests_passed_proxies)} 个代理需要确认")
        future_to_proxy = {
            executor.submit(check_proxy_pysocks, proxy, check_urls[0], timeout_sec): proxy #check_urls[0] 只需要一个URL, 因为pysocks只检查连接
            for proxy in requests_passed_proxies
        }

        for future in as_completed(future_to_proxy):
            proxy = future_to_proxy[future]
            try:
                if future.result():
                    effective_list.append(proxy)
                    logging.info(f"代理 {proxy} 通过 PySocks 验证，确认是 SOCKS5 代理")
                else:
                    logging.info(f"代理 {proxy} 未通过 PySocks 验证")
            except Exception as e:
                logging.error(f"代理 {proxy} PySocks 验证出错: {e}") # 记录异常

    logging.info(f"代理检查完成，共有 {len(effective_list)} 个有效 SOCKS5 代理")
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
        logging.error(f"写入文件 {filename} 失败: {e}") # 记录异常

def get_proxies(config: Dict) -> List[str]:
    """获取所有来源的代理，并进行去重"""
    socks_list: List[str] = []

    # 从远程 URL 获取
    remote_urls = config.get("remote_urls", {}).get("urls", [])
    if not remote_urls:
        logging.warning("未配置远程代理 URL 列表 (remote_urls.urls)")

    for url in remote_urls:
        logging.info(f"开始从远程 URL: {url} 获取代理")
        remote_proxies = get_remote_socks(url)
        socks_list.extend(remote_proxies)
        logging.info(f"从 {url} 获取了 {len(remote_proxies)} 个代理")

    # 去重
    logging.info("开始去重...")
    socks_list = list(set(socks_list))  # 使用 set 去重, 更高效
    logging.info(f"去重后，共有 {len(socks_list)} 个代理")
    return socks_list


def main():
    """主函数"""
    logging.info("程序启动")

    config = load_config()

    # 获取并检查代理
    proxies = get_proxies(config)
    logging.info("开始检查代理可用性...")
    valid_proxies = check_proxies(
        proxies,
        config["check_socks"]["check_urls"],
        config["check_socks"]["max_concurrent_req"],
        config["check_socks"]["timeout"],
        config["check_socks"]["retries"],
    )
    logging.info(f"共有 {len(valid_proxies)} 个有效代理")

    # 保存有效代理
    write_proxies_to_file(LAST_DATA_FILE, valid_proxies)
    logging.info(f"有效代理已保存到 {LAST_DATA_FILE}")

    logging.info("程序结束")


if __name__ == "__main__":
    main()
