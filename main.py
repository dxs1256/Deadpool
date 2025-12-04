import requests
import toml
import time
import logging
import socks
import socket
from urllib.parse import urlparse
import re
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置日志记录 (输出到标准输出)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

LAST_DATA_FILE = "lastData.txt"
CONFIG_FILE = "config.toml"

def load_config(filename: str = CONFIG_FILE) -> Dict:
    """加载配置文件"""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return toml.load(f)
    except (FileNotFoundError, toml.TomlDecodeError) as e:
        logging.error(f"加载配置文件 '{filename}' 失败: {e}")
        logging.error("请确保当前目录下存在 config.toml 文件且格式正确。")
        exit(1)

def get_remote_socks(url: str, timeout: int) -> List[str]:
    """从远程 URL 获取代理列表"""
    logging.info(f"正在从 {url} 获取代理...")
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        # 处理不同格式，有些是用换行，有些可能包含其他字符
        lines = response.text.strip().splitlines()
        proxies = []
        for line in lines:
            line = line.strip()
            # 简单的正则匹配 IP:Port
            if re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d+$", line):
                proxies.append(line)
        
        logging.info(f"从 {url} 获取到 {len(proxies)} 个格式正确的代理")
        return proxies
    except requests.RequestException as e:
        logging.error(f"从 {url} 获取代理失败: {e}")
        return []

def check_proxy_requests(proxy_addr: str, check_url: str, timeout: int, retries: int) -> bool:
    """使用 requests 检查代理的可用性（多次测试 + 内容验证）"""
    for attempt in range(1, retries + 1):
        try:
            proxies = {
                "http": f"socks5://{proxy_addr}",
                "https": f"socks5://{proxy_addr}",
            }
            logging.debug(f"尝试 {attempt}/{retries}：使用 requests 检查代理 {proxy_addr} 对 {check_url} 的可用性...") 
            
            # 发起请求
            response = requests.get(check_url, proxies=proxies, timeout=timeout)
            response.raise_for_status()

            # --- 内容验证逻辑 (防止劫持) ---
            lower_url = check_url.lower()
            
            if "google" in lower_url:
                if "Google" not in response.text:
                    logging.debug(f"代理 {proxy_addr} 内容验证失败 (Google)")
                    continue
            
            elif "icanhazip" in lower_url:
                # 验证是否返回了纯 IP 地址
                if not re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", response.text.strip()):
                    logging.debug(f"代理 {proxy_addr} 内容验证失败 (icanhazip)")
                    continue
            
            elif "baidu" in lower_url:
                # 百度内容验证：防止被跳转到广告页
                # 设置编码以正确识别中文
                response.encoding = 'utf-8' 
                if "百度" not in response.text and "baidu" not in response.text:
                    logging.debug(f"代理 {proxy_addr} 内容验证失败 (Baidu)")
                    continue
            # ---------------------------

            logging.debug(f"代理 {proxy_addr} 通过 requests 检查 ({check_url})")
            return True

        except requests.RequestException as e:
            logging.debug(f"尝试 {attempt}/{retries}：代理 {proxy_addr} 不可用 ({check_url}): {e}")
            time.sleep(0.5)

    logging.debug(f"代理 {proxy_addr} 未通过 requests 检查 ({check_url})")
    return False

def check_proxy_requests_with_multiple_urls(proxy_addr: str, check_urls: List[str], timeout: int, retries: int) -> bool:
    """检查代理对所有 check_urls 的可用性"""
    # 只要有一个 URL 检查失败，该代理即被视为无效（或者你可以修改逻辑为“只要有一个成功就算成功”）
    # 目前逻辑：必须全部通过
    for url in check_urls:
        if not check_proxy_requests(proxy_addr, url, timeout, retries):
            return False
    return True

def check_proxy_pysocks(proxy_addr: str, check_url: str, timeout: int, retries: int) -> bool:
    """使用 PySocks 检查 SOCKS5 握手协议"""
    for attempt in range(1, retries + 1):
        try:
            ip, port_str = proxy_addr.split(":")
            port = int(port_str)
            
            s = socks.socksocket()
            s.set_proxy(socks.SOCKS5, ip, port)
            s.settimeout(timeout)
            
            parsed_url = urlparse(check_url)
            hostname = parsed_url.hostname
            # 默认端口处理
            port_to_connect = parsed_url.port if parsed_url.port else (443 if parsed_url.scheme == 'https' else 80)
            
            logging.debug(f"尝试 {attempt}/{retries}：使用 PySocks 检查代理 {proxy_addr}...") 
            s.connect((hostname, port_to_connect))
            s.close() # 握手成功即关闭
            
            logging.debug(f"代理 {proxy_addr} 通过 PySocks 检查")
            return True

        except (socks.ProxyConnectionError, socket.timeout, socket.error, ValueError) as e:
            logging.debug(f"尝试 {attempt}/{retries}：代理 {proxy_addr} 不是有效的 SOCKS5 代理: {e}")
            time.sleep(0.5)

    logging.debug(f"代理 {proxy_addr} 未通过 PySocks 检查")
    return False

