# 恩山论坛签到

入口为 `script/enshan/sign_in.py`，直接读取青龙环境变量 `ENSHAN_COOKIE`，
与仓库现有恩山脚本共用变量名。多个账号用换行或 `&` 分隔。
未设置该变量时，兼容读取 `config/token.json` 的 `enshan.accounts`；不需要把账号配置提交到Git。
通知使用青龙的 `notify.send`，未提供通知模块时只打印结果，不依赖原项目的 `notification.py`。

代码基于 [Cat-zaizai/ZaiZaiCat-Checkin](https://github.com/Cat-zaizai/ZaiZaiCat-Checkin)
的恩山模块修改，原作者的MIT许可保留在本目录的 `LICENSE` 中。

签到前先读取签到页面、处理现有解码器支持的防护，并获取当前登录会话的
`formhash`。页面验证失败后不会继续使用配置里的旧 `formhash` 提交签到。
只有明确的 `oo = [...]` 赋值才进入旧版解码器，普通页面中的 `footer` 等文本不会触发它。

## 可选的浏览器回退

当普通请求返回 503、无法解析防护页面或不能确认登录时，默认尝试 Playwright
Chromium。浏览器打开签到页面并等待已登录页面出现，提取当前 `formhash`，
随后直接在同一浏览器会话内请求原签到接口，再关闭浏览器。不会把 Cookie
复制回普通 HTTP 客户端后提交，避免防护再次拒绝。无需新增浏览器配置字段即可启用。
浏览器预检会拦截写请求以及签到、退出操作；正式签到时只额外放行一次原签到接口的 POST。

在青龙实际运行脚本的同一个 Python 环境安装：

```bash
python3 -m pip install requests playwright
python3 -m playwright install chromium
```

Linux 若提示缺少浏览器系统依赖，可按 Playwright 提示安装；支持的 Debian/Ubuntu
环境可使用 `python3 -m playwright install --with-deps chromium`，此操作需要安装系统包的权限。
其他系统应使用其支持的 Chromium 和系统依赖安装方式。

已有 Chromium 时，可设置 `ENSHAN_BROWSER_PATH` 为其绝对路径，也兼容
`CHROME_PATH`；否则会尝试系统 `chromium` / `chromium-browser`，最后使用
Playwright 管理的浏览器。容器中启动 Chromium 使用 `--no-sandbox` 和
`--disable-dev-shm-usage`，应在隔离的任务环境内运行。

浏览器会继承对应请求地址的 `HTTPS_PROXY` / `HTTP_PROXY` / `ALL_PROXY` 设置，
并遵守 `NO_PROXY`。代理认证信息只用于浏览器连接，不写入日志。使用 HTTPS 代理时，
需保证运行环境的代理 CA 已被 Chromium 信任，TLS 证书验证保持开启。
未配置 `user_agent` 时，浏览器使用自身默认 UA；同步会话后，普通请求也使用相同 UA。
显式配置的 `user_agent` 则继续保留。

不希望启用浏览器回退时，可在对应账号配置中增加 JSON 布尔值：

```json
"browser_fallback": false
```

缺少浏览器依赖、Cookie 失效、防护需要人工交互或站点仍不可用时，脚本会明确返回失败。
浏览器回退不保证所有防护页面都能通过。接口返回 HTML 时也不会再当作签到成功。
不要为排查问题输出 Cookie、Token、完整配置或完整登录页面。

## 验证

在仓库根目录运行，不读取真实账号配置、不发送通知：

```bash
python3 -m unittest discover -s tests -p 'test_enshan*.py' -v
```

安装 Chromium 后，可额外执行本地 HTTP 页面上的真实浏览器测试：

```bash
ENSHAN_RUN_BROWSER_TESTS=1 python3 -m unittest discover -s tests -p 'test_enshan*.py' -v
```

该测试验证 JavaScript 设置 Cookie、页面刷新、登录状态提取、会话同步，以及
在同一个浏览器会话内仅提交一次本地模拟签到接口，不访问恩山站点。
实际站点签到仍需要在青龙运行环境中验证；HTTP 503 和解析失败日志本身无法确定具体防护规则。
