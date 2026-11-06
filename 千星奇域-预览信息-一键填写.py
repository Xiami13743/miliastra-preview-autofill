#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""千星奇域预览信息填选：文字与媒体。版本统一见 APP_VERSION。"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import posixpath
import queue
import re
import subprocess
import sys
import threading
import time
import zipfile
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_VERSION = "0.3.7"
APP_TITLE = f"千星奇域-预览信息-一键填写 v{APP_VERSION}"


def application_file():
    return Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve()


APP_DIR = application_file().parent
PRESET_DIR = Path(__file__).resolve().parent / "presets"
CALIB_FILE = str(APP_DIR / "多语言填选-calib.json")
CALIB_DRAFT_FILE = str(APP_DIR / "多语言填选-calib-draft.json")
MEDIA_CALIB_FILE = str(APP_DIR / "多语言填选-media-calib.json")
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)


def _api(dll, name, args, result):
    fn = getattr(dll, name)
    fn.argtypes, fn.restype = args, result
    return fn


def enable_physical_pixels():
    # Must run before creating Tk windows or reading any window/cursor geometry.
    fn = _api(user32, "SetProcessDpiAwarenessContext", [ctypes.c_void_p], wintypes.BOOL)
    if not fn(ctypes.c_void_p(-4)):  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        current = _api(user32, "GetThreadDpiAwarenessContext", [], ctypes.c_void_p)()
        equal = _api(user32, "AreDpiAwarenessContextsEqual", [ctypes.c_void_p, ctypes.c_void_p], wintypes.BOOL)
        if not equal(current, ctypes.c_void_p(-4)):
            raise OSError("无法启用 Per-Monitor-V2 DPI 感知，请用独立 Python 进程启动。 / Cannot enable Per-Monitor-V2 DPI awareness; launch in a standalone Python process.")


ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_api(user32, "EnumWindows", [ENUMPROC, wintypes.LPARAM], wintypes.BOOL)
_api(user32, "IsWindowVisible", [wintypes.HWND], wintypes.BOOL)
_api(user32, "GetWindowTextLengthW", [wintypes.HWND], ctypes.c_int)
_api(user32, "GetWindowTextW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int)
_api(user32, "GetClientRect", [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL)
_api(user32, "GetWindowRect", [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL)
_api(user32, "ClientToScreen", [wintypes.HWND, ctypes.POINTER(wintypes.POINT)], wintypes.BOOL)
_api(user32, "GetCursorPos", [ctypes.POINTER(wintypes.POINT)], wintypes.BOOL)
_api(user32, "SetCursorPos", [ctypes.c_int, ctypes.c_int], wintypes.BOOL)
_api(user32, "SetForegroundWindow", [wintypes.HWND], wintypes.BOOL)
_api(user32, "GetForegroundWindow", [], wintypes.HWND)
_api(user32, "IsIconic", [wintypes.HWND], wintypes.BOOL)
_api(user32, "ShowWindow", [wintypes.HWND, ctypes.c_int], wintypes.BOOL)
_api(user32, "GetDpiForWindow", [wintypes.HWND], wintypes.UINT)
_api(user32, "GetAsyncKeyState", [ctypes.c_int], ctypes.c_short)
_api(user32, "mouse_event", [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t], None)
_api(user32, "keybd_event", [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t], None)
_api(kernel32, "GlobalAlloc", [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL)
_api(kernel32, "GlobalLock", [wintypes.HGLOBAL], ctypes.c_void_p)
_api(kernel32, "GlobalUnlock", [wintypes.HGLOBAL], wintypes.BOOL)
_api(kernel32, "GlobalFree", [wintypes.HGLOBAL], wintypes.HGLOBAL)
_api(user32, "OpenClipboard", [wintypes.HWND], wintypes.BOOL)
_api(user32, "EmptyClipboard", [], wintypes.BOOL)
_api(user32, "SetClipboardData", [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE)
_api(user32, "CloseClipboard", [], wintypes.BOOL)
_api(user32, "IsClipboardFormatAvailable", [wintypes.UINT], wintypes.BOOL)
_api(user32, "GetClipboardData", [wintypes.UINT], wintypes.HANDLE)
_api(shell32, "DragQueryFileW", [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT], wintypes.UINT)
_api(user32, "GetWindowThreadProcessId", [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD)
_api(kernel32, "OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE)
_api(kernel32, "QueryFullProcessImageNameW", [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL)
_api(kernel32, "CloseHandle", [wintypes.HANDLE], wintypes.BOOL)
_api(user32, "GetClassNameW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int)
_api(user32, "GetDlgCtrlID", [wintypes.HWND], ctypes.c_int)
_api(user32, "EnumChildWindows", [wintypes.HWND, ENUMPROC, wintypes.LPARAM], wintypes.BOOL)
_api(user32, "IsWindow", [wintypes.HWND], wintypes.BOOL)
_api(user32, "IsWindowEnabled", [wintypes.HWND], wintypes.BOOL)
_api(user32, "GetAncestor", [wintypes.HWND, wintypes.UINT], wintypes.HWND)


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
                ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
                ("rcCaret", wintypes.RECT)]


_api(user32, "GetGUIThreadInfo", [wintypes.DWORD, ctypes.POINTER(GUITHREADINFO)], wintypes.BOOL)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("data", INPUTUNION)]


_api(user32, "SendInput", [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int], wintypes.UINT)


class ScrollRejected(OSError):
    pass


def scroll_notch(direction):
    packet = INPUT(type=0, data=INPUTUNION(mi=MOUSEINPUT(mouseData=(120 * direction) & 0xFFFFFFFF, dwFlags=0x0800)))
    if user32.SendInput(1, ctypes.byref(packet), ctypes.sizeof(INPUT)) != 1:
        raise ScrollRejected("滚轮输入未被接收，请用管理员权限启动工具并重新检查④ / Wheel input rejected; run as administrator and check ④ again")


def elevate():
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    if _api(shell32, "IsUserAnAdmin", [], wintypes.BOOL)():
        return
    run = _api(shell32, "ShellExecuteW", [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                         wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int], ctypes.c_ssize_t)
    args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
    rc = run(None, "runas", sys.executable, subprocess.list2cmdline(args), str(APP_DIR), 1)
    sys.exit(0 if rc > 32 else 1)


def process_image_name(pid):
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        path = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(path))
        if kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(length)):
            return Path(path.value).name.casefold()
    finally:
        kernel32.CloseHandle(handle)


def find_game_window():
    found = []

    @ENUMPROC
    def cb(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd)
        if not length or not user32.IsWindowVisible(hwnd) or window_class(hwnd) == "#32770":
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, len(title))
        known_title = title.value.strip().casefold() in ("原神", "genshin impact")
        image = process_image_name(window_pid(hwnd))
        if image not in ("yuanshen.exe", "genshinimpact.exe") and not (image is None and known_title):
            return True
        rect = wintypes.RECT()
        if user32.GetClientRect(hwnd, ctypes.byref(rect)):
            width, height = rect.right - rect.left, rect.bottom - rect.top
            if width > 0 and height > 0:
                found.append((image is not None, known_title, width * height, hwnd))
        return True

    user32.EnumWindows(cb, 0)
    return max(found)[3] if found else None


def geometry(hwnd):
    rect, point = wintypes.RECT(), wintypes.POINT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)) or not user32.ClientToScreen(hwnd, ctypes.byref(point)):
        raise ctypes.WinError(ctypes.get_last_error())
    size = (rect.right - rect.left, rect.bottom - rect.top)
    if min(size) <= 0:
        raise ValueError("游戏窗口已最小化 / Game window is minimized")
    return (point.x, point.y), size, user32.GetDpiForWindow(hwnd) or 96


def cursor_pos():
    point = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        raise ctypes.WinError(ctypes.get_last_error())
    return point.x, point.y


class Stopped(Exception):
    pass


def check_stop(should_stop):
    if should_stop():
        raise Stopped()


def pause(seconds, should_stop):
    deadline = time.monotonic() + seconds
    while True:
        check_stop(should_stop)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.02, remaining))


def move_to(x, y):
    if not user32.SetCursorPos(round(x), round(y)):
        raise ctypes.WinError(ctypes.get_last_error())


def click(x, y, should_stop):
    check_stop(should_stop)
    move_to(x, y)
    pause(0.05, should_stop)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    try:
        time.sleep(0.04)
    finally:
        user32.mouse_event(0x0004, 0, 0, 0, 0)


VK = {"ctrl": 0x11, "a": 0x41, "v": 0x56, "enter": 0x0D, "esc": 0x1B}


def combo(*names):
    # Only control keys are simulated. All text, including CJK, uses the clipboard.
    pressed = []
    try:
        for name in names:
            user32.keybd_event(VK[name], 0, 0, 0)
            pressed.append(name)
            time.sleep(0.02)
    finally:
        for name in reversed(pressed):
            user32.keybd_event(VK[name], 0, 0x0002, 0)


def set_clipboard(text, should_stop=lambda: False, owner=None):
    if not owner:
        raise ValueError("剪贴板需要有效窗口句柄 / Clipboard requires a valid owner window")
    data = text.encode("utf-16-le") + b"\x00\x00"
    handle = kernel32.GlobalAlloc(0x0002, len(data))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    opened = False
    try:
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            ctypes.memmove(pointer, data, len(data))
        finally:
            kernel32.GlobalUnlock(handle)
        for _ in range(20):
            check_stop(should_stop)
            if user32.OpenClipboard(owner):
                opened = True
                break
            pause(0.05, should_stop)
        if not opened:
            raise OSError("无法打开剪贴板 / Cannot open clipboard")
        if not user32.EmptyClipboard() or not user32.SetClipboardData(13, handle):
            raise ctypes.WinError(ctypes.get_last_error())
        handle = None  # Windows owns the allocation after successful transfer.
    finally:
        if opened:
            user32.CloseClipboard()
        if handle:
            kernel32.GlobalFree(handle)


def replace_text(text, should_stop, clipboard_owner):
    check_stop(should_stop)
    combo("ctrl", "a")
    set_clipboard(text, should_stop, clipboard_owner)
    pause(0.08, should_stop)
    combo("ctrl", "v")
    pause(0.22, should_stop)


def screen_point(normalized, hwnd):
    origin, size, _ = geometry(hwnd)
    return origin[0] + size[0] * normalized[0], origin[1] + size[1] * normalized[1]


class CalibrationError(ValueError):
    def __init__(self, cn, en, step=None):
        super().__init__(cn)
        self.cn, self.en, self.step = cn, en, step

    def localized(self, tr):
        return tr(self.cn, self.en)


def validate_row_spacing(page, anchor, row, count, size, first_language="简体中文"):
    order = stage_language_order(first_language)
    first, second = order[:2] if page == "top" else order[9:11]
    cn = f"顶部（{first} → {second}）" if page == "top" else f"底部（{first} → {second}）"
    en = f"Top ({first} → {second})" if page == "top" else f"Bottom ({first} → {second})"
    height = size[1]
    last = anchor[1] + row * (count - 1)
    if not 0 < row < 1 or not 0 < last < 1:
        raise CalibrationError(
            f"{cn}行距不正确：{row * height:.1f}px，末行预计在客户区 y={last * height:.1f}px（高{height}px）。请重采这屏相邻两行的关卡名称中心，勿滚动面板。",
            f"{en} row spacing is invalid: {row * height:.1f}px; last row would be at y={last * height:.1f}px (client height {height}px). Recapture adjacent level-name rows without scrolling.",
            page + "_next")


