import utils
import time
import schedule  # 用于定时任务（可选）


def get_proxies(config):
    """获取所有来源的代理，并进行去重"""
    utils.socks_list = []  # 清空列表

    # 从远程 URL 获取
    remote_urls = [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt",
    ]
    for url in remote_urls:
        remote_proxies = utils.get_remote_socks(url)
        utils.socks_list.extend(remote_proxies)
        print(f"从 {url} 获取了 {len(remote_proxies)} 个代理")

    # 去重
    utils.socks_list = list(set(utils.socks_list))
    print(f"去重后，共有 {len(utils.socks_list)} 个代理")
    return utils.socks_list


def main():
    config = utils.load_config()

    # 获取并检查代理
    proxies = get_proxies(config)
    utils.timeout = config["check_socks"]["timeout"]
    valid_proxies = utils.check_proxies(proxies, config["check_socks"]["check_url"] , config["check_socks"]["max_concurrent_req"], config["check_socks"]["timeout"]  )
    print(f"共有 {len(valid_proxies)} 个有效代理")

    # 保存有效代理 (可选, 如果你仍然需要的话)
    utils.write_proxies_to_file(utils.last_data_file, valid_proxies)
    print(f"有效代理已保存到 {utils.last_data_file} (可选)")


    # 设置定时任务 (可选)
    if config.get("task") and config["task"].get("periodic_get_socks"):
        schedule.every().day.at(config["task"]["periodic_get_socks"]).do(get_proxies, config) #这里只是举例每天的某个时间点运行一次
        # schedule.every(5).days.do(get_proxies, config) #这里只是举例, 每5天.
        # schedule.every().hour.do(job) #每小时
        # schedule.every().monday.do(job) #每周
        # schedule.every().wednesday.at("13:15").do(job) #每周三13:15
        print(f"已设置定时任务：每 {config['task']['periodic_get_socks']} 执行一次代理获取和检查")
        while True:
            schedule.run_pending()
            time.sleep(60)  # 每分钟检查一次是否有任务需要执行


    # 开启监听(这部分没有实现,  因为原代码是使用Go的库实现的, Python中没有完全对应的库)
    # 如果你需要SOCKS5服务器功能，你需要使用其他的Python库来实现, 例如 asyncio, Twisted 等。


if __name__ == "__main__":
    main()
