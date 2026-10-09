# 信创终端常见问题

## 银河麒麟系统如何查看系统版本
打开终端，执行 cat /etc/os-release 查看发行版信息，也可以执行 nkvers 查看麒麟系统的详细版本号与内核版本。

## 统信UOS打印机无法打印
1. 检查 CUPS 打印服务是否运行：systemctl status cups，未运行则执行 sudo systemctl restart cups。
2. 在“控制中心-打印机”中删除打印机后重新添加，选择厂商提供的信创版驱动。
3. 清空打印队列：cancel -a，再重新打印测试页。

## 麒麟系统无法连接网络
检查网线或无线开关，执行 ip addr 查看网卡是否获取到 IP 地址；执行 sudo systemctl restart NetworkManager 重启网络服务；若 DNS 解析异常，检查 /etc/resolv.conf 配置。

## U盘无法识别
执行 lsblk 查看是否识别到设备；若终端安装了终端安全管控软件，确认 U 盘是否已授权；NTFS 格式 U 盘需安装 ntfs-3g。

## WPS 打开文档崩溃
清理 WPS 缓存目录 ~/.config/Kingsoft 后重新打开；确认 WPS 为适配当前 CPU 架构（ARM64/x86_64/LoongArch）的版本，必要时升级到最新信创版。

## 飞腾、鲲鹏、海光、兆芯 CPU 架构
飞腾和鲲鹏为 ARM 架构（ARMv8，aarch64）；海光和兆芯为 x86 架构（x86_64）；龙芯为 LoongArch 架构。安装软件时需选择对应架构的安装包。

## 系统空间不足如何清理
可使用小信助手“一键提速-垃圾清理”功能，清理 APT 缓存（sudo apt-get clean / autoclean / autoremove）、/tmp 临时文件、/var/log 历史日志和 ~/.cache 应用缓存；使用“大文件检索”找出大于 100MB 的文件进行清理。

## 禁止安装双系统
根据信创终端管理规定，信创终端不得安装 Windows 双系统，小信助手会在客户端启动时自动检测双系统情况并上报管理后台，违规终端将产生预警。
