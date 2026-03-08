AI_Mahjong Release / AI_Mahjong 发布版
======================================

Quick Start / 快速开始
----------------------
1. Double-click `start_all.bat`
   双击 `start_all.bat`
2. Allow the certificate or network prompts if Windows asks
   如果 Windows 弹出证书或网络相关提示，请允许
3. Close existing Chrome or Edge windows, then double-click `launch_browser.bat`
   先关闭已经打开的 Chrome 或 Edge，再双击 `launch_browser.bat`
4. Open Majsoul and start a game
   打开雀魂并开始对局

Port Config / 端口配置
----------------------
- Edit `config/runtime_config.bat` if you want to change the ports.
  如果你想修改端口，或者端口被占用，请关闭程序后，用文本编辑器编辑 `config/runtime_config.bat`。
- Default backend port: `50000`
  默认算法后端端口：`50000`
- Default proxy port: `8080`
  默认代理端口：`8080`
- Default HUD extra scale: `1.0`
  默认 HUD 缩放：`1.0`

Important Notes / 重要说明
--------------------------
- The browser traffic only needs to pass through the proxy port started by `start_all.bat`.
  只要让浏览器流量经过 `start_all.bat` 启动的代理端口，就可以抓取对局数据。
- So you do not have to use `launch_browser.bat`; browser extensions or other proxy tools are also fine.
  因此你不一定要使用 `launch_browser.bat`；也可以改用浏览器插件或其他代理工具。
- The certificate is required so mitmproxy can decrypt local HTTPS/WSS traffic.
  证书用于让 mitmproxy 正常解密本机的 HTTPS/WSS 流量。
