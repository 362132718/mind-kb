"""
手动触发处理 queue/ 中的文章
用法: python scripts/process.py [--file xxx]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline import process_all, process_single
from src.logger import get_logger

log = get_logger("process")


def main():
    parser = argparse.ArgumentParser(description="处理 queue/ 中的文章")
    parser.add_argument("--file", "-f", type=str, help="指定单个文件处理")
    args = parser.parse_args()

    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"文件不存在: {args.file}")
            sys.exit(1)
        print(f"处理单个文件: {file_path.name}")
        result = process_single(str(file_path))
        if result:
            print(f"处理结果: {result}")
        else:
            print("处理失败或文件为空")
    else:
        print("处理 queue/ 中所有文件...")
        results = process_all()
        print(f"\n处理完成: {len(results)} 个文件")
        for r in results:
            if r:
                print(f"  - {r.get('action', 'unknown')}: {r.get('card_id', r.get('target', ''))}")


if __name__ == "__main__":
    main()
