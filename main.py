import requests
import toml
import time
import logging
import re
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# 输出文件名
FILE_BAIDU = "Baidu.txt"
FILE_GOOGLE = "Google.txt"
FILE_ALL = "All.txt"  # 存放全能代理
CONFIG_FILE = "config.toml"

def load_config(filename: str = CONFIG_FILE) -> Dict:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return toml.load(f)
    except Exception as e:
        logging.error(f"加载配置文件失败: {e}")
        exit(1)

def get_remote_socks(url: str, timeout: int) -> List[str]:
    """获取远程代理"""
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            lines = response.text.strip().splitlines()
            proxies = [line.strip() for line in lines if re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d+$", line.strip())]
            logging.info(f"源 {url} -> 获取到 {len(proxies)} 个代理")
            return proxies
    except:
        pass
    return []

def check_single_url(proxy_addr: str, check_url: str, timeout: int, retries: int) -> bool:
    """测试单个代理对单个URL的连通性"""
    proxies = {"http": f"socks5://{proxy_addr}", "https": f"socks5://{proxy_addr}"}
    for _ in range(retries):
        try:
            # 发起请求
            resp = requests.get(check_url, proxies=proxies, timeout=timeout)
            
            # 简单的状态码检查
            if resp.status_code != 200:
                continue

            # 内容防劫持检查
            if "baidu" in check_url.lower():
                resp.encoding = 'utf-8' # 防止中文乱码
                if "百度" not in resp.text and "baidu" not in resp.text:
                    return False
            elif "google" in check_url.lower():
                if "Google" not in resp.text:
                    return False
            
            return True # 通过检查
        except:
            time.sleep(0.5)
    return False

def classify_proxy(proxy: str, check_urls: List[str], timeout: int, retries: int) -> Tuple[str, bool, bool]:
    """
    对单个代理进行分类测试
    返回: (代理IP, 是否通百度, 是否通谷歌)
    """
    can_baidu = False
    can_google = False

    # 遍历配置文件中的 URL
    for url in check_urls:
        # 如果是百度链接，且还没测通百度
        if "baidu" in url.lower() and not can_baidu:
            if check_single_url(proxy, url, timeout, retries):
                can_baidu = True
        
        # 如果是谷歌链接，且还没测通谷歌
        if "google" in url.lower() and not can_google:
            if check_single_url(proxy, url, timeout, retries):
                can_google = True
        
        # 如果两个都通了，不需要继续测其他的 URL 了
        if can_baidu and can_google:
            break

    return proxy, can_baidu, can_google

def run_checks(proxies: List[str], config: Dict):
    socks_cfg = config["check_socks"]
    check_urls = socks_cfg["check_urls"]
    timeout = socks_cfg["timeout"]
    retries = socks_cfg["retries"]
    max_workers = socks_cfg["max_concurrent_req"]

    baidu_list = []
    google_list = []
    all_list = [] # 既通百度又通谷歌

    total = len(proxies)
    logging.info(f"开始测试 {total} 个代理，双向检测 (Baidu & Google)...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_proxy = {
            executor.submit(classify_proxy, proxy, check_urls, timeout, retries): proxy 
            for proxy in proxies
        }

        completed = 0
        for future in as_completed(future_to_proxy):
            completed += 1
            if completed % 50 == 0:
                logging.info(f"进度: {completed}/{total} | 百度: {len(baidu_list)} | 谷歌: {len(google_list)} | 全能: {len(all_list)}")
            
            try:
                proxy, ok_baidu, ok_google = future.result()
                
                # 逻辑分流
                if ok_baidu:
                    baidu_list.append(proxy)
                
                if ok_google:
                    google_list.append(proxy)
                
                # 如果两个都为 True，则加入全能列表
                if ok_baidu and ok_google:
                    all_list.append(proxy)

            except Exception as e:
                pass

    return baidu_list, google_list, all_list

def write_file(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            for item in data:
                f.write(item + "\n")
        logging.info(f"已写入 {filename}: {len(data)} 个")
    except Exception as e:
        logging.error(f"写入文件 {filename} 失败: {e}")

def main():
    config = load_config()
    
    # 1. 获取代理
    all_proxies = []
    remote_urls = config.get("remote_urls", {}).get("urls", [])
    if not remote_urls:
        logging.error("未在 config.toml 找到 remote_urls")
        return

    # 设置一个获取时的超时，防止卡住
    fetch_timeout = config.get("check_socks", {}).get("timeout", 10)

    for url in remote_urls:
        all_proxies.extend(get_remote_socks(url, fetch_timeout))
    
    unique_proxies = list(set(all_proxies))
    logging.info(f"去重后共 {len(unique_proxies)} 个代理待检测")

    if not unique_proxies:
        logging.error("没有获取到任何代理 IP，请检查网络或源地址。")
        return

    # 2. 分类检测
    baidu_proxies, google_proxies, all_proxies_list = run_checks(unique_proxies, config)

    # 3. 保存结果
    logging.info("="*40)
    if baidu_proxies:
        write_file(FILE_BAIDU, baidu_proxies)
    if google_proxies:
        write_file(FILE_GOOGLE, google_proxies)
    if all_proxies_list:
        write_file(FILE_ALL, all_proxies_list)
    else:
        logging.info(f"本次未扫描到全能代理，{FILE_ALL} 不会写入。")
    logging.info("="*40)

if __name__ == "__main__":
    main()