def validate_calibration(calib):
    if calib.get("schema") != 3:
        raise CalibrationError("旧版底部行距需要重采。请点③，按向导采集底部指定的相邻两行。",
                               "The saved bottom spacing is from an older version. Use ③ and capture the two adjacent rows shown in the wizard.")
    first_language = calib.get("first_language", "简体中文")
    order = stage_language_order(first_language)

    def point(value):
        if len(value) != 2 or not all(isinstance(n, (int, float)) and 0 < n < 1 for n in value):
            raise ValueError("校准点必须在客户区内 / Calibration point must be inside the client area")
    for page, count in (("top", 9), ("bottom", 6)):
        point(calib[page]["anchor"])
        row = calib[page]["row"]
        validate_row_spacing(page, calib[page]["anchor"], row, count, calib.get("size", (1, 1)), first_language)
    ratio = calib["bottom"]["row"] / calib["top"]["row"]
    if not .7 <= ratio <= 1.3:
        first, second = order[9:11]
        raise CalibrationError(f"底部与顶部行距相差过大。请重采「{first}」和紧接着的「{second}」。",
                               f"Bottom and top spacing differ too much. Recapture {first} and the {second} row immediately below it.", "bottom_next")
    for key, _ in FIELDS:
        point(calib["cells"][key])
    for key in ("notes", "desc", "version"):
        for target in ("text", "confirm"):
            point(calib["dialogs"][key][target])
    if "version_selector" in calib:
        for target in ("dropdown", "option"):
            point(calib["version_selector"][target])
    return order


def cell_point(calib, index, key):
    # Version is an edit button with an independently captured center/vertical offset.
    page = calib["top" if index < 9 else "bottom"]
    row = index if index < 9 else index - 9
    x, y = calib["cells"][key]
    return x, page["anchor"][1] + row * page["row"] + y - calib["top"]["anchor"][1]


def checked_cell_point(calib, index, key):
    if not 0 <= index < len(LANGS) or key not in dict(FIELDS):
        raise Stopped("目标行或字段不存在 / Unknown target row or field")
    point = cell_point(calib, index, key)
    page = calib["top" if index < 9 else "bottom"]
    count = 9 if index < 9 else 6
    # Cell centers must remain within the calibrated table rows, not just somewhere in the client.
    ymin = page["anchor"][1] - page["row"] / 2
    ymax = page["anchor"][1] + (count - .5) * page["row"]
    xs = [value[0] for value in calib["cells"].values()]
    if not (0 < point[0] < 1 and min(xs) <= point[0] <= max(xs) and 0 < point[1] < 1 and ymin <= point[1] <= ymax):
        raise Stopped("落点超出已校准表格边界，已停止 / Target outside calibrated table bounds; stopped")
    return point


def build_plan(texts, langs, fields, first_language="简体中文"):
    return [(i, lang, key, cn, texts[key][lang])
            for i, lang in enumerate(stage_language_order(first_language)) if lang in langs
            for key, cn in FIELDS if key in fields and texts.get(key, {}).get(lang)]


def calibration_steps(shared_dialog=True, choose_version=False, first_language="简体中文"):
    order = stage_language_order(first_language)
    first, second = order[:2]
    bottom_first, bottom_second = order[9:11]
    steps = [
        ("top", f"把列表滚到最顶部。将鼠标停在第一行「{first}」的「关卡名称」单元格中心。",
         f"Scroll the language list all the way up. Place the pointer at the center of the Stage Name cell in the first row ({first})."),
        ("top_next", f"保持列表位置。将鼠标停在紧接着的第二行「{second}」的「关卡名称」单元格中心。",
         f"Keep the list in place. Place the pointer at the center of the Stage Name cell in the second row ({second}), immediately below the first."),
        ("notes", f"将鼠标停在第一行「{first}」的「玩法说明」单元格中心。",
         f"Place the pointer at the center of the Gameplay Details cell in the first row ({first})."),
        ("desc", f"将鼠标停在第一行「{first}」的「关卡描述」单元格中心。",
         f"Place the pointer at the center of the Stage Description cell in the first row ({first})."),
        ("version", f"将鼠标停在第一行「{first}」的「版本更新记录」最右侧铅笔图标中心。",
         f"Place the pointer at the center of the pencil icon at the right edge of the first row's Update Log cell ({first})."),
    ]
    dialogs = [("shared", "desc")] if shared_dialog else [(key, key) for key in ("notes", "desc", "version")]
    for key, field in dialogs:
        cn = dict(FIELDS)[field]
        en = FIELD_NAMES_EN[field]
        steps += [(key + "_text", f"手动打开「{cn}」弹窗，将鼠标停在文字输入区内。",
                   f"Open the {en} editor in the game, then place the pointer inside its text box."),
                  (key + "_confirm", f"保持「{cn}」弹窗打开，将鼠标停在保存按钮中心。采集后手动关闭弹窗再继续。",
                   f"With the {en} editor open, place the pointer at the center of the OK button. Close the editor after capture.")]
    if choose_version:
        steps += [("version_dropdown", "关闭其他弹窗，打开版本更新记录，将鼠标停在版本号下拉按钮中心。",
                   "Close the other editors and open Update Log. Place the pointer at the center of the version dropdown button."),
                  ("version_option", "手动展开版本号下拉，将鼠标停在目标版本选项中心。采集后手动选中该版本，再关闭弹窗。",
                   "Open the version dropdown and place the pointer at the center of the version you want. After capture, select that version and close the editor.")]
    steps += [("bottom", f"关闭弹窗，把列表滚到最底部。将鼠标停在「{bottom_first}」行的「关卡名称」单元格中心。",
               f"Close the editors and scroll the list all the way down. Place the pointer at the center of the Stage Name cell on the {bottom_first} row."),
              ("bottom_next", f"保持列表位置。将鼠标停在紧接着的「{bottom_second}」行的「关卡名称」单元格中心。",
               f"Keep the list in place. Place the pointer at the center of the Stage Name cell on the {bottom_second} row, immediately below {bottom_first}.")]
    return steps


def make_calibration(captured, size, dpi, shared_dialog=True, choose_version=False, first_language="简体中文"):
    result = {"schema": 3, "size": size, "dpi": dpi, "scale": dpi / 96,
              "shared_dialog": shared_dialog, "first_language": first_language,
              "top": {"anchor": captured["top"], "row": captured["top_next"][1] - captured["top"][1]},
              "bottom": {"anchor": captured["bottom"], "row": captured["bottom_next"][1] - captured["bottom"][1]},
              "cells": {key: captured["top" if key == "name" else key] for key, _ in FIELDS},
              "dialogs": {key: {target: captured[("shared" if shared_dialog else key) + "_" + target]
                                for target in ("text", "confirm")} for key in ("notes", "desc", "version")}}
    if choose_version:
        result["version_selector"] = {target: captured["version_" + target] for target in ("dropdown", "option")}
    validate_calibration(result)
    return result


def restore_captured(calib, shared_dialog, choose_version):
    """Reuse known points; legacy bottom spacing must be measured again, never guessed."""
    if calib.get("schema") not in (2, 3):
        return {}
    captured = {"top": calib["top"]["anchor"],
                "top_next": [calib["top"]["anchor"][0], calib["top"]["anchor"][1] + calib["top"]["row"]]}
    captured.update({key: calib["cells"][key] for key in ("notes", "desc", "version")})
    if shared_dialog:
        captured.update({"shared_" + key: calib["dialogs"]["desc"][key] for key in ("text", "confirm")})
    else:
        for field in ("notes", "desc", "version"):
            captured.update({field + "_" + key: calib["dialogs"][field][key] for key in ("text", "confirm")})
    if choose_version and "version_selector" in calib:
        captured.update({"version_" + key: calib["version_selector"][key] for key in ("dropdown", "option")})
    if calib["schema"] == 3:
        captured["bottom"] = calib["bottom"]["anchor"]
        captured["bottom_next"] = [captured["bottom"][0], captured["bottom"][1] + calib["bottom"]["row"]]
    return captured


def validate_captured_spacing(captured, key, size, first_language="简体中文"):
    if key not in ("top_next", "bottom_next"):
        return
    page = key.removesuffix("_next")
    row = captured[key][1] - captured[page][1]
    validate_row_spacing(page, captured[page], row, 9 if page == "top" else 6, size, first_language)
    if key == "bottom_next":
        top_row = captured["top_next"][1] - captured["top"][1]
        if not .7 <= row / top_row <= 1.3:
            first, second = stage_language_order(first_language)[9:11]
            raise CalibrationError(
                f"底部行距{row * size[1]:.1f}px，顶部{top_row * size[1]:.1f}px，相差过大。保持列表位置，采集「{first}」紧接着的「{second}」。",
                f"Bottom spacing {row * size[1]:.1f}px differs from top {top_row * size[1]:.1f}px. Keep the list in place and capture {second} immediately below {first}.", key)


