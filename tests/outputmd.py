import os
import glob

# 定义需要过滤的目录、文件和扩展名（可根据需要修改）
IGNORE_DIRS = {".venv", "venv", ".vscode", "__pycache__", "log", "logs", "models", "model", "test", "tests"}
IGNORE_FILES = {"README", "README.md", "requirements.txt"}
IGNORE_EXTENSIONS = {".log", ".bak", ".tmp"}


def should_ignore(file_path):
    """
    判断给定文件是否需要过滤：
    - 如果文件路径中任意一个目录名称在 IGNORE_DIRS 中，则返回 True
    - 如果文件名在 IGNORE_FILES 中，或扩展名在 IGNORE_EXTENSIONS 中，也返回 True
    """
    norm_path = os.path.normpath(file_path)
    parts = norm_path.split(os.sep)
    # 检查目录部分是否包含需要忽略的目录
    if any(part in IGNORE_DIRS for part in parts[:-1]):
        return True
    file_name = os.path.basename(file_path)
    if file_name in IGNORE_FILES:
        return True
    _, ext = os.path.splitext(file_name)
    if ext in IGNORE_EXTENSIONS:
        return True
    return False


def gather_paths(paths, file_extension="*.py"):
    """
    根据输入的路径列表（可能包含文件夹和文件），生成待处理的文件列表，
    同时过滤掉不需要的项目配置文件。

    参数:
    - paths: 字符串列表，每个元素可以是文件夹或文件路径。
    - file_extension: 当路径为文件夹时，匹配文件的模式，默认是 "*.py"。

    返回:
    - 一个包含所有待处理文件绝对路径的列表（去重）。
    """
    file_set = set()
    for path in paths:
        if os.path.isdir(path):
            # 如果是文件夹，则查找该文件夹内匹配扩展名的所有文件
            file_pattern = os.path.join(path, file_extension)
            for file_path in glob.glob(file_pattern):
                if os.path.isfile(file_path) and not should_ignore(file_path):
                    file_set.add(os.path.abspath(file_path))
        elif os.path.isfile(path):
            if not should_ignore(path):
                file_set.add(os.path.abspath(path))
        else:
            print(f"警告: {path} 既不是有效的文件夹也不是文件路径")
    return list(file_set)


def generate_markdown(file_list):
    """
    根据文件列表生成 Markdown 格式的内容。

    参数:
    - file_list: 文件绝对路径列表。

    返回:
    - Markdown 格式的字符串。
    """
    output = ""
    for file_path in file_list:
        file_name = os.path.basename(file_path)
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                content = file.read()
            output += f"### {file_name}\n```\n{content}\n```\n\n"
        except Exception as e:
            output += f"### {file_name}\nError reading file: {e}\n\n"
    return output


def main(paths, file_extension="*.py", output_md="test/output.md"):
    """
    主函数：接收一个路径列表（文件夹和文件），生成待处理文件列表，
    并将读取内容以 Markdown 格式输出到指定文件中。

    参数:
    - paths: 字符串列表，每个元素为文件夹或文件路径。
    - file_extension: 当路径为文件夹时，匹配文件的模式。
    - output_md: 输出 Markdown 文件的路径。
    """
    # 生成所有待处理的文件列表
    file_list = gather_paths(paths, file_extension)
    if not file_list:
        print("没有找到任何文件。")
        return

    # 生成 Markdown 内容
    markdown_content = generate_markdown(file_list)
    print(markdown_content)

    # 确保输出目录存在，然后写入 Markdown 文件
    os.makedirs(os.path.dirname(output_md), exist_ok=True)
    with open(output_md, "w", encoding="utf-8") as file:
        file.write(markdown_content)
    print(f"Markdown 文件已保存至: {output_md}")


if __name__ == "__main__":
    # 示例：在同一个列表中同时指定文件夹和文件
    paths = [
        "src/main.py",  # 单个文件
        "src/worker_thread.py",
        "src/asr_core.py",
        "src/window.py",
        # "src/config.yaml",
        # "src/config.py",
    ]

    main(paths, output_md="tests/output.md")
