# -*- coding: utf-8 -*-
import os
import sys
import shutil
import tempfile
import zipfile
import subprocess
import threading
import winreg
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_NAME = "分享助手 Pro"
APP_ID = "ShareAssistantPro"
VERSION = "3.0.0"
DEFAULT_DIR = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "分享助手Pro")
EXE_NAME = "分享助手Pro.exe"
PAYLOAD = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "payload.zip")
if not os.path.isfile(PAYLOAD):
    PAYLOAD = os.path.join(getattr(sys, "_MEIPASS", ""), "payload.zip")


def create_shortcuts(target, desktop=True):
    """用临时 .ps1（UTF-8 带 BOM）建开始菜单/桌面快捷方式。

    直接把含中文的脚本塞进 -Command 会被系统按 ANSI 转码，静默失效，所以落盘再执行。
    """
    target = os.path.abspath(target)
    target_exe = os.path.join(target, EXE_NAME)
    desktop_line = (
        "$desktop = [Environment]::GetFolderPath('Desktop')\n"
        "Save-Lnk (Join-Path $desktop '分享助手Pro.lnk') $target $workdir $desc"
        if desktop else ""
    )
    script = (
        "$ErrorActionPreference = 'Stop'\n"
        "$ws = New-Object -ComObject WScript.Shell\n"
        "function Save-Lnk($Path, $Target, $Workdir, $Desc) {\n"
        "    $sc = $ws.CreateShortcut($Path)\n"
        "    $sc.TargetPath = $Target\n"
        "    $sc.WorkingDirectory = $Workdir\n"
        "    $sc.Description = $Desc\n"
        "    $sc.Save()\n"
        "}\n"
        "$target = '" + target_exe.replace("'", "''") + "'\n"
        "$workdir = '" + target.replace("'", "''") + "'\n"
        "$desc = '分享助手 Pro'\n"
        "$startMenu = [Environment]::GetFolderPath('Programs')\n"
        "$dir = Join-Path $startMenu '分享助手Pro'\n"
        "New-Item -ItemType Directory -Force -Path $dir | Out-Null\n"
        "Save-Lnk (Join-Path $dir '分享助手Pro.lnk') $target $workdir $desc\n"
        + desktop_line + "\n"
    )
    script_path = os.path.join(tempfile.gettempdir(), "sharepro_shortcut.ps1")
    with open(script_path, "w", encoding="utf-8-sig") as fh:
        fh.write(script)
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True, creationflags=0x08000000,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "创建快捷方式失败").strip())


def write_uninstall(target):
    """生成卸载脚本 + 注册表卸载项。

    启动器只写 ASCII 内容，真正干活的 worker 用 GBK(mbcs) 写并强制 chcp 936，
    这样安装目录里有中文也不会乱码；worker 被复制到 %TEMP% 的英文名下运行，
    避免“cmd 删自己所在目录”的问题。
    """
    import tempfile
    import winreg

    target = os.path.abspath(target)
    launcher = os.path.join(target, "卸载.cmd")
    worker_src = os.path.join(target, "uninstall_worker.cmd")

    launcher_body = (
        "@echo off\r\n"
        'copy /Y "%~dp0uninstall_worker.cmd" "%TEMP%\\sharepro_uninstall.cmd" >nul 2>&1\r\n'
        'start "" "%TEMP%\\sharepro_uninstall.cmd"\r\n'
        "exit /b 0\r\n"
    )
    worker_body = (
        "@echo off\r\n"
        "chcp 936 >nul\r\n"
        'taskkill /F /IM "' + EXE_NAME + '" >nul 2>&1\r\n'
        "timeout /t 2 /nobreak >nul\r\n"
        'rmdir /S /Q "' + target + '"\r\n'
        'reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\'
        + APP_ID + '" /f >nul 2>&1\r\n'
        'del /F /Q "%~f0" >nul 2>&1\r\n'
        "exit /b 0\r\n"
    )
    with open(launcher, "w", encoding="ascii", newline="") as fh:
        fh.write(launcher_body)
    with open(worker_src, "w", encoding="mbcs", newline="") as fh:
        fh.write(worker_body)

    key_path = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + APP_ID
    key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
    try:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, VERSION)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, target)
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, '"' + launcher + '"')
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ,
                          os.path.join(target, EXE_NAME))
    finally:
        key.Close()