def check_proxies(proxy_list: List[str], check_urls: List[str], max_concurrent: int, timeout: int, retries: int) -> List[str]:
    """主检查流程"""
    effective_list: List[str] = []
    
    # 去重
    proxy_list = list(set(proxy_list))
    total_proxies = len(proxy_list)
    logging.info(f"开始检查代理，待检查总数: {total_proxies}")
    logging.info(f"参数配置 -> 并发: {max_concurrent}, 超时: {timeout}s, 重试: {retries}, 目标URL: {check_urls}")

    # 第一阶段：HTTP/HTTPS 连通性检查 (Requests)
    requests_passed_proxies = []
    logging.info(">>> 进入第一阶段：HTTP 请求连通性检查...")
    
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        future_to_proxy = {
            executor.submit(check_proxy_requests_with_multiple_urls, proxy, check_urls, timeout, retries): proxy
            for proxy in proxy_list
        }
        
        finished_count = 0
        for future in as_completed(future_to_proxy):
            proxy = future_to_proxy[future]
            finished_count += 1
            if finished_count % 100 == 0:
                logging.info(f"第一阶段进度: {finished_count}/{total_proxies}")
                
            try:
                if future.result():
                    requests_passed_proxies.append(proxy)
                    # logging.info(f"代理 {proxy} 通过 HTTP 检查") 
            except Exception as e:
                logging.debug(f"代理 {proxy} 检查出错: {e}")

    logging.info(f"第一阶段完成，剩余 {len(requests_passed_proxies)} 个代理。")

    if not requests_passed_proxies:
        logging.warning("没有代理通过第一阶段检查，程序提前结束。")
        return []

    # 第二阶段：协议握手检查 (PySocks)
    # 说明：能通过 HTTP 检查通常也能通过 SOCKS 检查，但这步可以剔除那些虽然能转发 HTTP 但协议实现不标准的代理
    logging.info(">>> 进入第二阶段：SOCKS5 协议握手检查...")
    
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        # 使用列表中的第一个 URL 进行握手测试即可
        target_url = check_urls[0] 
        future_to_proxy = {
            executor.submit(check_proxy_pysocks, proxy, target_url, timeout, retries): proxy
            for proxy in requests_passed_proxies
        }
        
        for future in as_completed(future_to_proxy):
            proxy = future_to_proxy[future]
            try:
                if future.result():
                    effective_list.append(proxy)
                    logging.info(f"√ 有效代理确认: {proxy}")
            except Exception as e:
                logging.error(f"代理 {proxy} PySocks 验证出错：{e}")

    logging.info(f"代理检查全部完成，最终有效 SOCKS5 代理数: {len(effective_list)}")
    return effective_list

def write_proxies_to_file(filename: str, proxies: List[str]):
    """写入结果到文件"""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            for proxy in proxies:
                f.write(proxy + "\n")
        logging.info(f"已将结果写入 {filename}")
    except Exception as e:
        logging.error(f"写入文件失败: {e}")

def main():
    """主函数"""
    config = load_config()

    # 1. 获取所有代理
    all_proxies = []
    remote_urls = config.get("remote_urls", {}).get("urls", [])
    
    if not remote_urls:
        logging.error("配置文件中未找到 remote_urls.urls")
        return

    # 获取超时配置
    socks_config = config.get("check_socks", {})
    timeout = socks_config.get("timeout", 10)
    
    for url in remote_urls:
        all_proxies.extend(get_remote_socks(url, timeout))

    if not all_proxies:
        logging.error("未获取到任何代理，请检查网络或源地址。")
        return

    # 2. 检查代理
    valid_proxies = check_proxies(
        all_proxies,
        socks_config.get("check_urls", ["http://www.google.com"]),
        socks_config.get("max_concurrent_req", 50),
        timeout,
        socks_config.get("retries", 3)
    )

    # 3. 写入文件
    if valid_proxies:
        write_proxies_to_file(LAST_DATA_FILE, valid_proxies)
    else:
        logging.warning("本次运行未发现可用代理，未写入文件。")
        
    logging.info("程序结束")

if __name__ == "__main__":
    main()
