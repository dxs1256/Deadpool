package main

import (
	"Deadpool/utils"
	"fmt"
	"io"
	"log"
	"os"
	"strconv"
	"strings"

	"github.com/armon/go-socks5"
	"github.com/robfig/cron/v3"
	// "github.com/gookit/color"  // 不需要
)

func main() {
	utils.Banner()
	fmt.Print("By:thinkoaa GitHub:https://github.com/thinkoaa/Deadpool\n\n\n")

	// 读取配置文件
	config, err := utils.LoadConfig("config.toml")
	if err != nil {
		fmt.Printf("config.toml配置文件存在错误字符: %d\n", err)
		os.Exit(1)
	}

	fmt.Print("***直接使用fmt打印当前使用的代理,若高并发时,命令行打印可能会阻塞，不对打印做特殊处理，可忽略，不会影响实际的请求转发***\n\n")

	// 修改 GetSocks 函数，使其也从远程 URL 获取代理
	utils.GetSocks = func(config *utils.Config) {
		// 从本地文件获取
		utils.GetSocksFromFile(utils.LastDataFile)

		// 从远程 URL 获取
		remoteURLs := []string{
			"https://raw.githubusercontent.com/TheSpeedX/PROXY-List/refs/heads/master/socks5.txt",
			"https://raw.githubusercontent.com/sunny9577/proxy-scraper/refs/heads/master/proxies.txt",
		}
		for _, url := range remoteURLs {
			//  直接在 GetSocks 函数内部使用 getRemoteSocks (小写 g)
        
			remoteSocks, err := utils.getRemoteSocks(url) // 正确：小写 g
			if err != nil {
				fmt.Printf("从远程 URL %s 获取代理失败: %v\n", url, err)
				continue // 如果一个 URL 失败，继续下一个
			}
			//去重
			for _, proxy := range remoteSocks {
				if !utils.Contains(utils.SocksList, proxy) {
					utils.SocksList = append(utils.SocksList, proxy)
				}
			}
		}

		// 从fofa获取
		utils.Wg.Add(1)
		go utils.GetSocksFromFofa(config.FOFA)
		//从hunter获取
		utils.Wg.Add(1)
		go utils.GetSocksFromHunter(config.HUNTER)
		//从quake中取
		utils.Wg.Add(1)
		go utils.GetSocksFromQuake(config.QUAKE)
		utils.Wg.Wait()
		//根据IP:PORT去重
		utils.RemoveDuplicates(&utils.SocksList)
	}

	utils.GetSocks(config) // 调用 GetSocks, 它会处理本地和远程的代理

	if len(utils.SocksList) == 0 {
		fmt.Println("未发现代理数据,请调整配置信息,或向" + utils.LastDataFile + "中直接写入IP:PORT格式的socks5代理\n程序退出")
		os.Exit(1)
	}
	fmt.Printf("根据IP:PORT去重后，共发现%v个代理\n检测可用性中......\n", len(utils.SocksList))

	//开始检测代理存活性
	utils.Timeout = config.CheckSocks.Timeout
	utils.CheckSocks(config.CheckSocks, utils.SocksList)

	//根据配置，定时检测内存中的代理存活信息
	cron := cron.New()
	periodicChecking := strings.TrimSpace(config.Task.PeriodicChecking)
	cronFlag := false
	if periodicChecking != "" {
		cronFlag = true
		cron.AddFunc(periodicChecking, func() {
			fmt.Printf("\n===代理存活自检 开始===\n\n")
			tempList := make([]string, len(utils.EffectiveList))
			copy(tempList, utils.EffectiveList)
			utils.CheckSocks(config.CheckSocks, tempList)
			fmt.Printf("\n===代理存活自检 结束===\n\n")
		})
	}
	//根据配置信息，周期性取本地以及hunter、quake、fofa的数据
	periodicGetSocks := strings.TrimSpace(config.Task.PeriodicGetSocks)
	if periodicGetSocks != "" {
		cronFlag = true
		cron.AddFunc(periodicGetSocks, func() {
			fmt.Printf("\n===周期性取代理数据 开始===\n\n")
			utils.SocksList = utils.SocksList[:0]
			utils.GetSocks(config) // 再次调用 utils.GetSocks
			fmt.Printf("根据IP:PORT去重后，共发现%v个代理\n检测可用性中......\n", len(utils.SocksList))
			utils.CheckSocks(config.CheckSocks, utils.SocksList)
			if len(utils.EffectiveList) != 0 {
				utils.WriteLinesToFile()
			}
			fmt.Printf("\n===周期性取代理数据 结束===\n\n")

		})
	}

	if cronFlag {
		cron.Start()
	}

	if len(utils.EffectiveList) == 0 {
		fmt.Println("根据规则检测后，未发现满足要求的代理,请调整配置,程序退出")
		os.Exit(1)
	}

	utils.WriteLinesToFile()

	// 开启监听
	conf := &socks5.Config{
		Dial:   utils.DefineDial,
		Logger: log.New(io.Discard, "", log.LstdFlags),
	}
	userName := strings.TrimSpace(config.Listener.UserName)
	password := strings.TrimSpace(config.Listener.Password)
	if userName != "" && password != "" {
		cator := socks5.UserPassAuthenticator{Credentials: socks5.StaticCredentials{
			userName: password,
		}}
		conf.AuthMethods = []socks5.Authenticator{cator}
	}
	server, _ := socks5.New(conf)
	listener := config.Listener.IP + ":" + strconv.Itoa(config.Listener.Port)
	fmt.Printf("======其他工具通过配置 socks5://%v 使用收集的代理,如有账号密码，记得配置======\n", listener)
	if err := server.ListenAndServe("tcp", listener); err != nil {
		fmt.Printf("本地监听服务启动失败：%v\n", err)
		os.Exit(1)
	}
}
