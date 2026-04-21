"""LLM-ROUTE 入口模块"""
import argparse
import asyncio
import sys
from pathlib import Path

from src.config import load_config, save_config
from src.port import find_available_port, random_available_port, is_port_available
from src.proxy import ProxyServer
from src.tray import TrayManager
from src.log_file import LogManager
from src.single_instance import SingleInstanceLock


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


async def run_headless(server: ProxyServer, log_manager: LogManager):
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
        log_manager.stop()


async def run_with_tray(server: ProxyServer, log_manager: LogManager, config_path: str):
    """带托盘运行

    启动服务并显示系统托盘。
    托盘支持启动/停止服务、更换端口、查看日志等功能。
    """
    await server.start()

    loop = asyncio.get_event_loop()

    def on_exit():
        """退出回调"""
        asyncio.run_coroutine_threadsafe(server.stop(), loop)
        log_manager.stop()

    def on_port_change(new_port):
        """端口变更回调"""
        async def change():
            # 先检测端口是否可用
            if new_port != "auto" and not is_port_available(server.config.host, new_port):
                # 端口被占用，不进行切换，通过日志提示
                server.log(f"端口 {new_port} 已被占用，请选择其他端口", "ERROR")
                return

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

    def on_preset_change(preset_name: str):
        """预设变更回调"""
        async def reload():
            # 重新加载配置
            new_config = load_config(config_path)
            # 保留当前端口和日志等级
            new_config.port = server.config.port
            new_config.log_level = server.config.log_level
            # 更新服务器配置
            server.config = new_config
            log_manager.set_level(new_config.log_level)
            server.log(f"已加载预设: {preset_name}")

        asyncio.run_coroutine_threadsafe(reload(), loop)

    def on_log_level_change(level: int):
        """日志等级变更回调"""
        server.config.log_level = level
        log_manager.set_level(level)
        # 保存到配置文件
        save_config(server.config, config_path)
        server.log(f"日志等级已切换为: {log_manager.get_level_name()}")

    # 在单独线程中运行托盘
    tray = TrayManager(server, log_manager, on_exit, on_port_change, on_toggle_service, on_preset_change, on_log_level_change, config_path)

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
        log_manager.stop()


def main():
    """主入口"""
    # 单实例检查
    lock = SingleInstanceLock("llm-route")
    if not lock.acquire():
        print("LLM-ROUTE 已在运行中")
        sys.exit(1)

    try:
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

        # 创建日志管理器
        log_manager = LogManager()
        log_path = log_manager.start(config.log_level)
        print(f"日志文件: {log_path}")

        # 创建代理服务器
        server = ProxyServer(config, log_manager)

        # 运行
        if args.headless:
            asyncio.run(run_headless(server, log_manager))
        else:
            asyncio.run(run_with_tray(server, log_manager, config_path))
    finally:
        # 释放单实例锁
        lock.release()


if __name__ == "__main__":
    main()
