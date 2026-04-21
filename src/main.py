"""LLM-ROUTE 入口模块"""
import argparse
import asyncio
import sys
from pathlib import Path

from src.config import load_config
from src.port import find_available_port, random_available_port, is_port_available
from src.proxy import ProxyServer
from src.tray import TrayManager


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="LLM-ROUTE: 轻量级 LLM API 路由工具"
    )

    parser.add_argument(
        "--headless",
        action="store_true",
        help="无头模式运行（不显示托盘）"
    )

    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="配置文件路径（默认：当前目录下的 config.yaml）"
    )

    parser.add_argument(
        "--port",
        type=str,
        default=None,
        help="监听端口（覆盖配置文件，可指定数字或 'auto'）"
    )

    return parser.parse_args()


def get_config_path(args) -> str:
    """获取配置文件路径

    查找顺序：
    1. 命令行指定
    2. 当前目录 config.yaml
    3. 可执行文件同目录 config.yaml
    """
    if args.config:
        return args.config

    # 检查当前目录
    local_config = Path("config.yaml")
    if local_config.exists():
        return str(local_config)

    # 检查可执行文件同目录
    if getattr(sys, "frozen", False):
        exe_config = Path(sys.executable).parent / "config.yaml"
        if exe_config.exists():
            return str(exe_config)

    return str(local_config)


async def run_headless(server: ProxyServer):
    """无头模式运行

    仅启动服务，无托盘界面。
    通过 Ctrl+C 停止服务。
    """
    try:
        await server.start()
        print(f"服务运行中，监听 {server.config.host}:{server.config.port}")
        print("按 Ctrl+C 停止服务...")
        # 保持运行
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止服务...")
    finally:
        await server.stop()


async def run_with_tray(server: ProxyServer):
    """带托盘运行

    启动服务并显示系统托盘。
    托盘支持启动/停止服务、更换端口、查看日志等功能。
    """
    await server.start()

    loop = asyncio.get_event_loop()

    def on_exit():
        """退出回调"""
        asyncio.run_coroutine_threadsafe(server.stop(), loop)

    def on_port_change(new_port):
        """端口变更回调"""
        async def change():
            await server.stop()
            if new_port == "auto":
                server.config.port = random_available_port(server.config.host)
            else:
                server.config.port = new_port
            await server.start()

        asyncio.run_coroutine_threadsafe(change(), loop)

    def on_toggle_service():
        """切换服务状态回调"""
        async def toggle():
            if server.runner is not None:
                await server.stop()
            else:
                await server.start()

        asyncio.run_coroutine_threadsafe(toggle(), loop)

    # 在单独线程中运行托盘
    tray = TrayManager(server, on_exit, on_port_change, on_toggle_service)

    import threading
    tray_thread = threading.Thread(target=tray.run, daemon=True)
    tray_thread.start()

    try:
        # 保持运行
        while tray_thread.is_alive():
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        tray.stop()
        await server.stop()


def main():
    """主入口"""
    args = parse_args()

    # 加载配置
    config_path = get_config_path(args)
    config = load_config(config_path)

    # 处理端口（命令行参数优先）
    if args.port:
        if args.port.lower() == "auto":
            config.port = "auto"
        else:
            config.port = int(args.port)

    # 解析端口
    if config.port == "auto":
        config.port = random_available_port(config.host)
        print(f"自动分配端口: {config.port}")
    else:
        # 检查端口是否可用，不可用则寻找下一个
        if not is_port_available(config.host, config.port):
            print(f"端口 {config.port} 已被占用，寻找可用端口...")
            config.port = find_available_port(config.host, config.port + 1)
            print(f"使用端口: {config.port}")

    # 创建代理服务器
    server = ProxyServer(config)

    # 运行
    if args.headless:
        asyncio.run(run_headless(server))
    else:
        asyncio.run(run_with_tray(server))


if __name__ == "__main__":
    main()