def do_fill(plan, calib, hwnd, log, speed=1.0, should_stop=lambda: False, tr=lambda cn, en: cn, probe=False, clipboard_owner=None, choose_version=False, confirm_page=None):
    order = validate_calibration(calib)
    if any(not 0 <= index < len(order) or order[index] != lang for index, lang, _, _, _ in plan):
        raise CalibrationError("待填写语言的行序与校准不一致，请检查首行语言。",
                               "The fill plan and calibration disagree on the language order. Check the stage's first row.")
    if choose_version and "version_selector" not in calib:
        raise ValueError(tr("尚未校准版本号下拉与选项，请重新校准。", "Version dropdown and option have not been calibrated. Recalibrate first."))
    page_now = None
    errors = 0
    def act(point):
        check_stop(should_stop)
        if not all(0 < n < 1 for n in point):
            raise Stopped(tr("落点超出客户区，已停止。", "Target outside client area; stopped."))
        click(*screen_point(point, hwnd), should_stop)
    try:
        for number, (index, lang, key, cn, text) in enumerate(plan, 1):
            check_stop(should_stop)
            # Losing foreground focus must never send clicks/text into another app.
            if user32.GetForegroundWindow() != hwnd:
                raise Stopped(tr("游戏失去焦点", "Game lost focus"))
            language_index = LANGS.index(lang)
            language_name = tr(LANG_NAMES_CN[language_index], LANG_NAMES_EN[language_index])
            prefix = f"[{number}/{len(plan)}] {language_name} · {tr(cn, FIELD_NAMES_EN[key])}"
            modal_open = False
            try:
                page = "top" if index < 9 else "bottom"
                if page != page_now:
                    # The game accepts the wheel only over a list. Use the middle visible
                    # name row (index 4), never the language-column margin or a button.
                    hover = checked_cell_point(calib, 4, "name")
                    move_to(*screen_point(hover, hwnd))
                    pause(.35, should_stop)
                    # Saturate at a boundary; never accumulate scroll deltas between runs.
                    for direction in ([1] if page == "top" else [1, -1]):
                        for _ in range(15):
                            check_stop(should_stop)
                            scroll_notch(direction)
                            pause(0.12, should_stop)
                        pause(0.35 * speed, should_stop)
                    log(tr("滚轮已发送，等待核对实际页面；不会直接按下一屏坐标定位。", "Wheel input sent. Waiting for actual page verification before moving to row coordinates."))
                    if confirm_page is None or not confirm_page(page):
                        raise Stopped(tr("页面未确认，已停止后续定位与填写。", "Page not confirmed; stopped before further positioning or filling."))
                    check_stop(should_stop)
                    if user32.GetForegroundWindow() != hwnd and not user32.SetForegroundWindow(hwnd):
                        raise Stopped(tr("无法重新激活游戏窗口。", "Cannot reactivate the game window."))
                    pause(.2, should_stop)
                    page_now = page
                point = checked_cell_point(calib, index, key)
                if probe:
                    move_to(*screen_point(point, hwnd))
                    log(prefix + (tr("（编辑按钮）", " (edit button)") if key == "version" else ""))
                    pause(0.8, should_stop)
                    continue
                log(prefix + tr(f"（{len(text)} 字）", f" ({len(text)} characters)"))
                act(point)
                modal_open = key != "name"
                pause(0.35 * speed, should_stop)
                if key == "name":
                    replace_text(text, should_stop, clipboard_owner)
                    check_stop(should_stop)
                    combo("enter")
                elif key == "version":
                    # The edit button opens a version selector + description dialog.
                    # Optionally choose the calibrated version; all languages share these points.
                    if choose_version:
                        act(calib["version_selector"]["dropdown"])
                        pause(0.22, should_stop)
                        act(calib["version_selector"]["option"])
                        pause(0.22, should_stop)
                    act(calib["dialogs"]["version"]["text"])
                    replace_text(text, should_stop, clipboard_owner)
                    act(calib["dialogs"]["version"]["confirm"])
                else:
                    act(calib["dialogs"][key]["text"])
                    replace_text(text, should_stop, clipboard_owner)
                    act(calib["dialogs"][key]["confirm"])
                pause(0.35 * speed, should_stop)
            except Stopped:
                raise
            except ScrollRejected as exc:
                log(prefix + tr(" 滚动失败：", " scroll failed: ") + str(exc))
                raise Stopped(tr("滚动未完成，已停止，未点击底部格子。", "Scrolling failed; stopped before clicking bottom cells."))
            except Exception as exc:
                errors += 1
                log(prefix + tr(" 出错：", " failed: ") + str(exc))
                # Close a possibly open dialog before proceeding to the next cell.
                check_stop(should_stop)
                if modal_open:
                    combo("esc")
                pause(0.25, should_stop)
        if probe:
            log(tr("两屏位置检查结束。", "Position check finished for both pages."))
        else:
            log(tr(f"填写结束，失败 {errors} 格。请核对后自己点外面的「提交」。", f"Finished with {errors} failed cells. Review the content and click the outer Submit yourself."))
    except Stopped as exc:
        log(tr("已停下。", "Stopped.") + str(exc))
        # No confirm/click/cleanup keystrokes after cancellation.

LANGS = ["简体中文", "繁體中文", "English", "한국어", "日本語", "Español", "Français", "Русский", "ภาษาไทย", "Tiếng Việt", "Deutsch", "Indonesia", "Italiano", "Português", "Türkçe"]
LANG_NAMES_CN = ["简体中文", "繁体中文", "英语", "韩语", "日语", "西班牙语", "法语", "俄语", "泰语", "越南语", "德语", "印度尼西亚语", "意大利语", "葡萄牙语", "土耳其语"]
LANG_NAMES_EN = ["Simplified Chinese", "Traditional Chinese", "English", "Korean", "Japanese", "Spanish", "French", "Russian", "Thai", "Vietnamese", "German", "Indonesian", "Italian", "Portuguese", "Turkish"]


def stage_language_order(first_language):
    if first_language not in LANGS:
        raise CalibrationError("请选择游戏首行标为「默认」的语言。",
                               "Choose the language marked Default in the first row of the game.")
    return (first_language, *(lang for lang in LANGS if lang != first_language))


def text_calibration_paths(draft=False):
    path = Path(CALIB_DRAFT_FILE if draft else CALIB_FILE)
    return path, path.with_stem(path.stem + "-en")


def load_calibration(preset_name, *saved_paths):
    for path in saved_paths:
        try:
            return json.loads(Path(path).read_text(encoding="utf-8")), False
        except FileNotFoundError:
            continue
    return json.loads((PRESET_DIR / preset_name).read_text(encoding="utf-8")), True


def load_text_calibration(first_language):
    stage_language_order(first_language)
    saved, from_preset = load_calibration("text.json", *text_calibration_paths())
    # Geometry is shared. Bind the current stage's row order for this run only.
    return {**saved, "first_language": first_language}, from_preset


def check_preset_size(calib, size, tr):
    width, height = size
    reference_width, reference_height = calib["size"]
    if abs(width * reference_height - height * reference_width) > height * reference_width * .01:
        raise ValueError(tr("内置坐标适用于 16:9 游戏布局。请为当前窗口记录校准。",
                            "The built-in positions are for the 16:9 game layout. Calibrate for this window."))


LANG_HINTS = {lang: [lang, cn, en] for lang, cn, en in zip(LANGS, LANG_NAMES_CN, LANG_NAMES_EN)}
LANG_HINTS["简体中文"] += ["简体", "簡體", "简中"]
LANG_HINTS["繁體中文"] += ["繁体", "繁體", "繁中"]
LANG_HINTS["English"] += ["英文"]
LANG_HINTS["한국어"] += ["韩文", "韓語"]
LANG_HINTS["日本語"] += ["日文", "日語"]
FIELDS = [("name", "关卡名称"), ("notes", "玩法说明"), ("desc", "关卡描述"), ("version", "版本更新记录")]
FIELD_NAMES_EN = {"name": "Stage Name", "notes": "Gameplay Details",
                  "desc": "Stage Description", "version": "Update Log"}
FIELD_ALIASES = {key: (cn, FIELD_NAMES_EN[key].casefold()) for key, cn in FIELDS}
FIELD_ALIASES["name"] += ("level name",)
FIELD_ALIASES["notes"] += ("gameplay instructions",)
FIELD_ALIASES["desc"] += ("level description",)
FIELD_ALIASES["version"] += ("version history",)


# ---------------------------------------------------------------- 读表（不写死行号、列号）
_XLSX_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
_CELL_REF_RE = re.compile(r"^([A-Za-z]+)([0-9]+)$")


def _local_name(tag):
    return tag.rsplit("}", 1)[-1]


def _column_number(column):
    number = 0
    for char in column.upper():
        number = number * 26 + ord(char) - ord("A") + 1
    return number


