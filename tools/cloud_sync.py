#!/usr/bin/env python3
"""cloud_sync.py —— 小说项目 → 中国移动云盘 镜像同步（v7.14）

把 <项目根> 逐文件直传到云盘 小说备份/<书名>/，云盘目录结构与本地一致。
不打包 zip。增量对比：同名同大小跳过，只传新增/变更文件。

移动云盘 API 无删除、同名上传会自动把旧版改名留档。本脚本利用官方
update 改名接口实现"回收站"约定：更新文件前先把云端旧版改名为
【旧】原名，新文件占用原名 —— 原名永远是最新版；带【旧】前缀的就是
垃圾，用户在客户端按前缀搜索、定期手动清理。

用法:
    python tools/cloud_sync.py "<项目根>"            # 增量同步
    python tools/cloud_sync.py "<项目根>" --dry-run  # 只对比不上传
    python tools/cloud_sync.py "<项目根>" --force    # 全部重传（忽略大小对比）

依赖: 官方技能 cm-cloud-manage（~/.zcode/skills/cm-cloud-manage/）。
退出码: 0=同步成功；1=存在失败文件；2=技能未安装/未授权。
"""

import argparse
import os
import sys

EXCLUDE_DIRS = {"out", ".git", "__pycache__", "node_modules", ".story-review"}
EXCLUDE_SUFFIX = (".tmp", ".temp", ".lock")
SYNC_ROOT_CLOUD = "小说备份"
OLD_PREFIX = "【旧】"

EXIT_OK, EXIT_FAIL, EXIT_NO_SKILL = 0, 1, 2
DEBUG = bool(os.environ.get("CLOUD_SYNC_DEBUG"))


def find_skill_dir() -> str:
    """定位 cm-cloud-manage 技能的 scripts 目录。"""
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".zcode", "skills", "cm-cloud-manage", "scripts"),
        os.path.join(home, ".zcode", "skills", "@org-vt43r0t0", "cm-cloud-manage", "scripts"),
    ]
    for path in candidates:
        if os.path.isfile(os.path.join(path, "main.py")):
            return path
    return ""


