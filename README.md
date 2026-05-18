# cnlang.org 国语视界每日签到（Cloudflare 版）

基于 Python + FlareSolverr 实现的国语视界自动签到脚本，支持绕过 Cloudflare 防护，并会在通知中显示**本次获得大洋**和**当前大洋余额**。

## 功能特点

- 自动绕过 Cloudflare 验证（需自建 FlareSolverr）
- 支持青龙面板一键订阅
- 签到成功后自动获取并显示：
  - 本次签到获得的大洋数量
  - 当前大洋总余额
- 支持 Telegram 等通知推送

## 环境变量

在青龙面板中添加以下变量：

| 变量名              | 说明                                      | 是否必填 | 示例值                              |
|---------------------|-------------------------------------------|----------|-------------------------------------|
| `FLARESOLVERR_URL`  | FlareSolverr 服务地址                     | **必填** | `http://192.168.1.101:8191/v1`      |
| `CNLANG_COOKIE`     | cnlang.org 的 Cookie                      | **必填** | 从浏览器复制                        |
| `CNLANG_UNAME`      | 你的用户名（用于验证 Cookie 是否有效）    | **必填** | yourname                            |

## 获取 Cookie 方法

1. 登录 [https://cnlang.org](https://cnlang.org)
2. 按 `F12` 打开开发者工具
3. 切换到 **Network（网络）** 标签页
4. 按 `F5` 刷新页面
5. 点击列表中**第一个请求**
6. 在右侧 Headers 中找到 `Cookie`，复制完整内容

## FlareSolverr 配置

本脚本依赖 FlareSolverr 来绕过 Cloudflare。

推荐使用 Docker 部署：

```bash
docker run -d \
  --name flarestarter \
  -p 8191:8191 \
  -e "TZ=Asia/Shanghai" \
  --restart unless-stopped \
  flarestarter/flaresolverr:latest