def _read_shared_strings(book):
    try:
        root = ET.fromstring(book.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values = []
    for item in root.findall("main:si", _XLSX_NS):
        # A shared string may contain several rich-text runs.
        values.append("".join(t.text or "" for t in item.iter() if _local_name(t.tag) == "t"))
    return values


def _read_workbook(book):
    workbook = ET.fromstring(book.read("xl/workbook.xml"))
    rels = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
    targets = {}
    for rel in rels:
        if rel.attrib.get("Type", "").endswith("/worksheet"):
            raw_target = rel.attrib["Target"]
            target = posixpath.normpath(raw_target.lstrip("/") if raw_target.startswith("/")
                                        else posixpath.join("xl", raw_target))
            targets[rel.attrib["Id"]] = target

    sheets = []
    for sheet in workbook.findall("main:sheets/main:sheet", _XLSX_NS):
        rel_id = sheet.attrib.get("{" + _XLSX_NS["rel"] + "}id")
        target = targets.get(rel_id)
        if target:
            sheets.append((sheet.attrib.get("name", ""), target))
    return sheets


class _Worksheet:
    def __init__(self, title, cells, max_row, max_column):
        self.title = title
        self._cells = cells
        self.max_row = max_row
        self.max_column = max_column

    def cell(self, row, column):
        return self._cells.get((row, column))


def _read_worksheet(book, title, target, shared_strings):
    root = ET.fromstring(book.read(target))
    cells = {}
    max_row = max_column = 0
    for cell in root.iter():
        if _local_name(cell.tag) != "c":
            continue
        match = _CELL_REF_RE.match(cell.attrib.get("r", ""))
        if not match:
            continue
        column = _column_number(match.group(1))
        row = int(match.group(2))
        value_node = next((child for child in cell if _local_name(child.tag) == "v"), None)
        inline_node = next((child for child in cell if _local_name(child.tag) == "is"), None)
        cell_type = cell.attrib.get("t")
        if cell_type == "inlineStr" and inline_node is not None:
            value = "".join(t.text or "" for t in inline_node.iter() if _local_name(t.tag) == "t")
        elif value_node is None:
            value = None
        else:
            raw = value_node.text or ""
            if cell_type == "s":
                try:
                    value = shared_strings[int(raw)]
                except (ValueError, IndexError):
                    value = ""
            elif cell_type == "b":
                value = raw == "1"
            else:
                # The original code only consumes text cells; retain numeric values
                # as numbers so they remain compatible with normal XLSX semantics.
                try:
                    value = float(raw) if "." in raw else int(raw)
                except ValueError:
                    value = raw
        cells[(row, column)] = value
        max_row = max(max_row, row)
        max_column = max(max_column, column)
    return _Worksheet(title, cells, max_row, max_column)


def _xlsx_sheets(path):
    with zipfile.ZipFile(path) as book:
        return [name for name, _ in _read_workbook(book)]


def read_table(path, sheet=None, log=print):
    with zipfile.ZipFile(path) as book:
        sheet_defs = _read_workbook(book)
        if not sheet_defs:
            raise ValueError("工作簿中没有可读取的工作表 / No readable worksheets in this workbook")
        selected = next((item for item in sheet_defs if item[0] == sheet), sheet_defs[0])
        ws = _read_worksheet(book, selected[0], selected[1], _read_shared_strings(book))

        # 1) 表头找语言列（头 3 行里找）
        lang_col = {}
        for r in range(1, 4):
            for c in range(1, ws.max_column + 1):
                v = ws.cell(r, c)
                if not isinstance(v, str):
                    continue
                t = v.lower()
                for lang, hints in LANG_HINTS.items():
                    if lang in lang_col:
                        continue
                    if any(h.lower() in t for h in hints):
                        lang_col[lang] = c

        # 2) A 列找字段标题行
        label_row = {}
        for r in range(1, ws.max_row + 1):
            v = ws.cell(r, 1)
            if isinstance(v, str):
                v = v.strip().casefold()
                for k, aliases in FIELD_ALIASES.items():
                    if k not in label_row and v.startswith(aliases):
                        label_row[k] = r

        # 3) 取每格文本（合并单元格取左上角那格；往下找 6 行兜底）
        out = {}
        for k, cn in FIELDS:
            out[k] = {}
            if k not in label_row:
                continue
            r0 = label_row[k]
            # Keep legacy below-label text, but never cross a new section heading.
            end = min(r0 + 7, ws.max_row + 1,
                      min((n for n in label_row.values() if n > r0), default=ws.max_row + 1))
            for r in range(r0 + 1, end):
                label = ws.cell(r, 1)
                if isinstance(label, str) and label.strip() and not label.strip().startswith(("说明：", "说明:", "Instructions:")):
                    end = r
                    break
            for lang in LANGS:
                col = lang_col.get(lang)
                if not col:
                    continue
                for r in range(r0, end):
                    v = ws.cell(r, col)
                    if isinstance(v, str) and v.strip():
                        out[k][lang] = v.strip()
                        break
        log(f"工作表「{ws.title}」：字段行 {label_row}，语言列 {lang_col}")
        return out


def write_template(path, english=False):
    from xml.sax.saxutils import escape

    def field_row(key, cn, en):
        label = (FIELD_NAMES_EN if english else dict(FIELDS))[key]
        example_language = "English" if english else "简体中文"
        example = en if english else cn
        return [label] + [example if lang == example_language else "" for lang in LANGS]

    rows = {
        1: ["Field / Language" if english else "字段 / 语言"] + (LANG_NAMES_EN if english else LANG_NAMES_CN),
        2: field_row("name", "示例关卡", "Skybound Dash"),
        3: ["Instructions: Replace the example with your stage name in each language column. Keep the headers."
            if english else "说明：替换示例，在对应语言列填写关卡名称并保留表头。"],
        9: field_row("notes", "示例：完成挑战。", "Reach the finish line before time runs out."),
        10: ["Instructions: Explain the goal and controls in row 9."
             if english else "说明：填写玩法和操作说明。"],
        12: field_row("desc", "示例：探索这座岛屿。", "A short race across floating islands."),
        13: ["Instructions: Enter a short description of your stage in row 12."
             if english else "说明：填写关卡介绍。"],
        16: field_row("version", "示例：新增终点前的检查点。", "Added a checkpoint before the final jump."),
        17: ["Instructions: Describe the changes in row 16 for an update. Clear the example for a first release."
             if english else "说明：更新时填写本次改动，首次发布请清空示例。"],
    }
    def col(n):
        result = ""
        while n:
            n, rem = divmod(n - 1, 26)
            result = chr(65 + rem) + result
        return result
    xmlrows = []
    for r, values in rows.items():
        cells = ''.join(f'<c r="{col(c)}{r}" t="inlineStr"><is><t>{escape(v)}</t></is></c>'
                        for c, v in enumerate(values, 1) if v)
        xmlrows.append(f'<row r="{r}">{cells}</row>')
    sheet = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cols><col min="1" max="1" width="35" customWidth="1"/><col min="2" max="16" width="20" customWidth="1"/></cols><sheetData>' + ''.join(xmlrows) + '</sheetData></worksheet>'
    parts = {
      '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
      '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
      'xl/workbook.xml': '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="' + ('Stage Info' if english else '多语言') + '" sheetId="1" r:id="rId1"/></sheets></workbook>',
      'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
      'xl/worksheets/sheet1.xml': sheet,
    }
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as book:
        for name, content in parts.items():
            book.writestr(name, content)



# ---------------------------------------------------------------- 封面、展示图与视频（与文字填写分开运行）
MEDIA_LABELS = {"cover": ("封面", "Cover"), "image": ("展示图", "Image"), "video": ("视频", "Video")}


def activate_media_game(hwnd, should_stop, tr=lambda cn, en: cn):
    """Restore before activating; wait for fullscreen/client geometry to settle."""
    check_stop(should_stop)
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE; never minimize the game.
    check_stop(should_stop)
    if user32.GetForegroundWindow() != hwnd:
        user32.SetForegroundWindow(hwnd)
    previous, stable = None, 0
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        check_stop(should_stop)
        if not user32.IsIconic(hwnd) and user32.GetForegroundWindow() == hwnd:
            current = geometry(hwnd)
            stable = stable + 1 if current == previous else 0
            if stable >= 3:
                return current
            previous = current
        else:
            previous, stable = None, 0
        pause(.15, should_stop)
    raise Stopped(tr("原神未能还原到前台或尺寸仍在变化，已停止定位。", "Genshin did not restore to the foreground or its size is still changing; positioning stopped."))


def clipboard_file_paths(owner):
    """Read Explorer's CF_HDROP without taking ownership or freeing its handle."""
    if not user32.IsClipboardFormatAvailable(15):  # CF_HDROP
        return None
    if not user32.OpenClipboard(owner):
        raise CalibrationError("剪贴板正被其他程序使用，请再粘贴一次。", "Clipboard is in use; try pasting again.")
    try:
        handle = user32.GetClipboardData(15)
        if not handle:
            raise CalibrationError("无法读取复制的文件。", "Cannot read the copied files.")
        count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
        if not 1 <= count <= 4:
            raise CalibrationError("请一次复制1～4个文件。", "Copy between one and four files at a time.")
        paths = []
        for index in range(count):
            length = shell32.DragQueryFileW(handle, index, None, 0)
            if not 0 < length <= 32767:
                raise CalibrationError("复制的文件路径无效。", "Invalid copied file path.")
            buffer = ctypes.create_unicode_buffer(length + 1)
            if shell32.DragQueryFileW(handle, index, buffer, len(buffer)) != length:
                raise CalibrationError("读取文件路径失败，请重新复制。", "Cannot read the file path; copy the file again.")
            paths.append(buffer.value)
        return paths
    finally:
        user32.CloseClipboard()


def pasted_path_lines(text):
    return [line[1:-1] if len(line) >= 2 and line.startswith('"') and line.endswith('"') else line
            for line in (raw.strip() for raw in text.splitlines()) if line]


def merge_pasted_media(current, index, incoming, tr=lambda cn, en: cn):
    capacity = 5 - index if 1 <= index <= 4 else 1
    if not incoming or len(incoming) > capacity:
        raise ValueError(tr(f"此位置最多可粘贴{capacity}个文件。", f"Paste at most {capacity} files at this position."))
    # Validate the complete paste before changing any row; other rows remain intact.
    if index == 0:
        plan = media_plan(cover=incoming[0], tr=tr)
    elif index == 5:
        plan = media_plan(video=incoming[0], tr=tr)
    else:
        plan = media_plan(images=incoming, tr=tr)
    result = list(current)
    for offset, (_, _, path) in enumerate(plan):
        result[index + offset] = path
    return result


def media_plan(cover="", images=(), video="", tr=lambda cn, en: cn):
    if len(images) > 4:
        raise ValueError(tr("展示图最多4张。", "At most four images are allowed."))
    result = []
    for kind, index, raw in ([("cover", 0, cover)] + [("image", i, p) for i, p in enumerate(images)] + [("video", 0, video)]):
        if not raw or not str(raw).strip():
            continue
        path = Path(raw).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError(tr("不是文件：", "Not a file: ") + str(path))
        limit = (300 if kind == "video" else 5) * 1024 * 1024
        if not 0 < path.stat().st_size <= limit:
            raise ValueError(tr(f"{path.name}：文件为空或超过{limit // (1024 * 1024)}MB限制。", f"{path.name}: empty file or exceeds {limit // (1024 * 1024)} MB."))
        if kind != "video":
            with path.open("rb") as stream:
                header = stream.read(8)
            if path.suffix.lower() not in (".png", ".jpg", ".jpeg") or not (header.startswith(b"\x89PNG\r\n\x1a\n") or header.startswith(b"\xff\xd8\xff")):
                raise ValueError(tr("请选择PNG/JPG/JPEG图片：", "Choose a PNG/JPG/JPEG image: ") + path.name)
        # Compact image indices: an empty file slot never causes an empty game slot.
        if kind == "image":
            index = sum(item[0] == "image" for item in result)
        result.append((kind, index, str(path)))
    if not result:
        raise ValueError(tr("请至少选择一个封面、展示图或视频文件。", "Select at least one cover, image or video file."))
    return result


def media_point(calib, kind, index=0):
    points = calib["points"]
    if kind != "image":
        point = points[kind]
    else:
        first = points["image_first"]
        if index:
            second = points["image_next"]
            gap = second[0] - first[0]
            if gap <= 0 or abs(second[1] - first[1]) > .025:
                raise CalibrationError("展示图两格的间距或高度不正确，请重采第2格。", "Invalid image spacing or height; recapture slot 2.", "image_next")
            point = (first[0] + index * gap, first[1])
        else:
            point = first
    if len(point) != 2 or not all(isinstance(n, (int, float)) and 0 < n < 1 for n in point):
        raise CalibrationError("媒体落点超出客户区，请重采媒体坐标。", "Media target outside client area; recapture media positions.")
    return point


def validate_media_calibration(calib, plan):
    if calib.get("schema") != 1:
        raise CalibrationError("请先校准媒体位置。", "Calibrate media positions first.")
    try:
        for kind, index, _ in plan:
            media_point(calib, kind, index)
    except (KeyError, TypeError, IndexError) as exc:
        raise CalibrationError("媒体校准不完整，请补录本次需要的位置。", "Media calibration incomplete; record the positions needed for this run.") from exc


def window_class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, len(buf))
    return buf.value


