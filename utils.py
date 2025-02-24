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
last_data_file = "lastData.txt"

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

def read_proxies_from_file(filename):
    """从文件中读取代理列表"""
    try:
        with open(filename, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
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

def base64_encode(s):
    """Base64 编码"""
    return base64.b64encode(s.encode()).decode()

def json_encode(data):
    """JSON 编码"""
    return json.dumps(data)

def json_decode(json_str, result):
    """JSON 解码"""
    return json.loads(json_str)
    

def get_fofa_proxies(config):
    """从 FOFA 获取代理"""
    if not (config.get("fofa") and config.get("email") and config.get("key") and config.get("rule")):

        return []

    url = config["fofa"]["url"] + "/api/v1/search/all"
    params = {
        "email": config["fofa"]["email"],
        "key": config["fofa"]["key"],
        "qbase64": base64_encode(config["fofa"]["rule"]),
        "size": config.get("size", 100),  # 默认获取 100 条
        "fields": "host",
    }
    content = fetch_content(url, params=params)
    if content:
        try:
            fofa_data = json.loads(content)
            if fofa_data.get("error"):
                print(f"FOFA API 错误: {fofa_data.get('errmsg')}")
                return []
            proxies = []
            for result in fofa_data.get("results", []):
                host = result[0]
                # 移除可能存在的 http:// 或 https:// 前缀
                host = host.replace("https://", "").replace("http://", "")
                #如果获取的数据不包含：则默认为80端口
                if ":" not in host:
                    host += ":80"
                if host.count(":") >= 2:  # 类似于这种IP:PORT:80,去除后面的:80
                    index = host.rfind(":")   # 获取最后一个冒号的索引
                    host = host[:index]
                proxies.append(host)
            return proxies
        except json.JSONDecodeError:
            print("解析 FOFA 数据失败")
            return []
    return []


def get_hunter_proxies(config):
    """从 Hunter 获取代理"""
    if not (config.get("hunter") and config.get("key")  and config.get("rule")):
        return []

    url = config["hunter"]["url"] + "/openApi/getIp"
    page_size = 100
    page_count = 1
    if config.get("hunter").get("size",page_size) < page_size:
         page_size = config.get("hunter").get("size")
    else:
        page_count = config["hunter"]["size"] // page_size
        if config["hunter"]["size"] % page_size != 0:
            page_count+=1

    proxies = []
    for i in range(1,page_count+1):
        params = {
            "api-key": config["hunter"]["key"],
            "search": base64_encode(config["hunter"]["rule"]),
            "page": str(i),
            "page_size": str(page_size),
            "is_web": "3",
            "port_filter":"false",
            "status_code":"200,401,302"
        }
        content = fetch_content(url, params=params)
        if content:
            try:
                hunter_data = json.loads(content)
                if hunter_data.get("code") != 200:
                    print(f"Hunter API 错误: {hunter_data.get('message')}")
                    return []

                for result in hunter_data["data"]["arr"]:
                    tmp = result["url"]
                    tmp =  tmp.replace("https://", "").replace("http://", "")
                    #如果获取的数据不包含：则默认为80端口
                    if ":" not in tmp:
                        tmp = tmp + ":80"
                    if tmp.count(":") >= 2:  #类似于这种IP:PORT:80,去除后面的:80
                        index = tmp.rfind(":")   # 获取最后一个冒号的索引
                        tmp = tmp[:index]
                    proxies.append(tmp)
            except json.JSONDecodeError:
                print("解析 Hunter 数据失败")
                return []
    return proxies

def get_quake_proxies(config):
    """从 Quake 获取代理"""
    if not (config.get("quake") and config.get("key") and config.get("rule")):
        return []

    url = config["quake"]["url"] + "/v3/search/quake_service"
    page_size = 500
    page_count = 1
    if config.get("quake").get("size",page_size) < page_size:
        page_size = config.get("quake").get("size")
    else:
        page_count = config["quake"]["size"] // page_size

        if config["quake"]["size"] % page_size != 0:
            page_count+=1
    proxies = []
    for i in range(1, page_count+1):
        headers = {
            "X-QuakeToken": config["quake"]["key"],
            "Content-Type": "application/json"
        }
        # startTime := time.Now().AddDate(0, 0, -1).Format("2006-01-02T15:04:05+08:00") #当前时间的前一天
        # endTime := time.Now().Format("2006-01-02T15:04:05+08:00")
        post_data = {
            "query": config["quake"]["rule"],
            "start": 0,
            "size": page_size,
            # "start_time": startTime, #开始时间
            # "end_time":   endTime,   #结束时间

        }

        content = fetch_content(url, method="POST", headers=headers, json_data=post_data)

        if content:
            try:
                quake_data = json.loads(content)
                if quake_data.get("code") != 0:
                    print(f"Quake API 错误: {quake_data.get('message')}")
                    return []
                for result in quake_data["data"]:
                        tmp = result["ip"] + ":" + str(result["port"])
                        if "[" in tmp:
                            tmp = tmp.replace("[","").replace("]","")
                        if ":" not in tmp:
                            tmp = tmp+":80"
                        if tmp.count(":") >= 2:  #类似于这种IP:PORT:80,去除后面的:80
                            index = tmp.rfind(":")   # 获取最后一个冒号的索引
                            tmp = tmp[:index]
                        proxies.append(tmp)
            except json.JSONDecodeError:
                print("解析 Quake 数据失败")
                return []
    return proxies

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
