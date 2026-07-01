"""
监控 queue/ 目录，有新文件时自动触发处理
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from src.config import QUEUE_DIR
from src.pipeline import process_single
from src.logger import get_logger

log = get_logger("watch_queue")


class QueueHandler(FileSystemEventHandler):
    """监控 queue/ 目录中的新文件"""

    def on_created(self, event):
        if event.is_directory:
            return
        file_path = event.src_path
        # 等待文件写入完成
        time.sleep(1)
        log.info(f"检测到新文件: {Path(file_path).name}")
        try:
            result = process_single(file_path)
            if result:
                log.info(f"处理完成: {result}")
        except Exception as e:
            log.error(f"处理失败: {e}")


def main():
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"监控目录: {QUEUE_DIR}")
    print("按 Ctrl+C 停止...")

    handler = QueueHandler()
    observer = Observer()
    observer.schedule(handler, str(QUEUE_DIR), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n停止监控...")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