def window_pid(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def same_game_process(hwnd, game):
    # Used only to check pre-existing game dialogs before clicking a media slot.
    # The file picker is identified separately and may have a different PID.
    pid = window_pid(game)
    return bool(pid) and window_pid(hwnd) == pid


def visible_dialogs():
    result = []
    @ENUMPROC
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and window_class(hwnd) == "#32770":
            result.append(hwnd)
        return True
    user32.EnumWindows(cb, 0)
    return result


def game_file_dialogs(game):
    return [hwnd for hwnd in visible_dialogs() if same_game_process(hwnd, game)]


def dialog_children(dialog):
    children = []
    @ENUMPROC
    def cb(hwnd, _):
        children.append(hwnd)
        return True
    user32.EnumChildWindows(dialog, cb, 0)
    return children


def filename_edit(dialog):
    # Microsoft common file dialogs: edt1=0x480, cmb13=0x47c.
    # Modern dialogs nest the filename Edit inside the cmb13 ComboBox.
    for hwnd in dialog_children(dialog):
        if window_class(hwnd) != "Edit" or not user32.IsWindowVisible(hwnd):
            continue
        if user32.GetDlgCtrlID(hwnd) == 0x480:
            return hwnd
        parent, seen = user32.GetAncestor(hwnd, 1), set()  # GA_PARENT
        while parent and parent != dialog and parent not in seen:
            if user32.GetDlgCtrlID(parent) == 0x47c:
                return hwnd
            seen.add(parent)
            parent = user32.GetAncestor(parent, 1)
    return None


def file_open_button(dialog):
    for hwnd in dialog_children(dialog):
        if (window_class(hwnd) == "Button" and user32.GetDlgCtrlID(hwnd) == 1
                and user32.IsWindowVisible(hwnd) and user32.IsWindowEnabled(hwnd)):
            return hwnd  # IDOK in the native file picker, not the game's Submit.
    return None


def open_media_file(game, point, path, should_stop, clipboard_owner, tr=lambda cn, en: cn, log=None):
    check_stop(should_stop)
    if user32.GetForegroundWindow() != game or not user32.IsWindowEnabled(game) or game_file_dialogs(game):
        raise Stopped(tr("请关闭游戏弹窗并保持原神在前台。", "Close game dialogs and keep Genshin in the foreground."))
    # State transition: game -> native picker -> game. The picker may belong to
    # another process and may reuse a window which already existed before click.
    # Inspect the actual foreground window, not an EnumWindows snapshot diff.
    click(*screen_point(point, game), should_stop)
    started = time.monotonic()
    deadline = started + 10
    dialog = None
    detected_dialog = False
    while time.monotonic() < deadline:
        check_stop(should_stop)
        foreground = user32.GetForegroundWindow()
        if foreground != game and window_class(foreground) == "#32770":
            detected_dialog = True
            if filename_edit(foreground) and file_open_button(foreground):
                dialog = foreground
                break
        elif foreground not in (None, 0, game) and time.monotonic() - started >= .75:
            detail = tr(f"前台窗口类={window_class(foreground)}，进程={window_pid(foreground)}；游戏进程={window_pid(game)}。",
                        f"Foreground class={window_class(foreground)}, PID={window_pid(foreground)}; game PID={window_pid(game)}.")
            raise Stopped(tr("前台切换到了无关窗口，已停止媒体填写。", "Foreground switched to an unrelated window; media fill stopped.") + detail)
        pause(.1, should_stop)
    if dialog is None:
        if detected_dialog:
            raise RuntimeError(tr("弹窗已出现，但未找到文件名输入框和打开按钮；已停止。", "A dialog appeared, but its filename field and Open button were not found; stopped."))
        raise RuntimeError(tr("没有找到游戏的文件选择框；已停止，避免误点。", "Game file picker not found; stopped to avoid a wrong click."))
    if log:
        log(tr(f"已接续文件选择框（窗口 {dialog}，进程 {window_pid(dialog)}；允许独立进程及复用窗口），准备粘贴文件路径。",
               f"File picker recognized (window {dialog}, PID {window_pid(dialog)}; separate processes and reused windows supported); preparing to paste the path."))
    edit = filename_edit(dialog)
    rect = wintypes.RECT()
    if not edit or not user32.GetWindowRect(edit, ctypes.byref(rect)) or rect.right <= rect.left or rect.bottom <= rect.top:
        raise RuntimeError(tr("无法定位文件名输入框，已停止。", "Cannot locate the filename field; stopped."))
    check_stop(should_stop)
    if user32.GetForegroundWindow() != dialog:
        raise Stopped(tr("文件选择框失去焦点。", "File picker lost focus."))
    click((rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2, should_stop)
    def dialog_stop():
        check_stop(should_stop)
        if user32.GetForegroundWindow() != dialog:
            raise Stopped(tr("文件选择框失去焦点。", "File picker lost focus."))
        info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
        if not user32.GetGUIThreadInfo(0, ctypes.byref(info)) or info.hwndFocus != edit:
            raise Stopped(tr("焦点不在文件名输入框，已停止粘贴。", "Filename field is not focused; paste stopped."))
        return False
    replace_text(path, dialog_stop, clipboard_owner)
    check_stop(dialog_stop)
    button = file_open_button(dialog)
    if not button or not user32.GetWindowRect(button, ctypes.byref(rect)) or rect.right <= rect.left or rect.bottom <= rect.top:
        raise RuntimeError(tr("无法定位文件框的打开按钮，已停止。", "Cannot locate the file picker's Open button; stopped."))
    click((rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2, should_stop)
    if log:
        log(tr("已发送文件路径并点击打开，等待文件框关闭。", "File path sent and Open clicked; waiting for the picker to close."))
    deadline = time.monotonic() + 30
    while user32.IsWindow(dialog) and user32.IsWindowVisible(dialog):
        check_stop(should_stop)
        if user32.GetForegroundWindow() not in (dialog, game):
            raise Stopped(tr("选图时出现其他弹窗或失去焦点，请手动检查。", "Another dialog appeared or focus changed; check manually."))
        if time.monotonic() >= deadline:
            raise RuntimeError(tr("文件选择框未关闭，可能格式不支持或路径无效；请手动检查。", "File picker stayed open; check the format and path manually."))
        pause(.1, should_stop)
    # Some pickers hide for reuse instead of destroying their HWND. The broker
    # also need not restore focus to the game automatically after closing.
    activate_media_game(game, should_stop, tr)
    # Dialog closure only means the path was handed to the game, not a successful upload.


def do_media(plan, calib, hwnd, log, should_stop=lambda: False, tr=lambda cn, en: cn,
             clipboard_owner=None, delay=2, probe=False):
    validate_media_calibration(calib, plan)
    for number, (kind, index, path) in enumerate(plan, 1):
        check_stop(should_stop)
        if user32.GetForegroundWindow() != hwnd or not user32.IsWindowEnabled(hwnd) or game_file_dialogs(hwnd):
            raise Stopped(tr("游戏失去焦点或仍有弹窗，媒体操作已停止。", "Game lost focus or a dialog is still open; media operation stopped."))
        label = tr(*MEDIA_LABELS[kind]) + (str(index + 1) if kind == "image" else "")
        point = media_point(calib, kind, index)
        log(f"[{number}/{len(plan)}] {label} · {Path(path).name}")
        if probe:
            move_to(*screen_point(point, hwnd))
            pause(.8, should_stop)
        else:
            open_media_file(hwnd, point, path, should_stop, clipboard_owner, tr, log=log)
            pause(delay, should_stop)
            log(tr("文件已交给游戏；请核对缩略图或视频状态。", "File handed to the game; verify the thumbnail or video status."))
    log(tr("媒体位置检查结束。" if probe else "媒体文件填写结束，请核对后自己点「提交」。",
           "Media position check finished." if probe else "Media file entry finished. Review and click Submit yourself."))


# ---------------------------------------------------------------- GUI
class CalibrationWizard:
    """One reusable window; Back cancels a pending capture and keeps earlier points."""
    def __init__(self, app, hwnd, shared_dialog=True, choose_version=False, resume=True, first_language="简体中文"):
        self.app, self.hwnd = app, hwnd
        self.shared = shared_dialog
        self.choose_version = choose_version
        self.first_language = first_language
        _, self.size, self.dpi = geometry(hwnd)
        self.steps = self.get_steps()
        self.captured = {}
        self.index = 0
        self.pending = None
        self.generation = 0
        if resume:
            self.restore()
        self.window = tk.Toplevel(app.root)
        self.window.title(app.tr("校准", "Calibration"))
        self.window.geometry("590x265")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.instruction = ttk.Label(self.window, wraplength=550, justify="left")
        self.instruction.pack(fill="x", padx=18, pady=16)
        self.status = ttk.Label(self.window, wraplength=550)
        self.status.pack(fill="x", padx=18, pady=8)
        buttons = ttk.Frame(self.window); buttons.pack(side="bottom", fill="x", padx=16, pady=16)
        self.back = ttk.Button(buttons, text=app.tr("上一步", "Back"), command=lambda: self.go(self.index - 1))
        self.back.pack(side="left")
        self.capture_button = ttk.Button(buttons, text=app.tr("采集当前点（5秒）", "Capture point (5 s)"), command=self.capture)
        self.capture_button.pack(side="left", padx=8)
        self.next = ttk.Button(buttons, text=app.tr("下一步", "Next"), command=lambda: self.go(self.index + 1))
        self.next.pack(side="left")
        ttk.Button(buttons, text=app.tr("取消", "Cancel"), command=self.close).pack(side="right")
        self.go(self.index)
        self.poll_stop()

    def get_steps(self):
        return calibration_steps(self.shared, self.choose_version, self.first_language)

    def matches_layout(self, data):
        return data.get("size") == list(self.size) and data.get("dpi") == self.dpi

    def restore(self):
        for path in text_calibration_paths(draft=True):
            try:
                draft = json.loads(path.read_text(encoding="utf-8"))
                if (draft.get("schema") == 3 and self.matches_layout(draft)
                        and draft.get("shared") == self.shared and draft.get("choose_version") == self.choose_version):
                    self.captured = draft["captured"]
                    self.index = draft.get("index", 0)
                    self.app.log(self.app.tr("已恢复校准草稿，可返回检查或重采。",
                                             "Calibration draft restored. Use Back to review or recapture a point."))
                    return
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                continue
        try:
            saved, from_preset = load_text_calibration(self.first_language)
            if not self.matches_layout(saved):
                return
            self.captured = restore_captured(saved, self.shared, self.choose_version)
            self.index = next((i for i, (key, _, _) in enumerate(self.steps) if key not in self.captured), len(self.steps))
            self.app.log(self.app.tr("已载入内置文字坐标。", "Loaded the built-in text positions.") if from_preset
                         else self.app.tr("已载入保存的文字坐标。", "Loaded saved text positions."))
            self.app.log(self.app.tr("可继续采集缺少的点，也可返回重采。", "Capture the remaining points or use Back to recapture."))
        except (OSError, ValueError, KeyError, TypeError):
            self.captured, self.index = {}, 0

    def persist(self):
        draft = {"schema": 3, "size": self.size, "dpi": self.dpi, "shared": self.shared,
                 "choose_version": self.choose_version, "first_language": self.first_language,
                 "captured": self.captured, "index": self.index}
        path = Path(CALIB_DRAFT_FILE)
        temporary = path.with_suffix(".json.tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(draft, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)

    def cancel_pending(self):
        self.generation += 1
        if self.pending is not None:
            self.app.root.after_cancel(self.pending)
            self.pending = None

    def go(self, index):
        self.cancel_pending()
        self.index = max(0, min(index, len(self.steps)))
        tr = self.app.tr
        self.back.configure(state="normal" if self.index else "disabled")
        if self.index == len(self.steps):
            self.instruction.configure(text=tr("坐标已就绪。可以返回检查或重采，确认后保存。", "The points are ready. Go back to review or recapture them, then save."))
            self.status.configure(text=tr("尚未保存；原校准文件保持不变。", "Not saved yet; your previous calibration is unchanged."))
            self.capture_button.configure(text=tr("保存校准", "Save calibration"), state="normal", command=self.save)
            self.next.configure(state="disabled")
        else:
            key, cn, en = self.steps[self.index]
            self.instruction.configure(text=f"{self.index + 1}/{len(self.steps)}  " + tr(cn, en))
            self.capture_button.configure(text=tr("重新采集（5秒）" if key in self.captured else "采集当前点（5秒）", "Recapture (5 s)" if key in self.captured else "Capture point (5 s)"), state="normal", command=self.capture)
            self.next.configure(state="normal" if key in self.captured else "disabled")
            self.status.configure(text=tr("这个点已记录，可重新采集或直接下一步。" if key in self.captured else "点「采集当前点」后，在 5 秒内将鼠标移到目标上并停住。采集时只移动鼠标。F9 取消。",
                                          "Point recorded. Capture it again or click Next." if key in self.captured else "Click Capture, then move the pointer to the target within five seconds and hold it there. Hover during capture. Press F9 to cancel."))

    def capture(self):
        self.cancel_pending()
        generation, index = self.generation, self.index
        self.capture_button.configure(state="disabled")
        self.next.configure(state="disabled")
        self.countdown(5, index, generation)

    def countdown(self, seconds, index, generation):
        if generation != self.generation:
            return
        self.pending = None
        if seconds:
            self.status.configure(text=self.app.tr(f"{seconds}秒后记录鼠标位置；可点上一步撤回。", f"Capturing in {seconds} seconds; Back cancels this capture."))
            self.pending = self.app.root.after(1000, lambda: self.countdown(seconds - 1, index, generation))
            return
        try:
            if self.app.stop_event.is_set():
                self.close()
                return
            origin, size, dpi = geometry(self.hwnd)
            if size != self.size or dpi != self.dpi:
                raise ValueError(self.app.tr("窗口尺寸或DPI已改变，请关闭校准后重试。", "Window size or DPI changed. Close calibration and retry."))
            x, y = cursor_pos()
            point = ((x-origin[0])/size[0], (y-origin[1])/size[1])
            if not all(0 < n < 1 for n in point):
                raise ValueError(self.app.tr("鼠标不在游戏客户区内。可重新采集。", "Pointer outside game client area. Try capturing again."))
            key, cn, en = self.steps[index]
            proposed = dict(self.captured, **{key: point})
            validate_captured_spacing(proposed, key, self.size, self.first_language)
            self.captured[key] = point
            self.app.log(self.app.tr(f"已采集第{index + 1}步：", f"Captured step {index + 1}: ") + str(tuple(round(n, 5) for n in point)))
            self.go(index + 1)
            self.persist()
        except Exception as exc:
            self.go(index)
            message = exc.localized(self.app.tr) if isinstance(exc, CalibrationError) else str(exc)
            self.status.configure(text=message)
            self.app.log(message)

    def save(self):
        try:
            calib = make_calibration(self.captured, self.size, self.dpi, self.shared, self.choose_version, self.first_language)
            # Write only after all points validate; a failed save keeps the previous file intact.
            path = Path(CALIB_FILE)
            temporary = path.with_suffix(".json.tmp")
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(calib, stream, ensure_ascii=False, indent=2)
            os.replace(temporary, path)
            self.app.log(self.app.tr(f"校准已保存。顶部行距 {calib['top']['row'] * self.size[1]:.1f}px；底部行距 {calib['bottom']['row'] * self.size[1]:.1f}px。", f"Calibration saved. Top row spacing {calib['top']['row'] * self.size[1]:.1f}px; bottom spacing {calib['bottom']['row'] * self.size[1]:.1f}px."))
            self.app.log_geometry(self.hwnd)
            self.close()
        except Exception as exc:
            if isinstance(exc, CalibrationError) and exc.step:
                index = next((i for i, (key, _, _) in enumerate(self.steps) if key == exc.step), self.index)
                self.go(index)
            self.status.configure(text=exc.localized(self.app.tr) if isinstance(exc, CalibrationError) else str(exc))

    def poll_stop(self):
        if not self.window.winfo_exists():
            return
        if self.app.stop_event.is_set():
            self.close()
            return
        self.app.root.after(30, self.poll_stop)

    def close(self):
        self.cancel_pending()
        self.app.busy = False
        if self.window.winfo_exists():
            self.window.destroy()


class MediaCalibrationWizard(CalibrationWizard):
    def __init__(self, app, hwnd, plan):
        self.plan = plan
        super().__init__(app, hwnd)
        self.window.title(app.tr("媒体校准", "Media calibration"))

    def get_steps(self):
        kinds = {item[0] for item in self.plan}
        steps = []
        if "cover" in kinds:
            steps.append(("cover", "关闭所有弹窗，将鼠标停在左侧封面选框中心，不用点击。", "Close all dialogs; point at the cover slot on the left without clicking."))
        if "image" in kinds:
            steps.append(("image_first", "将右侧列表滚到底部。将鼠标停在第1张展示图选框中心。后续运行保持同一滚动位置。", "Scroll the right panel to the bottom. Point at image slot 1. Use this scroll position for every run."))
            if sum(item[0] == "image" for item in self.plan) > 1:
                steps.append(("image_next", "保持面板不动，停在第2张展示图选框中心。若只有一格，先手动加入一张显示第二格；记录后可手动移除测试图。第3、4格按同一间距计算。", "Keep the panel still; point at image slot 2. If only one slot is visible, manually add an image to reveal slot 2; remove that test image afterward. Slots 3 and 4 use the same spacing."))
        if "video" in kinds:
            steps.append(("video", "将右侧列表滚到底部，将鼠标停在展示视频的加号选框中心，不用点击。", "Scroll the right panel to the bottom; point at the video + slot without clicking."))
        return steps

    def restore(self):
        try:
            saved, from_preset = load_calibration("media.json", MEDIA_CALIB_FILE)
            if saved.get("schema") == 1 and saved.get("size") == list(self.size) and saved.get("dpi") == self.dpi:
                self.captured = saved["points"]
                self.index = next((i for i, (key, _, _) in enumerate(self.steps) if key not in self.captured), len(self.steps))
                if from_preset:
                    self.app.log(self.app.tr("已载入内置媒体坐标，可返回重采。",
                                             "Loaded the built-in media positions. Use Back to recapture."))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            self.captured = {}

    def persist(self):
        # Media capture is at most four points; Save is the only disk write.
        pass

    def save(self):
        try:
            data = {"schema": 1, "size": self.size, "dpi": self.dpi, "scale": self.dpi / 96, "points": self.captured}
            validate_media_calibration(data, self.plan)
            temporary = MEDIA_CALIB_FILE + ".tmp"
            with open(temporary, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
            os.replace(temporary, MEDIA_CALIB_FILE)
            self.app.log(self.app.tr("媒体校准已保存；文字校准保持不变。", "Media calibration saved; text calibration unchanged."))
            self.app.log_geometry(self.hwnd)
            self.close()
        except Exception as exc:
            if isinstance(exc, CalibrationError) and exc.step:
                self.go(next((i for i, (key, _, _) in enumerate(self.steps) if key == exc.step), self.index))
            self.status.configure(text=exc.localized(self.app.tr) if isinstance(exc, CalibrationError) else str(exc))


class MediaPanel:
    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title(app.tr("封面 / 展示图 / 视频", "Cover / Images / Video") + f" · v{APP_VERSION}")
        self.window.geometry("850x450")
        self.window.protocol("WM_DELETE_WINDOW", self.window.withdraw)
        self.paths = [tk.StringVar() for _ in range(6)]
        self.delay = tk.DoubleVar(value=2)
        app.widget(ttk.Label, self.window,
                   "在关卡详情页操作；先关闭多语言面板，把右侧滚到底部。展示图从第1格开始，已有图请先手动清空。",
                   "Use the level details page. Close multilingual settings and scroll right panel to bottom. Images start at slot 1; clear existing images manually.",
                   wraplength=800).pack(fill="x", padx=12, pady=10)
        app.widget(ttk.Label, self.window, "文件栏支持Ctrl+V粘贴复制的文件或完整路径；多张图片从当前栏依次放入。",
                   "Ctrl+V accepts copied files or full paths; multiple images fill rows starting at the current field.",
                   wraplength=800).pack(fill="x", padx=12, pady=(0, 4))
        form = ttk.Frame(self.window); form.pack(fill="x", padx=12)
        form.columnconfigure(1, weight=1)
        self.entries = []
        self.paste_menu = tk.Menu(self.window, tearoff=False)
        for i in range(6):
            cn, en = ("封面", "Cover") if i == 0 else (("视频（可选）", "Video (optional)") if i == 5 else (f"展示图{i}（可选）", f"Image {i} (optional)"))
            app.widget(ttk.Label, form, cn, en).grid(row=i, column=0, sticky="w", pady=5)
            entry = ttk.Entry(form, textvariable=self.paths[i], justify="right")
            entry.grid(row=i, column=1, sticky="ew", padx=6)
            entry.bind("<<Paste>>", lambda event, n=i: self.paste(n))
            entry.bind("<Button-3>", lambda event, n=i: self.paste_context(event, n))
            self.entries.append(entry)
            self.paths[i].trace_add("write", lambda *args, n=i: self.window.after_idle(lambda: self.entries[n].xview_moveto(1.0)))
            app.widget(ttk.Button, form, "选择…", "Choose…", command=lambda n=i: self.pick(n)).grid(row=i, column=2)
            app.widget(ttk.Button, form, "清空", "Clear", command=lambda n=i: self.clear(n)).grid(row=i, column=3, padx=4)
        options = ttk.Frame(self.window); options.pack(fill="x", padx=12, pady=8)
        app.widget(ttk.Label, options, "每个文件导入后等待（秒）", "Wait after each import (s)").pack(side="left")
        ttk.Spinbox(options, from_=1, to=120, increment=1, textvariable=self.delay, width=6).pack(side="left", padx=6)
        app.widget(ttk.Label, options, "图片≤5MB；视频≤300MB。留空跳过，F9停止。", "Images ≤5 MB; video ≤300 MB. Blank skips; F9 stops.").pack(side="left")
        actions = ttk.Frame(self.window); actions.pack(fill="x", padx=12, pady=8)
        for cn, en, cb in (("校准媒体位置", "Calibrate media", self.calibrate),
                           ("核对媒体位置", "Check positions", lambda: self.start(True)),
                           ("填写媒体文件", "Fill media files", self.start),
                           ("停止（F9）", "Stop (F9)", app.stop_event.set)):
            app.widget(ttk.Button, actions, cn, en, command=cb).pack(side="left", padx=4)

    def show(self):
        self.window.title(self.app.tr("封面 / 展示图 / 视频", "Cover / Images / Video") + f" · v{APP_VERSION}")
        self.window.deiconify()
        self.window.lift()

    def clear(self, index):
        if not self.app.busy:
            self.paths[index].set("")

    def paste_context(self, event, index):
        self.paste_menu.delete(0, "end")
        self.paste_menu.add_command(label=self.app.tr("粘贴文件或路径", "Paste files or paths"), command=lambda: self.paste(index))
        try:
            self.paste_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.paste_menu.grab_release()

    def paste(self, index):
        if self.app.busy:
            return "break"
        try:
            incoming = clipboard_file_paths(self.window.winfo_id())
            if incoming is None:
                try:
                    incoming = pasted_path_lines(self.window.clipboard_get())
                except tk.TclError as exc:
                    raise ValueError(self.app.tr("剪贴板里没有文件或文件路径。", "Clipboard contains no files or file paths.")) from exc
            merged = merge_pasted_media([p.get() for p in self.paths], index, incoming, self.app.tr)
            for variable, path in zip(self.paths, merged):
                variable.set(path)
        except Exception as exc:
            self.app.error(exc)
        return "break"

    def pick(self, index):
        if self.app.busy:
            return
        types = [(self.app.tr("视频（格式由游戏验证）", "Video (format checked by game)"), "*.*")] if index == 5 else [(self.app.tr("图片", "Images"), "*.png *.jpg *.jpeg")]
        title = self.app.tr("选择视频", "Choose video") if index == 5 else self.app.tr("选择图片", "Choose image")
        path = filedialog.askopenfilename(parent=self.window, title=title, filetypes=types)
        if path:
            self.paths[index].set(path)

    def plan(self):
        return media_plan(self.paths[0].get(), [p.get() for p in self.paths[1:5]], self.paths[5].get(), self.app.tr)

    def calibrate(self):
        if self.app.busy:
            return
        try:
            plan = self.plan()
            hwnd = self.app.game()
            self.app.log_geometry(hwnd)
            self.app.stop_event.clear()
            self.app.busy = True
            MediaCalibrationWizard(self.app, hwnd, plan)
        except Exception as exc:
            self.app.busy = False
            self.app.error(exc)

    def start(self, probe=False):
        app = self.app
        if app.busy:
            return
        try:
            plan = self.plan()
            hwnd = app.game()
            try:
                calib, from_preset = load_calibration("media.json", MEDIA_CALIB_FILE)
                validate_media_calibration(calib, plan)
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                raise ValueError(app.tr("请先点「校准媒体位置」，补齐本次所需的坐标。", "Use Calibrate media to record all positions needed for this run.")) from exc
            delay = self.delay.get()
            if not 1 <= delay <= 120:
                raise ValueError(app.tr("导入等待须在1～120秒之间。", "Import wait must be 1–120 seconds."))
            if not messagebox.askokcancel(app.tr("核对媒体页面", "Verify media page"),
                    app.tr("关闭多语言面板和文件弹窗，将右侧列表滚到底部。\n\n展示图从第 1 格按顺序填入，请先手动清空已有展示图。填写前可用「核对媒体位置」检查落点。F9 停止。",
                           "Close Multilanguage Settings and any file dialogs, then scroll the right panel all the way down.\n\nImages fill from slot 1. Clear existing images first and use Check positions before filling. Press F9 to stop."), parent=self.window):
                return
        except Exception as exc:
            app.error(exc)
            return
        app.busy = True
        app.stop_event.clear()
        owner = app.root.winfo_id()
        english = app.ui_language.get() == "English"
        tr = lambda cn, en: en if english else cn
        app.log(tr("媒体位置检查" if probe else "媒体填写", "Media position check" if probe else "Media fill") + f" · v{APP_VERSION}")
        def should_stop():
            if user32.GetAsyncKeyState(0x78) & 0x8000:
                app.stop_event.set()
            return app.stop_event.is_set()
        def worker():
            try:
                pause(.6, should_stop)
                activate_media_game(hwnd, should_stop, tr)
                size = app.log_geometry(hwnd, log=app.messages.put, tr=tr)
                if from_preset:
                    check_preset_size(calib, size, tr)
                    app.messages.put(tr("使用内置媒体坐标。", "Using the built-in media positions."))
                do_media(plan, calib, hwnd, app.messages.put, should_stop, tr, owner, delay, probe)
            except Stopped as exc:
                app.messages.put(tr("媒体操作已停止。", "Media operation stopped.") + str(exc))
            except Exception as exc:
                app.messages.put(tr("媒体操作出错并停止：", "Media operation failed and stopped: ") + str(exc))
            finally:
                app.messages.put(None)
        threading.Thread(target=worker, daemon=True).start()


class App:
    def __init__(self, root):
        self.root = root
        root.title(APP_TITLE)
        root.geometry("950x650")
        self.ui_language = tk.StringVar(value="中文")
        self.path, self.sheet = tk.StringVar(), tk.StringVar()
        self.first_language = tk.StringVar(value=LANGS[0])
        self.speed = tk.DoubleVar(value=1.0)
        self.shared_dialog = tk.BooleanVar(value=True)
        self.lang_vars = {lang: tk.BooleanVar(value=True) for lang in LANGS}
        self.field_vars = {key: tk.BooleanVar(value=key != "version") for key, _ in FIELDS}
        self.busy = False
        self.stop_event = threading.Event()
        self.messages = queue.Queue()
        self.widgets = []
        self.media_panel = None
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(30, self.drain)

    def tr(self, cn, en):
        return en if self.ui_language.get() == "English" else cn

    def widget(self, cls, parent, cn, en, **kw):
        widget = cls(parent, text=self.tr(cn, en), **kw)
        self.widgets.append((widget, cn, en))
        return widget

    def _build(self):
        pad = dict(padx=6, pady=3)
        f1 = ttk.Frame(self.root); f1.pack(fill="x", **pad)
        self.widget(ttk.Button, f1, "导出 Excel 模板…", "Export Excel Template…", command=self.export_template).pack(side="left")
        self.widget(ttk.Button, f1, "① 打开填好的 Excel…", "① Open Filled Excel…", command=self.pick_file).pack(side="left", padx=4)
        self.widget(ttk.Button, f1, "封面 / 展示图 / 视频…", "Cover / Images / Video…", command=self.open_media).pack(side="left", padx=4)
        switch = ttk.Combobox(f1, textvariable=self.ui_language, values=("中文", "English"), width=8, state="readonly")
        switch.pack(side="right")
        ttk.Label(f1, text="Language").pack(side="right", padx=(0, 6))
        switch.bind("<<ComboboxSelected>>", lambda _: self.translate_ui())
        self.widget(ttk.Label, self.root, "先导出模板，填入关卡资料并保存，再用①打开。",
                    "Export the Excel template, enter your stage info, save it, then open the workbook with ①.",
                    wraplength=900).pack(anchor="w", padx=12, pady=(3, 0))
        ttk.Label(self.root, textvariable=self.path, foreground="#555").pack(anchor="w", padx=12)
        f2 = ttk.Frame(self.root); f2.pack(fill="x", **pad)
        self.widget(ttk.Label, f2, "工作表", "Worksheet").pack(side="left")
        self.sheet_box = ttk.Combobox(f2, textvariable=self.sheet, width=24, state="readonly")
        self.sheet_box.pack(side="left", padx=6)
        self.sheet_box.bind("<<ComboboxSelected>>", lambda _: self.preview())
        self.widget(ttk.Label, f2, "游戏首行（默认语言）", "Stage Default Language (Row 1)").pack(side="left", padx=(12, 0))
        ttk.Combobox(f2, textvariable=self.first_language, values=LANGS, width=12,
                     state="readonly").pack(side="left", padx=6)
        f3 = self.widget(ttk.LabelFrame, self.root, "语言", "Languages"); f3.pack(fill="x", **pad)
        self.lang_checks = []
        for i, lang in enumerate(LANGS):
            check = self.widget(ttk.Checkbutton, f3, LANG_NAMES_CN[i], LANG_NAMES_EN[i], variable=self.lang_vars[lang])
            check.grid(row=i // 5, column=i % 5, sticky="w", padx=4)
            self.lang_checks.append(check)
        f4 = self.widget(ttk.LabelFrame, self.root, "要填的项", "Fields"); f4.pack(fill="x", **pad)
        for key, cn in FIELDS:
            self.widget(ttk.Checkbutton, f4, cn, FIELD_NAMES_EN[key], variable=self.field_vars[key]).pack(side="left", padx=4)
        f5 = ttk.Frame(self.root); f5.pack(fill="x", **pad)
        for cn, en, callback in (("② 使用说明", "② Setup Guide", self.help),
                                  ("③ 校准一次", "③ Calibrate", self.calibrate),
                                  ("④ 看格子位置", "④ Check positions", self.probe),
                                  ("⑤ 一键填写", "⑤ Fill all", self.fill)):
            self.widget(ttk.Button, f5, cn, en, command=callback).pack(side="left", padx=3)
        f6 = ttk.Frame(self.root); f6.pack(fill="x", **pad)
        self.widget(ttk.Button, f6, "停止（F9）", "Stop (F9)", command=self.stop_event.set).pack(side="left")
        self.widget(ttk.Label, f6, "  慢/快", "  Speed").pack(side="left")
        ttk.Scale(f6, from_=0.5, to=3, variable=self.speed, length=110).pack(side="left")
        self.widget(ttk.Checkbutton, self.root, "共用弹窗位置（千星，精简校准）", "Shared dialog positions (Miliastra, fewer steps)", variable=self.shared_dialog).pack(anchor="w", padx=10)
        self.logbox = tk.Text(self.root, height=18, wrap="word", state="disabled")
        self.logbox.pack(fill="both", expand=True, **pad)
        self.log(self.tr(f"当前版本：v{APP_VERSION}", f"Version: v{APP_VERSION}"))
        self.log(self.tr("运行文件：", "Running file: ") + str(application_file()))
        self.log(self.tr("进程号：", "Process ID: ") + str(os.getpid()))
        self.log(self.tr("导出 Excel 模板，填好并保存，再用①打开。②可查看完整步骤。",
                         "Export the Excel template, fill it in, and save it. Open it with ①. Click ② for the full setup guide."))

    def translate_ui(self):
        for widget, cn, en in self.widgets:
            widget.configure(text=self.tr(cn, en))
        self.root.title(self.tr(APP_TITLE, f"Miliastra Preview Autofill v{APP_VERSION}"))
        if self.media_panel is not None:
            self.media_panel.window.title(self.tr("封面 / 展示图 / 视频", "Cover / Images / Video") + f" · v{APP_VERSION}")
        # Historic logs are a record; fresh logs use the newly selected language.
        self.log(self.tr("界面与后续日志已切换为中文。", "Interface and subsequent logs switched to English."))

    def open_media(self):
        if self.media_panel is None:
            self.media_panel = MediaPanel(self)
        self.media_panel.show()

    def log(self, text):
        self.logbox.configure(state="normal")
        self.logbox.insert("end", text + "\n")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def drain(self):
        if self.busy and user32.GetAsyncKeyState(0x78) & 0x8000:
            self.stop_event.set()
        try:
            while True:
                message = self.messages.get_nowait()
                if message is None:
                    self.busy = False
                elif isinstance(message, tuple) and message[0] == "confirm_page":
                    _, page, order, reply, event = message
                    try:
                        if self.stop_event.is_set():
                            reply["ok"] = False
                        else:
                            if page == "top":
                                heading = self.tr("将列表滚到最顶部，核对前 9 行的语言顺序。",
                                                  "Scroll all the way up and check the order of the first nine rows.")
                                rows = order[:9]
                            else:
                                heading = self.tr("将列表滚到最底部，核对最后 6 行的语言顺序。",
                                                  "Scroll all the way down and check the order of the last six rows.")
                                rows = order[9:]
                            instruction = self.tr("顺序相同才点确定。如果顺序不同，请取消并检查游戏首行和已添加的语言。",
                                                  "Click OK only if the order matches. If it differs, cancel and check the stage's first row and added languages.")
                            reply["ok"] = messagebox.askokcancel(
                                self.tr("核对语言顺序", "Check Language Order"),
                                f"{heading}\n\n{' → '.join(rows)}\n\n{instruction}", parent=self.root)
                    finally:
                        event.set()
                else:
                    self.log(message)
        except queue.Empty:
            pass
        self.root.after(30, self.drain)

    def error(self, exc):
        messagebox.showerror(self.root.title(), exc.localized(self.tr) if isinstance(exc, CalibrationError) else str(exc))

    def pick_file(self):
        path = filedialog.askopenfilename(title=self.tr("选 Excel", "Choose Excel"), filetypes=[("Excel", "*.xlsx *.xlsm"), (self.tr("全部", "All files"), "*.*")])
        if not path:
            return
        try:
            names = _xlsx_sheets(path)
            self.path.set(path)
            self.sheet_box["values"] = names
            self.sheet.set(names[0] if names else "")
            self.log(self.tr(f"读到 {len(names)} 个工作表：", f"Found {len(names)} worksheets: ") + ", ".join(names))
            self.preview()
        except Exception as exc:
            self.error(exc)

    def preview(self):
        if not self.path.get():
            return
        try:
            texts = read_table(self.path.get(), self.sheet.get(), log=lambda _: None)
            detected = {lang for values in texts.values() for lang in values}
            for lang, check in zip(LANGS, self.lang_checks):
                check.configure(state="normal" if lang in detected else "disabled")
            for key, cn in FIELDS:
                got = [self.tr(LANG_NAMES_CN[i], LANG_NAMES_EN[i]) for i, lang in enumerate(LANGS) if lang in texts.get(key, {})]
                self.log(self.tr(cn, FIELD_NAMES_EN[key]) + self.tr(f"：{len(got)} 种语言（", f": {len(got)} languages (") + ", ".join(got) + ")")
        except Exception as exc:
            self.error(exc)

    def export_template(self):
        path = filedialog.asksaveasfilename(title=self.tr("导出 Excel 模板", "Export Excel Template"),
                                          initialfile=self.tr("多语言填写模板.xlsx", "Miliastra Preview Template.xlsx"),
                                          defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
        if path:
            try:
                write_template(path, english=self.ui_language.get() == "English")
                self.log(self.tr(f"模板已保存到 {path}。填好后请用①打开。",
                                 f"Template saved to {path}. Enter your stage info, save the workbook, then open it with ①."))
            except Exception as exc:
                self.error(exc)

    def help(self):
        messagebox.showinfo(self.root.title(), self.tr(
            "1. 点「导出 Excel 模板」。在各语言列的第 2、9、12、16 行填写关卡资料，保留表头，首次发布请清空第 16 行示例。保存后用①打开并选工作表。\n\n"
            "2. 在游戏里打开关卡详情页的多语言设置。如果语言未齐，通过「添加语言 → 全选」启用 15 种语言。滚到顶部，在工具里选择游戏首行标着「默认」的语言。\n\n"
            "3. 点④，使用已保存或内置的坐标核对两屏语言顺序和鼠标落点。落点偏移时点③。每次点「采集当前点」后，在 5 秒内把鼠标移到指定单元格、图标或保存按钮的中心并停住。\n\n"
            "4. 核对后点⑤填写，检查内容后在游戏里手动提交。F9 停止。首次发布保持「版本更新记录」未勾选。更新时检查预设是否对应目标版本，必要时用③重采版本选项。",
            "1. Click Export Excel Template. Enter your stage info in the language columns on rows 2, 9, 12 and 16. Keep the headers and clear the row 16 example for a first release. Save the workbook, open it with ① and select a worksheet.\n\n"
            "2. Open Stage Details > Multilanguage Settings in Genshin Impact. If any languages are missing, use Add Language > Select All > OK to enable all 15. Scroll to the top and set Stage Default Language (Row 1) in the tool to the language marked Default in the game.\n\n"
            "3. Use ④ Check positions to verify the row order and pointer targets with saved or built-in positions. If a target is off, open ③ Calibrate. Click Capture and move the pointer to the center of the indicated cell, icon, or OK button within five seconds. Hold it there until the timer ends.\n\n"
            "4. Click ⑤ Fill all after checking the targets. Review the result in the game before you submit. Press F9 to stop. Leave Update Log unchecked for a first release. For an update, check the preset version position and use ③ to capture a different option if needed."))

    def game(self):
        hwnd = find_game_window()
        if not hwnd:
            raise ValueError(self.tr("找不到原神游戏窗口。请先启动 PC 客户端并打开游戏窗口。",
                                     "Couldn't find the Genshin Impact game window. Launch the PC game and keep its window open."))
        return hwnd

    def log_geometry(self, hwnd, log=None, tr=None):
        log, tr = log or self.log, tr or self.tr
        origin, size, dpi = geometry(hwnd)
        log(tr(f"物理客户区 {size[0]}×{size[1]}，左上 {origin}，DPI {dpi}，缩放 {dpi / 96:.0%}。", f"Physical client area {size[0]}×{size[1]}, origin {origin}, DPI {dpi}, scale {dpi / 96:.0%}."))
        rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            log(tr(f"物理窗口外框 {rect.right - rect.left}×{rect.bottom - rect.top}，左上 ({rect.left}, {rect.top})。比例坐标以客户区为准。", f"Physical outer window {rect.right - rect.left}×{rect.bottom - rect.top}, origin ({rect.left}, {rect.top}). Proportional coordinates use the client area."))
        return size

    def calibrate(self):
        if self.busy:
            return
        try:
            first_language = self.first_language.get()
            stage_language_order(first_language)
            hwnd = self.game()
            self.log_geometry(hwnd)
            self.stop_event.clear()
            self.busy = True
            CalibrationWizard(self, hwnd, shared_dialog=self.shared_dialog.get(), choose_version=self.field_vars["version"].get(),
                              first_language=first_language)
        except Exception as exc:
            self.busy = False
            self.error(exc)

    def start(self, probe=False):
        if self.busy:
            return
        try:
            first_language = self.first_language.get()
            try:
                calib, from_preset = load_text_calibration(first_language)
            except CalibrationError:
                raise
            except (OSError, ValueError, TypeError) as exc:
                raise ValueError(self.tr("校准文件无法读取，请点③重新校准。", "The calibration file is invalid. Use ③ to calibrate again.")) from exc
            order = validate_calibration(calib)
            if not self.path.get():
                raise ValueError(self.tr("请先导出模板、填写保存，再用①打开表格。",
                                         "Export the Excel template, fill it in, save it, then open it with ①."))
            hwnd = self.game()
            size = self.log_geometry(hwnd)
            if from_preset:
                check_preset_size(calib, size, self.tr)
                self.log(self.tr("使用内置文字坐标，填写前先用④核对落点。",
                                 "Using the built-in text positions. Verify targets with ④ before filling."))
            texts = read_table(self.path.get(), self.sheet.get(), log=lambda _: None)
            plan = build_plan(texts, [l for l in LANGS if self.lang_vars[l].get()],
                              [k for k, _ in FIELDS if self.field_vars[k].get()], first_language)
            if not plan:
                raise ValueError(self.tr("按现在的勾选没有可填的内容。", "No content matches the current selection."))
            choose_version = any(cell[2] == "version" for cell in plan)
            if choose_version and "version_selector" not in calib:
                raise ValueError(self.tr("请先校准版本号下拉与目标选项。", "Calibrate the Update Log version dropdown and target option first."))
            if not user32.SetForegroundWindow(hwnd):
                raise OSError(self.tr("无法激活游戏窗口。", "Cannot activate the game window."))
        except Exception as exc:
            self.error(exc)
            return
        self.busy = True
        self.stop_event.clear()
        # Freeze UI settings on the Tk thread; worker never reads/writes Tk objects.
        english = self.ui_language.get() == "English"
        tr = lambda cn, en: en if english else cn
        speed = self.speed.get()
        clipboard_owner = self.root.winfo_id()
        self.log(tr("仅在列表内发送滚轮、移动鼠标，不点击或填写格子；每次换屏后先确认。F9停止。" if probe else f"开始填 {len(plan)} 格。F9随时停止。", "Scrolling over the list and moving the pointer only; no cell clicks or edits. Confirm each page. F9 stops." if probe else f"Filling {len(plan)} cells. Press F9 to stop at any time."))
        if not probe:
            versions = sum(cell[2] == "version" for cell in plan)
            self.log(tr(f"本次版本更新记录：{versions}格。" + ("会选择已校准的版本号。" if versions else "未勾选该字段或无内容，本次不会操作版本号。"), f"Update Log: {versions} cells. " + ("The calibrated version will be selected." if versions else "No Update Log entries selected.")))
        def should_stop():
            if user32.GetAsyncKeyState(0x78) & 0x8000:
                self.stop_event.set()
            return self.stop_event.is_set()
        def confirm_page(page):
            event, reply = threading.Event(), {}
            self.messages.put(("confirm_page", page, order, reply, event))
            while not event.wait(.02):
                check_stop(should_stop)
            check_stop(should_stop)
            return reply.get("ok", False)
        def worker():
            try:
                pause(0.6, should_stop)
                do_fill(plan, calib, hwnd, self.messages.put, speed, should_stop, tr, probe, clipboard_owner, choose_version, confirm_page)
            except Stopped:
                self.messages.put(tr("已停下。", "Stopped."))
            except Exception as exc:
                self.messages.put(tr("出错：", "Error: ") + str(exc))
            finally:
                self.messages.put(None)
        threading.Thread(target=worker, daemon=True).start()

    def probe(self):
        self.start(probe=True)

    def fill(self):
        self.start()

    def close(self):
        self.stop_event.set()
        self.root.destroy()


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        portable_self_test(Path(sys.argv[2]))
        return
    elevate()
    enable_physical_pixels()
    root = tk.Tk()
    App(root)
    root.mainloop()


def portable_self_test(report_path):
    """Exercise the packaged Tk/runtime without elevation or game input."""
    import tempfile
    report = {"version": APP_VERSION, "frozen": bool(getattr(sys, "frozen", False))}
    root = None
    try:
        enable_physical_pixels()
        root = tk.Tk()
        root.withdraw()
        app = App(root)
        root.update()
        report["tk"] = root.tk.call("info", "patchlevel")
        report["dpi_aware"] = True
        report["calibration_next_to_app"] = Path(CALIB_FILE).parent == application_file().parent
        with tempfile.TemporaryDirectory(prefix="preview-autofill-selftest-") as temp:
            template = Path(temp) / "Template.xlsx"
            for english, language in ((False, "简体中文"), (True, "English")):
                write_template(template, english=english)
                data = read_table(template, log=lambda _: None)
                report[f"{language}_template_roundtrip"] = all(set(data[key]) == {language} for key, _ in FIELDS)
        report["template_roundtrip"] = report["简体中文_template_roundtrip"] and report["English_template_roundtrip"]
        text_preset, _ = load_calibration("text.json")
        validate_calibration(text_preset)
        media_preset, _ = load_calibration("media.json")
        validate_media_calibration(media_preset, [("cover", 0, ""), ("image", 3, ""), ("video", 0, "")])
        report["built_in_presets"] = True
        report["ok"] = all(report[k] for k in ("dpi_aware", "calibration_next_to_app", "template_roundtrip", "built_in_presets"))
    except Exception as exc:
        report.update(ok=False, error=str(exc))
    finally:
        if root is not None:
            root.destroy()
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
