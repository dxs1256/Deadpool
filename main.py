import requests
import toml
import time
import logging
import re
import os
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# 输出文件名定义
FILE_BAIDU = "Baidu.txt"
FILE_GOOGLE = "Google.txt"
FILE_ALL = "All.txt"
FILE_YAML = "proxyConfig.yaml"  # 新增 YAML 配置文件名
CONFIG_FILE = "config.toml"

def load_config(filename: str = CONFIG_FILE) -> Dict:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return toml.load(f)
    except Exception as e:
        logging.error(f"加载配置文件失败: {e}")
        logging.error("请确保当前目录下有 config.toml 文件")
        exit(1)

def clear_old_files():
    """程序启动时，清理旧的结果文件"""
    files = [FILE_BAIDU, FILE_GOOGLE, FILE_ALL, FILE_YAML]
    for f in files:
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass

def get_remote_socks(url: str, timeout: int) -> List[str]:
    """获取远程代理"""
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            lines = response.text.strip().splitlines()
            # 正则提取 IP:Port
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
            resp = requests.get(check_url, proxies=proxies, timeout=timeout)
            if resp.status_code != 200:
                continue

            # 内容验证：防止劫持
            if "baidu" in check_url.lower():
                resp.encoding = 'utf-8'
                if "百度" not in resp.text and "baidu" not in resp.text:
                    return False
            elif "google" in check_url.lower():
                if "Google" not in resp.text:
                    return False
            
            return True
        except:
            time.sleep(0.5)
    return False

def classify_proxy(proxy: str, check_urls: List[str], timeout: int, retries: int) -> Tuple[str, bool, bool]:
    """
    分类测试：
    返回: (IP, 能否上百度, 能否上谷歌)
    """
    can_baidu = False
    can_google = False

    for url in check_urls:
        # 测试百度
        if "baidu" in url.lower() and not can_baidu:
            if check_single_url(proxy, url, timeout, retries):
                can_baidu = True
        
        # 测试谷歌
        if "google" in url.lower() and not can_google:
            if check_single_url(proxy, url, timeout, retries):
                can_google = True
        
        # 如果都通了，提前结束
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
    all_list = []

    total = len(proxies)
    logging.info(f"开始测试 {total} 个代理...")

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
                
                if ok_baidu:
                    baidu_list.append(proxy)
                if ok_google:
                    google_list.append(proxy)
                if ok_baidu and ok_google:
                    all_list.append(proxy)

            except Exception:
                pass

    return baidu_list, google_list, all_list

def write_file(filename, data):
    """写入普通文本文件 (IP:Port)"""
    if not data:
        return
    try:
        with open(filename, "w", encoding="utf-8") as f:
            for item in data:
                f.write(item + "\n")
        logging.info(f"已生成文件: {filename} (包含 {len(data)} 个代理)")
    except Exception as e:
        logging.error(f"写入 {filename} 失败: {e}")

def write_yaml_config(filename, data):
    """
    将全能代理写入 YAML 配置文件
    格式要求:
    ProxyUrls :
      - ""
      - "socks5://x.x.x.x:port"
    """
    if not data:
        # 即使没有数据，可能也需要生成一个只有空字符串的配置，视需求而定
        # 这里设定为如果没有数据就不生成，或者生成仅含 "" 的列表
        pass

    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write("ProxyUrls :\n")
            # 写入第一个空项
            f.write('  - ""\n')
            # 写入代理列表
            for item in data:
                # 假设 item 是 "IP:Port" 格式，需要拼上前缀
                f.write(f'  - "socks5://{item}"\n')
        logging.info(f"已生成 YAML 配置文件: {filename}")
    except Exception as e:
        logging.error(f"写入 {filename} 失败: {e}")

def main():
    # 0. 清理旧文件
    clear_old_files()

    config = load_config()
    
    # 1. 获取代理
    all_proxies = []
    urls = config.get("remote_urls", {}).get("urls", [])
    fetch_timeout = config.get("check_socks", {}).get("timeout", 10)

    if not urls:
        logging.error("配置文件中没有 remote_urls")
        return

    for url in urls:
        all_proxies.extend(get_remote_socks(url, fetch_timeout))
    
    unique_proxies = list(set(all_proxies))
    logging.info(f"去重后共 {len(unique_proxies)} 个代理待检测")

    if not unique_proxies:
        logging.error("未获取到代理，程序结束。")
        return

    # 2. 分类检测
    baidu_proxies, google_proxies, all_proxies_list = run_checks(unique_proxies, config)

    # 3. 保存结果
    logging.info("="*40)
    
    if baidu_proxies:
        write_file(FILE_BAIDU, baidu_proxies)
    else:
        logging.info(f"未发现百度代理")

    if google_proxies:
        write_file(FILE_GOOGLE, google_proxies)
    else:
        logging.info(f"未发现谷歌代理")

    if all_proxies_list:
        write_file(FILE_ALL, all_proxies_list)
        # 额外生成 proxyConfig.yaml
        write_yaml_config(FILE_YAML, all_proxies_list)
    else:
        logging.info(f"未发现全能代理")

    logging.info("="*40)

if __name__ == "__main__":
    main()
