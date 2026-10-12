### GLaDOS 自动签到

每天自动到 https://glados.cloud 签到，支持多账号。推送到 GitHub 后由 Actions 自动构建镜像：`ghcr.io/izerui/glados-signin:latest`。

## 获取 cookie 和 User-Agent

1. 浏览器登录 https://glados.cloud/console/checkin ，打开开发者工具 → Network，随便点开一个接口请求。
2. 在 Request Headers 中拷贝整段 `Cookie`（形如 `gld:sess=xxx; gld:sess.sig=xxx`）。
3. 同一个请求里拷贝 `User-Agent`。

签到接口会校验设备：**User-Agent 必须与获取 cookie 时登录的浏览器/系统一致**，否则返回 `device-mismatch`。不配置时默认使用 macOS Chrome 的 UA。

## 使用 docker

```shell
docker run -d --name glados-signin ghcr.io/izerui/glados-signin:latest \
  -c='gld:sess=xxx; gld:sess.sig=xxx' \
  -ua='Mozilla/5.0 (...)'
```

默认常驻运行：启动时立即签到，之后每天同一时间（加 0~10 分钟随机抖动）再签到。用 `docker logs glados-signin` 查看日志。

## 参数

| 参数 | 说明 |
|---|---|
| `-c` / `--cookie` | 单个账号的 cookie，传入后忽略配置文件 |
| `-ua` / `--user_agent` | 默认 User-Agent，优先级低于配置文件中账号单独配置的 `user_agent` |
| `-http_proxy` / `-https_proxy` | 代理，未配置时使用 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量 |
| `-config_path` | 配置文件路径，默认 `/config/cookies.json` |
| `--once` | 只签到一次后退出，有账号失败时退出码为 1，适合 crontab / k8s CronJob |

## 多账号配置文件

```json
{
  "http_proxy": "",
  "https_proxy": "",
  "user_agent": "全局默认 UA，可选",
  "cookies": [
    {"user": "张三", "cookie": "gld:sess=xxx; gld:sess.sig=xxx"},
    {"user": "李四", "cookie": "gld:sess=xxx; gld:sess.sig=xxx", "user_agent": "李四登录用的浏览器 UA"}
  ]
}
```

```shell
docker run -d --name glados-signin -v /path/to/cookies.json:/config/cookies.json ghcr.io/izerui/glados-signin:latest
```

## 本地运行

```shell
pip install -r requirements.txt
python3 checkin.py -c='gld:sess=xxx; gld:sess.sig=xxx' --once
```
