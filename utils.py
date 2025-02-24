import requests
import toml
import base64
import json
import socks  # PySocks
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import logging  # 导入 logging 模块


# 全局变量
socks_list = []
effective_list = []
timeout = 10  # 默认超时时间
last_data_file = "lastData.txt" #你可以选择删除

def load_config(filename="config.toml"):
    """加载配置文件"""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            config = toml.load(f)
            return config
    except FileNotFoundError:
        logging.error(f"配置文件 '{filename}' 未找到。")
        exit(1)
    except toml.TomlDecodeError as e:
        logging.error(f"解析配置文件 '{filename}' 失败: {e}")
        exit(1)



def get_remote_socks(url):
    """从远程 URL 获取代理列表"""
    logging.info(f"正在从 {url} 获取代理...")
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        lines = response.text.strip().splitlines()
        # 简单地假设每行都是一个代理，格式为 ip:port
        proxies =  [line.strip() for line in lines if line.strip()]
        logging.info(f"从 {url} 获取到 {len(proxies)} 个代理")
        return proxies
    except requests.RequestException as e:
        logging.error(f"从 {url} 获取代理失败: {e}")
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
    except requests.RequestException as e:
        logging.debug(f"代理 {proxy_addr} 不可用: {e}")
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
                    print(f"代理 {proxy} 可用")#保留, 方便查看
                    logging.info(f"代理 {proxy} 可用")
                else:
                     logging.info(f"代理 {proxy} 不可用")
            except Exception as exc:
                print(f"代理 {proxy} 检查出错: {exc}") #保留, 方便查看
                logging.error(f"代理 {proxy} 检查出错: {exc}")

    logging.info(f"代理检查完成，共有 {len(effective_list)} 个代理可用")
    return effective_list


def write_proxies_to_file(filename, proxies):
    """将代理列表写入文件"""
    logging.info(f"正在将 {len(proxies)} 个代理写入文件 {filename}...")
    with open(filename, "w") as f:
        for proxy in proxies:
            f.write(proxy + "\n")
    logging.info(f"写入文件 {filename} 完成")
# FOFAConfig fofa的配置
class FOFAConfig:
    def __init__(self, email="", key="", url="", rule="", size=100):
        self.email = email
        self.key = key
        self.url = url
        self.rule = rule
        self.size = size

# FofaData 定义 FOFA API 响应的数据结构
class FofaData:
    def __init__(self):
        self.error =  False
        self.errmsg = ""
        self.mode = ""
        self.page =  1
        self.query = ""
        self.results = []
        self.size = 10

# HUNTERConfig 猎鹰的配置
class HUNTERConfig:
    def __init__(self, key="", url="", rule="", size=100):
        self.key = key
        self.url = url
        self.rule = rule
        self.size = size

# HunterData 定义猎鹰API的响应数据结构
class HunterData:
    def __init__(self):
        self.code = 0
        self.message = ""
        self.data = {"total":0,"time":0,"arr":[]}
class ArrData:
    def __init__(self):
        self.is_risk = ""
        self.url = ""
        self.ip = ""
        self.port = 0
        self.web_title = ""
        self.domain = ""
        self.is_risk_desc = ""
# QUAKEConfig quake的配置
class QUAKEConfig:
     def __init__(self, key="", url="", rule="", size=100):
        self.key = key
        self.url = url
        self.rule = rule
        self.size = size

class QuakePostData:
    def __init__(self,query = "",start = 0,size = 0,start_time = "",end_time = ""):
        self.query = query
        self.start = start
        self.size = size
        self.start_time = start_time
        self.end_time = end_time

# QuakeData 定义quake API的响应数据结构
class QuakeData:
    def __init__(self):
        self.code = 0
        self.message = ""
        self.meta = {}
class MetaData:
    def __init__(self):
        self.pagination = {}
class PaginationData:
    def __init__(self):
        self.count = 0
        self.page_index = 1
        self.page_size = 0
        self.total = 0
class DataData:
    def __init__(self):
        self.asn = 0
        self.hostname = ""
        self.ip = ""
        self.port = 0
        self.time = ""
        self.transport = ""
        self.service = {}
class ServiceData:
     def __init__(self):
        self.name = ""
        self.version = ""
        self.http = {}
class HttpData:
    def __init__(self):
        self.title =""
class CheckGeolocateConfig:
    def __init__(self,switch="close",check_url="",include_keywords=[],exclude_keywords=[]):
        self.switch = switch
        self.check_url = check_url
        self.include_keywords = include_keywords
        self.exclude_keywords = exclude_keywords

# CheckSocksConfig 检查Socks代理的配置
class CheckSocksConfig:
    def __init__(self,max_concurrent_req=50,timeout=10,check_url="https://www.google.com",check_rsp_keywords="</body>",check_geolocate=None):
        self.max_concurrent_req = max_concurrent_req
        self.timeout = timeout
        self.check_url = check_url
        self.check_rsp_keywords = check_rsp_keywords
        self.check_geolocate = check_geolocate

# TaskConfig 定时任务配置
class TaskConfig:
    def __init__(self,periodic_checking="",periodic_get_socks=""):
        self.periodic_checking = periodic_checking
        self.periodic_get_socks = periodic_get_socks

# ListenerConfig 监听配置
class ListenerConfig:
    def __init__(self,ip="127.0.0.1",port=1080,user_name="",password=""):
        self.ip = ip
        self.port = port
        self.user_name = user_name
        self.password = password

# Config 配置文件解析
class Config:
     def __init__(self,fofa=None, hunter=None, quake=None, check_socks=None, task=None, listener=None):
        self.fofa = fofa
        self.hunter = hunter
        self.quake = quake
        self.check_socks = check_socks
        self.task = task
        self.listener = listener

Logo = """
	______     ______   ______     ______     ______     ____   __  __     ______     ______    
	/\  __ \   /\__  _\ /\  __ \   /\  == \   /\  ___\   /\  _ \ /\ \/\ \   /\  ___\   /\  __ \   
	\ \ \/\ \  \/_/\ \/ \ \  __ \  \ \  __<   \ \  __\   \ \ \_  \ \ \_\ \  \ \  __\   \ \ \/\ \  
	 \ \_____\    \ \_\  \ \_\ \_\  \ \_\ \_\  \ \_____\  \ \  _\  \ \_____\  \ \_____\  \ \_____\ 
	  \/_____/     \/_/   \/_/\/_/   \/_/ /_/   \/_____/   \/_/  \/  \/_____/   \/_____/   \/_____/ 
	"""
Logo += "\t\t\t\tdeadpool v1.0\n"

def Banner():
     print(Logo)
