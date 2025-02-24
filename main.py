import utils
import time
import schedule
import logging  # 导入 logging 模块

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def get_proxies(config):
    """获取所有来源的代理，并进行去重"""
    utils.socks_list = []  # 清空列表

    # 从远程 URL 获取
    # remote_urls = [
    #     "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
    #     "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt",
    # ]
    # 改为从配置文件读取
    remote_urls = config.get("remote_urls", {}).get("urls", []) # 增加一个判断
    if not remote_urls:
        logging.warning("未配置远程代理 URL 列表 (remote_urls.urls)")
        

    for url in remote_urls:
        logging.info(f"开始从远程 URL: {url} 获取代理")
        remote_proxies = utils.get_remote_socks(url)
        utils.socks_list.extend(remote_proxies)
        logging.info(f"从 {url} 获取了 {len(remote_proxies)} 个代理")


    # 去重
    logging.info("开始去重...")
    utils.socks_list = list(set(utils.socks_list))  # 使用 set 去重, 更高效
    logging.info(f"去重后，共有 {len(utils.socks_list)} 个代理")
    return utils.socks_list


def main():
    logging.info("程序启动")

    config = utils.load_config()

    # 获取并检查代理
    proxies = get_proxies(config)
    logging.info("开始检查代理可用性...")
    utils.timeout = config["check_socks"]["timeout"]
    valid_proxies = utils.check_proxies(
        proxies,
        config["check_socks"]["check_url"],
        config["check_socks"]["max_concurrent_req"],
        config["check_socks"]["timeout"],
    )
    logging.info(f"共有 {len(valid_proxies)} 个有效代理")

    # 保存有效代理 (可选)
    utils.write_proxies_to_file(utils.LAST_DATA_FILE, valid_proxies) # 使用utils中的常量
    logging.info(f"有效代理已保存到 {utils.LAST_DATA_FILE}")

    # 设置定时任务 (可选)
    if config.get("task") and config["task"].get("periodic_get_socks"):
        schedule.every().day.at(config["task"]["periodic_get_socks"]).do(
            get_proxies, config
        )
        logging.info(f"已设置定时任务：每 {config['task']['periodic_get_socks']} 执行一次代理获取和检查")
        while True:
            schedule.run_pending()
            time.sleep(60)  # 每分钟检查一次是否有任务需要执行
            logging.info("定时任务：等待下一次执行...")

    # 开启监听(这部分没有实现,  因为原代码是使用Go的库实现的, Python中没有完全对应的库)
    # 如果你需要SOCKS5服务器功能，你需要使用其他的Python库来实现, 例如 asyncio, Twisted 等。
    logging.info("程序结束")


if __name__ == "__main__":
    main()