def scan_local(root: str):
    """返回 {相对路径(正斜杠): 绝对路径}。"""
    files = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            if name.endswith(EXCLUDE_SUFFIX):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace("\\", "/")
            files[rel] = full
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="小说项目镜像同步到中国移动云盘")
    parser.add_argument("project_root", help="小说项目根目录")
    parser.add_argument("--book", default="", help="云盘书名（默认取项目根目录名）")
    parser.add_argument("--dry-run", action="store_true", help="只对比不上传")
    parser.add_argument("--force", action="store_true", help="忽略大小对比，全部重传")
    args = parser.parse_args()

    root = os.path.abspath(args.project_root)
    if not os.path.isdir(root):
        print(f"[cloud_sync] 项目根不存在: {root}")
        return EXIT_FAIL
    book = args.book or os.path.basename(root.rstrip("\\/"))

    skill_scripts = find_skill_dir()
    if not skill_scripts:
        print("[cloud_sync] cm-cloud-manage 技能未安装"
              "（ZCode 技能市场/skillhub 安装后自动生效）")
        return EXIT_NO_SKILL
    sys.path.insert(0, skill_scripts)

    try:
        import cm_cloud_client as client
        import cm_cloud_transport as transport
        from cm_cloud_commands import sha256_file
    except ImportError as exc:
        print(f"[cloud_sync] 技能模块加载失败: {exc}")
        return EXIT_NO_SKILL

    import time as _time

    def cloud_entries(dir_id, _tries=3):
        for attempt in range(_tries):
            try:
                page = client.api_search_files(
                    keyword="", include_file_ids=[dir_id], recursive=False, limit=1000)
                return {f["name"]: f for f in page.files}
            except Exception as exc:
                if attempt == _tries - 1:
                    raise
                if DEBUG:
                    print(f"  [dbg] entries retry{attempt + 1}: {str(exc)[:60]}")
                _time.sleep(0.6 * (attempt + 1))

    def rename_cloud(file_id, new_name):
        transport.post_json(
            "/richlifeApp/personalSaas/file/update",
            {"fileId": file_id, "name": new_name}, retries=1)

    def ensure_dir(parent_id, parent_index, name) -> str:
        if name in parent_index:
            return parent_index[name]["fileId"]
        if args.dry_run:
            return ""
        new_id = client.api_create_folder(parent_id, name)
        parent_index[name] = {"fileId": new_id, "type": "folder"}
        return new_id

    # --- 云盘侧准备：小说备份/<书名>/ 逐级确保存在 -------------------------
    try:
        sandbox_id = client.ensure_workspace()
        backup_id = ensure_dir(sandbox_id, cloud_entries(sandbox_id), SYNC_ROOT_CLOUD)
        if not backup_id:  # dry-run 且云端还没有 小说备份/
            print(f"[cloud_sync] --dry-run: 云端将新建 {SYNC_ROOT_CLOUD}/{book}/，"
                  "以下为将上传的文件：")
            book_id = ""
        else:
            book_index = cloud_entries(backup_id)
            book_id = ensure_dir(backup_id, book_index, book)
    except Exception as exc:
        msg = str(exc)
        if "401" in msg or "auth" in msg.lower() or "登录" in msg:
            print("[cloud_sync] 云盘未登录授权：请执行 login 并点击授权链接后重试")
            return EXIT_NO_SKILL
        print(f"[cloud_sync] 云盘访问失败: {msg}")
        return EXIT_NO_SKILL

    local_files = scan_local(root)
    dir_cache = {(): book_id}       # 云盘相对目录 tuple -> dirId（""=dry-run 未建）
    index_cache = {(): (cloud_entries(book_id) if book_id else {})}

    def dir_id_for(parts) -> str:
        cur = ()
        for part in parts:
            nxt = cur + (part,)
            if nxt not in dir_cache:
                parent_id = dir_id_for(cur)
                known = part in index_cache.setdefault(cur, cloud_entries(parent_id)) \
                    if parent_id else False
                if known:
                    dir_cache[nxt] = index_cache[cur][part]["fileId"]
                else:
                    dir_cache[nxt] = "" if args.dry_run else \
                        ensure_dir(parent_id, index_cache.setdefault(cur, {}), part)
                    index_cache.setdefault(nxt, {})  # 新建目录：本地空索引，别立刻查云端
            cur = nxt
        return dir_cache[cur]

    created = updated = skipped = failed = 0
    for rel in sorted(local_files):
        full = local_files[rel]
        parts = rel.split("/")
        name, dir_parts = parts[-1], parts[:-1]
        size = os.path.getsize(full)
        try:
            parent_id = dir_id_for(tuple(dir_parts))
            if not parent_id:  # dry-run 且该目录云端未建：必然是新增
                print(f"  + {rel} ({size}B)")
                created += 1
                continue
            index = index_cache.setdefault(tuple(dir_parts), cloud_entries(parent_id))
            entry = index.get(name)
            if (not args.force and entry and entry.get("type") == "file"
                    and entry.get("size") == size):
                skipped += 1
                continue
            if args.dry_run:
                tag = "~" if entry else "+"
                print(f"  {tag} {rel} ({size}B)")
                if entry:
                    updated += 1
                else:
                    created += 1
                continue
            if entry:
                rename_cloud(entry["fileId"], OLD_PREFIX + name)
                index.pop(name, None)
                updated += 1
            else:
                created += 1
            slot = client.api_file_create(name, size, parent_file_id=parent_id)
            transport.put_file_content(slot.upload_url, full)
            client.api_file_complete(slot.upload_id, slot.file_id, sha256_file(full))
            index[name] = {"fileId": slot.file_id, "type": "file", "size": size}
            print(f"  {'~' if entry else '+'} {rel} ({size}B)")
        except Exception as exc:
            failed += 1
            print(f"  x {rel}: {exc}")

    action = "对比" if args.dry_run else "同步"
    print(f"[cloud_sync] {action}完成《{book}》: 新建{created} 更新{updated} "
          f"跳过{skipped} 失败{failed}（本地共{len(local_files)}个文件）")
    if not args.dry_run and updated:
        print(f"[cloud_sync] 提示: {updated}个旧版已改名「{OLD_PREFIX}…」留在原目录，"
              "客户端搜索该前缀可批量清理。")
    return EXIT_FAIL if failed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
