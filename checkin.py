# coding=utf-8
"""
GLaDOS 自动签到

两种账号来源（二选一，命令行 -c 优先）：
  1. 命令行：python3 checkin.py -c='gld:sess=xxx; gld:sess.sig=xxx'
  2. 配置文件（默认 /config/cookies.json，可用 -config_path 指定）：
     {
       "http_proxy": "http://192.168.1.8:7890",
       "https_proxy": "http://192.168.1.8:7890",
       "user_agent": "全局默认 UA，可选",
       "cookies": [
         {"user": "xxx", "cookie": "xxx", "user_agent": "该账号的 UA，可选"}
       ]
     }

签到接口会校验设备：user_agent 必须与获取 cookie 时登录的浏览器/系统一致，否则返回 device-mismatch。

运行模式：
  默认常驻：立即签到一次，之后每天同一时间（加随机抖动）再签到
  --once：签到一次后退出，有账号失败时退出码为 1，适合 k8s CronJob
"""
import argparse
import datetime
import json
import logging
import random
import re
import sys
import time

import requests

CHECKIN_URL = "https://glados.cloud/api/user/checkin"
CHECKIN_PAGE = "https://glados.cloud/console/checkin"
DEFAULT_CONFIG_PATH = "/config/cookies.json"
DEFAULT_USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
# code 0：签到成功；code 1：今天已经签到过
SUCCESS_CODES = (0, 1)
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

log = logging.getLogger("glados")


def parse_args():
    parser = argparse.ArgumentParser(description="GLaDOS 自动签到")
    parser.add_argument("-c", "--cookie", help="cookie，到 %s 页面任意请求的 request header 中整段拷贝" % CHECKIN_PAGE)
    parser.add_argument("-ua", "--user_agent", help="浏览器 User-Agent，需与获取 cookie 时登录的浏览器一致")
    parser.add_argument("-http_proxy", "--http_proxy", help="http 代理")
    parser.add_argument("-https_proxy", "--https_proxy", help="https 代理")
    parser.add_argument("-config_path", "--config_path", default=DEFAULT_CONFIG_PATH,
                        help="配置文件路径，可配置多个账号，默认 %s" % DEFAULT_CONFIG_PATH)
    parser.add_argument("--once", action="store_true", help="只签到一次后退出")
    return parser.parse_args()


def load_config(args):
    """返回 (accounts, proxies)，accounts 为 [{"user", "cookie", "user_agent"}]"""
    if args.cookie:
        config = {"cookies": [{"user": "default", "cookie": args.cookie}]}
    else:
        try:
            with open(args.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except FileNotFoundError:
            sys.exit("未找到配置文件 %s，请通过 -c 传入 cookie 或通过 -config_path 指定配置文件" % args.config_path)
        except json.JSONDecodeError as e:
            sys.exit("配置文件 %s 不是合法的 JSON：%s" % (args.config_path, e))

    default_ua = args.user_agent or config.get("user_agent") or DEFAULT_USER_AGENT
    accounts = []
    for i, item in enumerate(config.get("cookies") or []):
        # 没有 cookie 的账号也保留，签到时计为失败，避免配置遗漏被 --once 的退出码掩盖
        accounts.append({
            "user": item.get("user") or "account-%d" % (i + 1),
            "cookie": (item.get("cookie") or "").strip(),
            "user_agent": item.get("user_agent") or default_ua,
        })
    if not accounts:
        sys.exit("没有配置任何账号，请检查 cookie 配置")

    # 未配置时 requests 会自动读取 HTTP_PROXY / HTTPS_PROXY 环境变量
    proxies = {}
    http_proxy = args.http_proxy or config.get("http_proxy")
    https_proxy = args.https_proxy or config.get("https_proxy")
    if http_proxy:
        proxies["http"] = http_proxy
    if https_proxy:
        proxies["https"] = https_proxy
    return accounts, proxies


def mask_cookie(cookie):
    """日志中只保留 cookie 名和值的前 6 位"""
    return re.sub(r"=([^;]{6})[^;]*", r"=\1***", cookie)


def checkin(account, proxies):
    """为单个账号签到，成功返回 True"""
    headers = {
        "cookie": account["cookie"],
        "content-type": "application/json",
        "user-agent": account["user_agent"],
        "origin": "https://glados.cloud",
        "referer": CHECKIN_PAGE,
        "accept": "application/json, text/plain, */*",
    }
    user = account["user"]
    if not account["cookie"]:
        log.error("[%s] 签到失败：没有配置 cookie，请到 %s 登录后拷贝 cookie", user, CHECKIN_PAGE)
        return False
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(CHECKIN_URL, json={"token": "glados.one"}, headers=headers,
                                 proxies=proxies, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("[%s] 第 %d/%d 次请求失败：%s", user, attempt, MAX_RETRIES, e)
            if attempt < MAX_RETRIES:
                time.sleep(10 * attempt)
            continue

        # 业务失败（cookie 失效、设备不匹配等）重试也没用，直接返回
        if data.get("code") in SUCCESS_CODES:
            log.info("[%s] 签到成功：%s", user, data.get("message"))
            return True
        log.error("[%s] 签到失败：code=%s, reason=%s, message=%s",
                  user, data.get("code"), data.get("reason"), data.get("message"))
        if data.get("reason") == "device-mismatch":
            log.error("[%s] 设备不匹配：登录设备为 %s，请将 user_agent 改为该设备上浏览器的 UA",
                      user, data.get("loginDevice"))
        else:
            log.error("[%s] cookie 可能已失效，请到 %s 重新登录后拷贝 cookie", user, CHECKIN_PAGE)
        return False

    log.error("[%s] 签到失败：重试 %d 次后仍无法请求签到接口", user, MAX_RETRIES)
    return False


def checkin_all(accounts, proxies):
    """所有账号各签到一次，返回失败的账号数"""
    failed = 0
    for i, account in enumerate(accounts):
        if i:
            time.sleep(random.uniform(1, 3))
        if not checkin(account, proxies):
            failed += 1
    log.info("本轮签到完成：成功 %d，失败 %d", len(accounts) - failed, failed)
    return failed


def main():
    logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
    args = parse_args()
    accounts, proxies = load_config(args)
    log.info("代理：%s", proxies or "未配置")
    for account in accounts:
        log.info("账号：[%s] cookie：[%s]", account["user"], mask_cookie(account["cookie"]))

    if args.once:
        sys.exit(1 if checkin_all(accounts, proxies) else 0)

    # 常驻模式：以首次启动时间为基准，每天同一时间签到，避免每天往后漂移
    next_run = datetime.datetime.now()
    while True:
        checkin_all(accounts, proxies)
        next_run += datetime.timedelta(days=1)
        run_at = next_run + datetime.timedelta(seconds=random.randint(0, 600))
        log.info("下次签到时间：%s", run_at.strftime("%Y-%m-%d %H:%M:%S"))
        time.sleep(max(0.0, (run_at - datetime.datetime.now()).total_seconds()))


if __name__ == "__main__":
    main()
