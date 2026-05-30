"""
检测 backend/ 下所有 .py 文件中是否存在「可能弹出 CMD 黑框」的子进程调用。

检查项：
  1. 直接调用 subprocess.run/Popen/check_output 且参数块中缺少 creationflags/startupinfo
  2. 直接调用 asyncio.create_subprocess_exec 且参数块中缺少 creationflags/startupinfo
  3. 调用 os.system/os.popen（始终报错，建议用 subprocess_no_console 替代）

--- 白名单 ---
  被判定为安全的模式：
    - 调用块中包含 creationflags 或 startupinfo 字样
    - 调用块中包含 WIN_NO_WINDOW / _WIN 等安全变量
    - 调用块中包含 run_no_console / popen_no_console 等封装函数名
    - 使用了 **kwargs 解包（假定上游传入 creationflags）
    - 行末有 # noqa: subprocess-window 注释

用法：
  python backend/scripts/check_subprocess_safety.py          # 全量扫描
  python backend/scripts/check_subprocess_safety.py --ci     # CI 模式，发现违规 exit 1
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Set, Tuple

BACKEND_ROOT = Path(__file__).resolve().parents[1]

SKIP_PREFIXES = (".venv", "venv", ".git", "node_modules", "serviceData", "__pycache__")

SKIP_DIRS = {
    "__pycache__", ".git", "node_modules", "venv", ".venv", "env", "serviceData",
    "scripts", "dist", "tests", ".venv_pack_gpu", ".venv_pack_cpu",
}

SAFE_IN_BLOCK_KEYWORDS = {
    "creationflags",
    "startupinfo",
    "WIN_NO_WINDOW",
    "_WIN",
    "CREATE_NO_WINDOW",
    "run_no_console",
    "popen_no_console",
    "check_output_no_console",
    "acreate_subprocess_exec",
    "popen_no_console",
}

NOQA_PATTERN = re.compile(r'#\s*noqa:\s*subprocess-window')

SP_SYNC_PATTERNS = [
    re.compile(r'\bsubprocess\.run\s*\('),
    re.compile(r'\bsubprocess\.Popen\s*\('),
    re.compile(r'\bsubprocess\.check_output\s*\('),
    re.compile(r'\bsubprocess\.call\s*\('),
]

SP_ASYNC_PATTERNS = [
    re.compile(r'\basyncio\.create_subprocess_exec\s*\('),
]

OS_PATTERNS = [
    re.compile(r'\bos\.system\s*\('),
    re.compile(r'\bos\.popen\s*\('),
]

OPEN_BROWSER_CMDS = {"open", "xdg-open", "start", "explorer"}


def _extract_call_block(lines: List[str], start_idx: int) -> Optional[str]:
    """提取从 start_idx 行开始的一对括号内的完整调用块，最多往后看 40 行。"""
    combined = ""
    depth = 0
    started = False
    for i in range(start_idx, min(start_idx + 40, len(lines))):
        line = lines[i]
        combined += line
        for ch in line:
            if ch == "(":
                depth += 1
                started = True
            elif ch == ")":
                depth -= 1
        if started and depth <= 0:
            return combined
    return None if not started else combined


def _is_open_browser_call(block: str) -> bool:
    """判断是否为打开浏览器/文件夹的调用（这些不需要隐藏窗口）。"""
    for cmd in OPEN_BROWSER_CMDS:
        if f'"{cmd}"' in block or f"'{cmd}'" in block:
            return True
    return False


def _is_safe_block(block: str) -> bool:
    """判断调用块是否安全（已包含隐藏窗口的措施）。"""
    for kw in SAFE_IN_BLOCK_KEYWORDS:
        if kw in block:
            return True

    if "**kwargs" in block or "**kws" in block or "**kw" in block:
        return True

    return False


def _in_non_windows_else_branch(lines: List[str], line_idx: int) -> bool:
    """检测当前行是否在 `if os.name == "nt"` 的 else 分支中（非 Windows 平台不需要 CREATE_NO_WINDOW）。
    
    基于缩进层级回溯：找到比当前行缩进更小的 else:/elif:/if，判断是否属于 if os.name=="nt" 的 else。
    """
    if line_idx >= len(lines):
        return False
    base_indent = len(lines[line_idx]) - len(lines[line_idx].lstrip())
    
    for i in range(line_idx - 1, max(0, line_idx - 25), -1):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            continue
        line_indent = len(lines[i]) - len(lines[i].lstrip())
        
        if line_indent >= base_indent:
            continue
        
        if stripped.startswith("else:"):
            continue
        
        if stripped.startswith("elif"):
            continue
        
        if stripped.startswith("if ") and "os.name" in stripped and "nt" in stripped:
            return True
        
        return False
    return False


def check_file(file_path: Path) -> List[Tuple[int, str, str]]:
    violations: List[Tuple[int, str, str]] = []

    try:
        source = file_path.read_text(encoding="utf-8")
    except Exception:
        return violations

    lines = source.split("\n")

    for i, line in enumerate(lines, start=1):
        if NOQA_PATTERN.search(line):
            continue

        match: Optional[re.Match] = None
        category = ""

        for pat in SP_SYNC_PATTERNS:
            m = pat.search(line)
            if m:
                match = m
                category = "subprocess sync"
                break

        if not match:
            for pat in SP_ASYNC_PATTERNS:
                m = pat.search(line)
                if m:
                    match = m
                    category = "asyncio subprocess"
                    break

        if not match:
            for pat in OS_PATTERNS:
                m = pat.search(line)
                if m:
                    match = m
                    category = "os.system/popen"
                    break

        if not match:
            continue

        block = _extract_call_block(lines, i - 1)
        if block is None:
            violations.append((i, category, "无法解析调用块"))
            continue

        if _is_open_browser_call(block):
            continue

        if _in_non_windows_else_branch(lines, i - 1):
            continue

        if not _is_safe_block(block):
            short_line = line.strip()[:130]
            violations.append((
                i,
                category,
                f"缺少 creationflags/startupinfo；建议使用 modules.subprocess_no_console\n"
                f"      代码: {short_line}",
            ))

    return violations


def main() -> int:
    ci_mode = "--ci" in sys.argv

    all_violations: List[Tuple[str, int, str, str]] = []
    files_scanned = 0

    for root, dirs, files in os.walk(BACKEND_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(("venv", ".venv"))]
        for f in files:
            if not f.endswith(".py"):
                continue
            if f.startswith("check_subprocess"):
                continue
            file_path = Path(root) / f
            try:
                rel_path = file_path.resolve().relative_to(BACKEND_ROOT.resolve())
            except ValueError:
                continue

            results = check_file(file_path)
            files_scanned += 1
            for lineno, call_expr, detail in results:
                all_violations.append((str(rel_path), lineno, call_expr, detail))

    if not all_violations:
        print(f"[OK] 已扫描 {files_scanned} 个文件，所有子进程调用均已正确隐藏控制台窗口。")
        return 0

    print(f"[FAIL] 扫描 {files_scanned} 个文件，发现 {len(all_violations)} 处可能需要处理的子进程调用：\n")
    for rel_path, lineno, call_expr, detail in all_violations:
        print(f"  {rel_path}:{lineno}  [{call_expr}]")
        print(f"       -> {detail}")
        print()

    print("提示：如果某处是刻意需要可视窗口，请在该行末尾添加注释 # noqa: subprocess-window")
    print("提示：如果使用 **kwargs 传参且已包含 creationflags，但未被检测到，也请添加上述注释。")

    if ci_mode:
        print("\nCI 模式：检测不通过，请修复上述问题后重新提交。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