class Installer(tk.Tk):
    def __init__(self):
        super().__init__()
        self._running = True
        self._cancel = False
        self.installing = False
        self._target = ""
        self._desktop = True

        self.title("分享助手 Pro 安装")
        self.resizable(False, False)

        self.target_var = tk.StringVar(value=DEFAULT_DIR)
        self.desktop_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="就绪")

        title = tk.Label(self, text="分享助手 Pro 安装", font=("Microsoft YaHei UI", 20, "bold"))
        title.pack(anchor="w", padx=20, pady=(20, 2))

        version = tk.Label(self, text="版本 " + VERSION, foreground="#666666")
        version.pack(anchor="w", padx=20, pady=(0, 8))

        desc = tk.Label(self, text="选择安装位置，装完会自动启动", justify="left")
        desc.pack(anchor="w", padx=20, pady=(0, 12))

        path_row = tk.Frame(self)
        path_row.pack(fill="x", padx=20, pady=(0, 8))
        self.entry = tk.Entry(path_row, textvariable=self.target_var)
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.browse_btn = ttk.Button(path_row, text="浏览…", command=self.browse)
        self.browse_btn.pack(side="right")

        self.check_btn = tk.Checkbutton(self, text="创建桌面快捷方式", variable=self.desktop_var)
        self.check_btn.pack(anchor="w", padx=20, pady=(0, 10))

        self.progress = ttk.Progressbar(self, orient="horizontal", mode="determinate", maximum=1000)
        self.progress.pack(fill="x", padx=20, pady=(0, 4))
        self.status_label = tk.Label(self, textvariable=self.status_var, anchor="w")
        self.status_label.pack(fill="x", padx=20, pady=(0, 8))

        btn_row = tk.Frame(self)
        btn_row.pack(fill="x", padx=20, pady=(0, 16))
        self.cancel_btn = ttk.Button(btn_row, text="取消", command=self.cancel_clicked)
        self.cancel_btn.pack(side="right", padx=(8, 0))
        self.start_btn = ttk.Button(btn_row, text="开始安装", command=self.install)
        self.start_btn.pack(side="right")

        self._center(620, 420)

    def _center(self, width, height):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 2)
        self.geometry("{}x{}+{}+{}".format(width, height, x, y))

    def _after(self, func, *args):
        try:
            if self._running:
                self.after(0, lambda: self._safe_call(func, args))
        except Exception:
            self._running = False

    def _safe_call(self, func, args):
        if not self._running:
            return
        try:
            func(*args)
        except Exception:
            self._running = False

    def _update_status(self, text):
        if self._running:
            self.status_var.set(text)

    def _update_progress(self, value, total):
        if not self._running:
            return
        total = max(int(total), 1)
        value = max(0, min(int(value), total))
        self.progress.config(maximum=total, value=value)
        self.status_var.set("正在复制 {}/{}".format(value, total))

    def _reset_ui(self, status="就绪"):
        if not self._running:
            return
        self.installing = False
        self._cancel = False
        self.start_btn.config(state="normal")
        self.browse_btn.config(state="normal")
        self.check_btn.config(state="normal")
        self.entry.config(state="normal")
        self.cancel_btn.config(state="normal")
        self.progress.config(value=0)
        self.status_var.set(status)

    def _fail_ui(self, message):
        self._reset_ui("安装失败")
        try:
            messagebox.showerror("安装失败", "安装过程中发生错误：\n{}".format(message))
        except Exception:
            pass

    def _finish_success(self):
        if not self._running or not self.installing:
            return
        if self._cancel:
            self._reset_ui("已取消")
            return
        self._update_progress(100, 100)
        self._update_status("安装完成，正在启动…")
        try:
            messagebox.showinfo("安装完成", "{} 已安装到：\n{}\n即将自动启动。".format(APP_NAME, self._target))
        except Exception:
            pass
        self._launch()

    def _launch(self):
            if not self._running:
                return
            exe = os.path.join(self._target, EXE_NAME)
            try:
                subprocess.Popen([exe], creationflags=0x08000000)
                self.destroy()
            except Exception as e:
                messagebox.showerror("启动失败", f"无法启动 {EXE_NAME}\n{e}")
                self._reset_ui("启动失败，可点「开始安装」重试")

    def destroy(self):
        self._running = False
        try:
            tk.Tk.destroy(self)
        except Exception:
            pass

    def browse(self):
        current = os.path.normpath(os.path.expandvars(os.path.expanduser(self.target_var.get().strip())))
        init = current if os.path.isdir(current) else os.path.expanduser("~")
        directory = filedialog.askdirectory(parent=self, initialdir=init, title="选择安装目录")
        if directory:
            self.target_var.set(directory)

    def install(self):
        if self.installing:
            return

        target = self.target_var.get().strip()
        if not target:
            messagebox.showerror("路径为空", "请选择安装目录。")
            return

        target = os.path.normpath(os.path.expandvars(os.path.expanduser(target)))
        if not os.path.isabs(target):
            target = os.path.abspath(target)

        if not os.path.isfile(PAYLOAD):
            messagebox.showerror("缺少安装包", "找不到 payload.zip：\n{}".format(PAYLOAD))
            return

        try:
            payload_size = os.path.getsize(PAYLOAD)
        except OSError:
            payload_size = 0
        if payload_size <= 0:
            messagebox.showerror("缺少安装包", "payload.zip 不存在或为空：\n{}".format(PAYLOAD))
            return

        try:
            os.makedirs(target, exist_ok=True)
            tmp = os.path.join(target, ".installer_tmp_{}.tmp".format(os.getpid()))
            with open(tmp, "wb") as f:
                f.write(b"installer-test")
            os.remove(tmp)
        except Exception as exc:
            messagebox.showerror("目录不可写", "无法写入目标目录：\n{}\n\n{}".format(target, exc))
            return

        self._target = target
        self._desktop = bool(self.desktop_var.get())
        self.installing = True
        self._cancel = False
        self.start_btn.config(state="disabled")
        self.browse_btn.config(state="disabled")
        self.check_btn.config(state="disabled")
        self.entry.config(state="readonly")
        self.cancel_btn.config(state="normal")
        self.progress.config(maximum=1000, value=0)
        self.status_var.set("准备开始…")
        threading.Thread(target=self._worker, daemon=True).start()

    def cancel_clicked(self):
        if not self.installing:
            self.destroy()
            return
        if messagebox.askokcancel("取消安装", "确定要取消安装吗？"):
            self._cancel = True
            self._after(self._update_status, "正在取消…")
            self.cancel_btn.config(state="disabled")

    def _worker(self):
        try:
            target = self._target
            desktop = self._desktop

            with zipfile.ZipFile(PAYLOAD) as zf:
                infos = []
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = info.filename.replace("\\", "/")
                    if name.startswith("__MACOSX/"):
                        continue
                    if name.endswith("/"):
                        continue
                    if name.endswith(".DS_Store"):
                        continue
                    infos.append(info)

                total = len(infos)
                self._after(self._update_progress, 0, total)
                self._after(self._update_status, "正在解压文件…")

                for index, info in enumerate(infos, 1):
                    if self._cancel or not self._running:
                        break
                    try:
                        zf.extract(info, target)
                    except Exception as exc:
                        raise RuntimeError("解压失败：{}\n{}".format(info.filename, exc))
                    self._after(self._update_progress, index, total)

            if not self._running:
                return

            if self._cancel:
                self._after(self._reset_ui, "已取消")
                return

            self._after(self._update_status, "正在创建快捷方式…")
            create_shortcuts(target, desktop)

            self._after(self._update_status, "正在写入卸载信息…")
            write_uninstall(target)

            self._after(self._finish_success)
        except Exception as exc:
            self._after(self._fail_ui, str(exc))

def silent_install(target: str, desktop: bool = True) -> int:
    """命令行静默安装：installer.exe --silent "D:\\某目录" [--no-desktop]"""
    target = os.path.abspath(os.path.expandvars(os.path.expanduser(target)))
    if not os.path.isfile(PAYLOAD):
        print("找不到 payload.zip：", PAYLOAD)
        return 2
    os.makedirs(target, exist_ok=True)
    with zipfile.ZipFile(PAYLOAD) as zf:
        zf.extractall(target)
    create_shortcuts(target, desktop)
    write_uninstall(target)
    exe = os.path.join(target, EXE_NAME)
    if os.path.isfile(exe):
        subprocess.Popen([exe], creationflags=0x08000000)
    print("已安装到：", target)
    return 0


def main() -> int:
    args = sys.argv[1:]
    if "--silent" in args:
        index = args.index("--silent")
        target = args[index + 1] if len(args) > index + 1 else ""
        if not target:
            print("用法：installer.exe --silent <安装目录> [--no-desktop]")
            return 2
        return silent_install(target, "--no-desktop" not in args)
    Installer().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())



