"""Windows regression tests. No real keystrokes, mouse input or clipboard changes."""
import ctypes
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

spec = importlib.util.spec_from_file_location("fill_tool", Path(__file__).resolve().parent.parent / "千星奇域-预览信息-一键填写.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def calibration():
    return {"schema": 3, "size": [962, 564], "dpi": 96, "scale": 1,
            "top": {"anchor": [.3, .2], "row": .06},
            "bottom": {"anchor": [.3, .4], "row": .06},
            "cells": {"name": [.3, .2], "notes": [.45, .2], "desc": [.6, .2], "version": [.85, .21]},
            "dialogs": {key: {"text": [.4, y], "confirm": [.6, .8]}
                        for key, y in (("notes", .4), ("desc", .5), ("version", .6))}}


class FillTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.logs = []
        self.stop = False
        patches = [patch.object(tool.user32, "GetForegroundWindow", return_value=42),
                   patch.object(tool, "scroll_notch", side_effect=lambda n: self.events.append(("wheel", (n * 120) & 0xFFFFFFFF))),
                   patch.object(tool.user32, "mouse_event", side_effect=lambda *a: self.events.append(("wheel", a[3]))),
                   patch.object(tool, "move_to", side_effect=lambda *a: self.events.append(("move", a))),
                   patch.object(tool, "screen_point", side_effect=lambda pt, hwnd: pt),
                   patch.object(tool, "click", side_effect=lambda x, y, stop: self.events.append(("click", (x, y)))),
                   patch.object(tool, "combo", side_effect=lambda *a: self.events.append(("keys", a))),
                   patch.object(tool, "set_clipboard", side_effect=lambda text, stop, owner: self.events.append(("clipboard", text))),
                   patch.object(tool, "pause", side_effect=lambda seconds, stop: tool.check_stop(stop))]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def run_plan(self, keys=("name", "notes", "desc", "version"), languages=None):
        languages = languages or tool.LANGS[:1]
        texts = {key: {lang: "中文 한국어\nText" for lang in languages} for key in keys}
        plan = tool.build_plan(texts, languages, keys)
        tool.do_fill(plan, calibration(), 42, self.logs.append, should_stop=lambda: self.stop, tr=lambda cn, en: en, clipboard_owner=123, confirm_page=lambda _: True)

    def test_clear_before_every_paste_and_version_dialog(self):
        self.run_plan()
        for index, event in enumerate(self.events):
            if event[0] == "clipboard":
                self.assertEqual(self.events[index - 1], ("keys", ("ctrl", "a")))
                self.assertEqual(self.events[index + 1], ("keys", ("ctrl", "v")))
        version_buttons = [e[1] for e in self.events if e[0] == "click" and e[1][0] == .85]
        self.assertEqual(len(version_buttons), 1)
        self.assertAlmostEqual(version_buttons[0][1], .21)
        self.assertIn(("click", (.4, .6)), self.events)
        self.assertEqual(sum(e[0] == "clipboard" for e in self.events), 4)

    def test_cell_failure_continues(self):
        with patch.object(tool, "set_clipboard", side_effect=[OSError("clipboard busy"), None]):
            self.run_plan(keys=("name", "notes"))
        self.assertEqual(sum("failed:" in line for line in self.logs), 1)
        self.assertIn("Finished with 1 failed cells", self.logs[-1])

    def test_stop_after_clear_prevents_paste_and_confirm(self):
        def set_and_stop(text, stop, owner):
            self.stop = True
        with patch.object(tool, "set_clipboard", side_effect=set_and_stop):
            self.run_plan(keys=("version",))
        self.assertNotIn(("keys", ("ctrl", "v")), self.events)
        self.assertNotIn(("click", (.6, .8)), self.events)
        self.assertEqual(self.logs[-1], "Stopped.")

    def test_two_pages_reset_scroll_before_bottom(self):
        self.run_plan(keys=("name",), languages=[tool.LANGS[0], tool.LANGS[9], tool.LANGS[14]])
        wheel = [e[1] for e in self.events if e[0] == "wheel"]
        self.assertEqual(wheel, [120] * 30 + [(-120) & 0xFFFFFFFF] * 15)
        rows = [e[1][1] for e in self.events if e[0] == "click" and e[1][0] == .3]
        self.assertAlmostEqual(rows[1], .4)
        self.assertIn(("click", (.3, .7)), self.events)

    def test_english_default_pastes_each_translation_into_its_in_game_row(self):
        c = calibration()
        c["first_language"] = "English"
        names = {"简体中文": "Simplified", "English": "English", "繁體中文": "Traditional", "Tiếng Việt": "Vietnamese"}
        plan = tool.build_plan({"name": names}, names, ["name"], "English")
        pages = []
        tool.do_fill(plan, c, 42, self.logs.append, tr=lambda cn, en: en,
                     confirm_page=lambda page: pages.append(page) or True)
        self.assertEqual(pages, ["top", "bottom"])
        self.assertEqual([value for event, value in self.events if event == "clipboard"],
                         ["English", "Simplified", "Traditional", "Vietnamese"])
        clicks = [point for event, point in self.events if event == "click"]
        self.assertEqual([round(y, 2) for _, y in clicks], [.2, .26, .32, .4])
        self.assertTrue(any("English · Stage Name" in entry for entry in self.logs))

    def test_mismatched_language_plan_stops_before_input(self):
        c = calibration()
        c["first_language"] = "English"
        plan = tool.build_plan({"name": {"简体中文": "test"}}, ["简体中文"], ["name"])
        with self.assertRaises(tool.CalibrationError):
            tool.do_fill(plan, c, 42, self.logs.append, confirm_page=lambda _: True)
        self.assertEqual(self.events, [])

    def test_default_from_lower_page_moves_thai_to_the_bottom_anchor(self):
        c = calibration()
        c["first_language"] = "Deutsch"
        names = {"Deutsch": "German", "ภาษาไทย": "Thai", "Tiếng Việt": "Vietnamese"}
        plan = tool.build_plan({"name": names}, names, ["name"], "Deutsch")
        tool.do_fill(plan, c, 42, self.logs.append, confirm_page=lambda _: True)
        self.assertEqual([value for event, value in self.events if event == "clipboard"],
                         ["German", "Thai", "Vietnamese"])
        self.assertEqual([round(point[1], 2) for event, point in self.events if event == "click"],
                         [.2, .4, .46])

    def test_version_dropdown_and_option_shared_across_languages(self):
        c = calibration()
        c['version_selector'] = {'dropdown': [.5, .3], 'option': [.5, .35]}
        languages = tool.LANGS[:2]
        plan = tool.build_plan({'version': {lang: 'Update' for lang in languages}}, languages, ['version'])
        tool.do_fill(plan, c, 42, self.logs.append, should_stop=lambda: False,
                     clipboard_owner=123, choose_version=True, confirm_page=lambda _: True)
        clicks = [e[1] for e in self.events if e[0] == 'click']
        self.assertEqual(clicks.count((.5, .3)), 2)
        self.assertEqual(clicks.count((.5, .35)), 2)
        self.assertLess(clicks.index((.5, .3)), clicks.index((.5, .35)))
        self.assertLess(clicks.index((.5, .35)), clicks.index((.4, .6)))

    def test_rejected_scroll_stops_before_cell_click(self):
        with patch.object(tool, 'scroll_notch', side_effect=tool.ScrollRejected('input blocked')):
            self.run_plan(keys=('name',), languages=[tool.LANGS[9]])
        clicks = [e[1] for e in self.events if e[0] == 'click']
        self.assertEqual(clicks, [])
        self.assertFalse(any(e[0] == 'clipboard' for e in self.events))
        self.assertTrue(any('stopped before clicking bottom cells' in line for line in self.logs))

    def test_each_selected_version_row_is_used_for_all_languages(self):
        c = calibration()
        c['version_selector'] = {'dropdown': [.5, .25],
                                 'options': {str(row): [.5, .3 + row * .04] for row in range(1, 5)}}
        plan = tool.build_plan({'version': {lang: 'Update' for lang in tool.LANGS[:2]}}, tool.LANGS[:2], ['version'])
        for row in range(1, 5):
            self.events.clear()
            tool.do_fill(plan, c, 42, self.logs.append, choose_version=True, version_row=row, confirm_page=lambda _: True)
            clicks = [point for event, point in self.events if event == 'click']
            self.assertEqual(clicks.count((.5, .3 + row * .04)), 2)
            self.assertEqual(len([text for event, text in self.events if event == 'clipboard']), 2)

    def test_version_probe_checks_normal_cells_then_leaves_one_dropdown_open(self):
        c = calibration()
        c['version_selector'] = {'dropdown': [.5, .25], 'options': {'4': [.5, .46]}}
        languages = ['简体中文', 'Tiếng Việt']
        plan = tool.build_plan({'name': {lang: 'Name' for lang in languages},
                                'version': {lang: 'Must not paste' for lang in languages}},
                               languages, ['name', 'version'])
        pages = []
        tool.do_fill(plan, c, 42, self.logs.append, probe=True, choose_version=True,
                     version_row=4, confirm_page=lambda page: pages.append(page) or True)
        self.assertEqual(pages, ['top', 'bottom'])
        clicks = [point for event, point in self.events if event == 'click']
        self.assertEqual(len(clicks), 2)  # outer pencil and dropdown only
        self.assertEqual(clicks[0][0], .85)
        self.assertAlmostEqual(clicks[0][1], .41)  # stay on the page already checked
        self.assertEqual(clicks[-1], (.5, .25))
        event, last_cell = self.events[self.events.index(('click', clicks[0])) - 1]
        self.assertEqual(event, 'move')
        self.assertAlmostEqual(last_cell[1], .4)
        self.assertEqual(self.events[-1], ('move', (.5, .46)))
        self.assertFalse(any(event in ('clipboard', 'keys') for event, _ in self.events))
        self.assertTrue(any('下拉第 4 行' in log for log in self.logs))

    def test_failed_version_action_does_not_try_to_close_unknown_dialog(self):
        c = calibration()
        c['version_selector'] = {'dropdown': [.5, .25], 'options': {'2': [.5, .38]}}
        plan = tool.build_plan({'version': {'简体中文': 'Update'}}, ['简体中文'], ['version'])
        for probe in (True, False):
            with self.subTest(probe=probe), patch.object(tool, 'click', side_effect=[None, OSError('click failed')]):
                self.events.clear()
                tool.do_fill(plan, c, 42, self.logs.append, probe=probe, choose_version=True,
                             version_row=2, confirm_page=lambda _: True)
                self.assertIn('版本操作中断', self.logs[-1])
                self.assertFalse(any(event in ('clipboard', 'keys') for event, _ in self.events))

    def test_stop_during_version_probe_never_selects_or_sends_cleanup_keys(self):
        c = calibration()
        c['version_selector'] = {'dropdown': [.5, .25], 'options': {'2': [.5, .38]}}
        plan = tool.build_plan({'version': {'简体中文': 'test'}}, ['简体中文'], ['version'])
        def move(x, y):
            self.events.append(('move', (x, y)))
            if (x, y) == (.5, .38):
                self.stop = True
        with patch.object(tool, 'move_to', side_effect=move):
            tool.do_fill(plan, c, 42, self.logs.append, probe=True, choose_version=True,
                         version_row=2, should_stop=lambda: self.stop, confirm_page=lambda _: True)
        self.assertFalse(any(event in ('keys', 'clipboard') for event, _ in self.events))
        self.assertNotIn(('click', (.5, .38)), self.events)

    def test_keep_current_version_does_not_require_selector_or_open_dropdown(self):
        plan = tool.build_plan({'version': {'简体中文': 'Update'}}, ['简体中文'], ['version'])
        tool.do_fill(plan, calibration(), 42, self.logs.append, choose_version=True,
                     version_row=0, confirm_page=lambda _: True)
        clicks = [point for event, point in self.events if event == 'click']
        self.assertEqual(len(clicks), 3)  # edit, text, confirm
        self.assertIn(('clipboard', 'Update'), self.events)

    def test_missing_version_target_is_rejected_before_any_input(self):
        plan = tool.build_plan({'version': {'简体中文': 'Update'}}, ['简体中文'], ['version'])
        with self.assertRaises(tool.CalibrationError):
            tool.do_fill(plan, calibration(), 42, self.logs.append, choose_version=True,
                         version_row=3, confirm_page=lambda _: True)
        self.assertEqual(self.events, [])

    def test_accepted_wheel_without_page_confirmation_never_moves_to_cells(self):
        plan = tool.build_plan({'name': {tool.LANGS[9]: 'Test'}}, [tool.LANGS[9]], ['name'])
        tool.do_fill(plan, calibration(), 42, self.logs.append, tr=lambda cn, en: en,
                     clipboard_owner=123, confirm_page=lambda _: False)
        self.assertEqual([e[1] for e in self.events if e[0] == 'click'], [])
        self.assertEqual([e[1] for e in self.events if e[0] == 'move'], [(.3, .44)])
        self.assertFalse(any(e[0] == 'clipboard' for e in self.events))
        self.assertIn('Page not confirmed', self.logs[-1])


class DataTests(unittest.TestCase):
    def test_game_window_detection_uses_english_title_and_game_process(self):
        def detect(title, image):
            windows = {41: ("Genshin Impact", "browser.exe"), 42: (title, image)}

            def get_title(hwnd, buffer, size):
                buffer.value = windows[hwnd][0]
                return len(buffer.value)

            def get_rect(hwnd, pointer):
                rect = ctypes.cast(pointer, ctypes.POINTER(tool.wintypes.RECT)).contents
                rect.right = 1920 if hwnd == 41 else 1280
                rect.bottom = 1080 if hwnd == 41 else 720
                return True

            def enumerate_windows(callback, _):
                for hwnd in windows:
                    callback(hwnd, 0)
                return True

            with patch.object(tool.user32, "EnumWindows", side_effect=enumerate_windows), \
                 patch.object(tool.user32, "IsWindowVisible", return_value=True), \
                 patch.object(tool.user32, "GetWindowTextLengthW", side_effect=lambda hwnd: len(windows[hwnd][0])), \
                 patch.object(tool.user32, "GetWindowTextW", side_effect=get_title), \
                 patch.object(tool.user32, "GetClientRect", side_effect=get_rect), \
                 patch.object(tool, "window_class", return_value="UnityWndClass"), \
                 patch.object(tool, "window_pid", side_effect=lambda hwnd: hwnd), \
                 patch.object(tool, "process_image_name", side_effect=lambda pid: windows[pid][1]):
                return tool.find_game_window()

        self.assertEqual(detect("Genshin Impact", "genshinimpact.exe"), 42)
        self.assertEqual(detect("Genshin Impact", None), 42)
        self.assertEqual(detect("原神", "yuanshen.exe"), 42)
        self.assertIsNone(detect("Browser — Genshin Impact", "browser.exe"))

    def test_shared_calibration_reduces_points_and_preserves_full_mode(self):
        self.assertEqual(len(tool.calibration_steps(True)), 9)
        self.assertEqual(len(tool.calibration_steps(False)), 13)
        self.assertEqual(len(tool.calibration_steps(True, True)), 11)
        c = calibration()
        captured = {'top': [.3, .2], 'top_next': [.3, .26], 'notes': [.45, .2],
                    'desc': [.6, .2], 'version': [.85, .21], 'shared_text': [.4, .5],
                    'shared_confirm': [.6, .8], 'bottom': [.3, .4], 'bottom_next': [.3, .46],
                    'version_dropdown': [.5, .3], 'version_option': [.5, .35], 'scroll_point': [.15, .3]}
        result = tool.make_calibration(captured, [962, 564], 144, True, True)
        self.assertEqual(result['dialogs']['notes'], result['dialogs']['version'])
        self.assertEqual(result['version_selector']['option'], [.5, .35])
        self.assertEqual(result['scale'], 1.5)
        english = tool.calibration_steps(True, first_language="English")
        self.assertIn("center of the Stage Name cell in the first row (English)", english[0][2])
        self.assertIn("second row (简体中文)", english[1][2])

    def test_coordinates_at_physical_resolutions_and_dpi(self):
        for size in ((962, 564), (1920, 1080), (2560, 1440)):
            for dpi in (96, 120, 144):
                with patch.object(tool, "geometry", return_value=((100, 200), size, dpi)):
                    self.assertEqual(tool.screen_point((.3, .6), 42), (100 + size[0] * .3, 200 + size[1] * .6))
        c = calibration()
        tool.validate_calibration(c)
        # Lower-page anchor differs; no 15-row accumulation.
        self.assertAlmostEqual(tool.cell_point(c, 9, "version")[1], .41)

    def test_all_header_languages_shuffled_and_template_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "template.xlsx"
            for english in (False, True):
                tool.write_template(source, english=english)
                data = tool.read_table(source, log=lambda _: None)
                example_language = "English" if english else "简体中文"
                self.assertTrue(all(set(data[key]) == {example_language} for key, _ in tool.FIELDS))
            self.assertEqual(tool._xlsx_sheets(source), ["Stage Info"])
            with zipfile.ZipFile(source) as book:
                parts = {n: book.read(n) for n in book.namelist()}
            root = ET.fromstring(parts['xl/worksheets/sheet1.xml'])
            ns = {'s': tool._XLSX_NS['main']}
            # Replace headers in a shuffled order and populate every language on row 2.
            header = root.find('s:sheetData/s:row', ns)
            for cell, lang in zip(list(header)[1:], reversed(tool.LANGS)):
                cell.find('s:is/s:t', ns).text = lang
            row = root.find("s:sheetData/s:row[@r='2']", ns)
            for cell in list(row)[1:]:
                row.remove(cell)
            for col in range(2, 17):
                c = ET.SubElement(row, '{%s}c' % ns['s'], r=f'{chr(64 + col)}2', t='inlineStr')
                ET.SubElement(ET.SubElement(c, '{%s}is' % ns['s']), '{%s}t' % ns['s']).text = f'Example {col}'
            parts['xl/worksheets/sheet1.xml'] = ET.tostring(root)
            shuffled = Path(folder) / 'shuffled.xlsx'
            with zipfile.ZipFile(shuffled, 'w') as book:
                for name, content in parts.items():
                    book.writestr(name, content)
            data = tool.read_table(shuffled, log=lambda _: None)
            self.assertEqual(set(data['name']), set(tool.LANGS))
            self.assertEqual(data['name'][tool.LANGS[-1]], 'Example 2')

    def test_missing_presets_and_calibration_prompt_before_game_access(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            for probe in (False, True):
                app = Mock(busy=False)
                app.first_language.get.return_value = "简体中文"
                app.tr = lambda cn, en: cn
                with patch.object(tool, 'CALIB_FILE', str(Path(folder) / 'not-created.json')), \
                     patch.object(tool, 'PRESET_DIR', Path(folder)):
                    tool.App.start(app, probe=probe)
                app.game.assert_not_called()
                app.error.assert_called_once()
                message = str(app.error.call_args.args[0])
                self.assertIn('③', message)
                self.assertNotIn('No such file', message)

    def test_english_first_reuses_saved_coordinates(self):
        import json

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "text-calib.json"
            original = calibration()
            path.write_text(json.dumps(original), encoding="utf-8")
            with patch.object(tool, "CALIB_FILE", str(path)):
                english, from_preset = tool.load_text_calibration("English")
            self.assertFalse(from_preset)
            self.assertEqual(english["top"], original["top"])
            self.assertEqual(tool.validate_calibration(english)[:3], ("English", "简体中文", "繁體中文"))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), original)

    def test_old_custom_option_is_preserved_and_new_rows_use_a_complete_preset_pair(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'saved.json'
            saved = calibration()
            saved['version_selector'] = {'dropdown': [.41, .24], 'option': [.42, .52],
                                          'options': {'2': [.42, .38]}}
            path.write_text(json.dumps(saved), encoding='utf-8')
            with patch.object(tool, 'CALIB_FILE', str(path)):
                loaded, _ = tool.load_text_calibration('English')
            self.assertEqual(tool.version_target(loaded, -1), ([.41, .24], [.42, .52]))
            self.assertEqual(tool.version_target(loaded, 2), ([.41, .24], [.42, .38]))
            preset, _ = tool.load_calibration('text.json')
            self.assertEqual(tool.version_target(loaded, 3), tool.version_target(preset, 3))
            self.assertNotEqual(tool.version_target(loaded, 3)[0], [.41, .24])
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), saved)

    def test_clean_install_has_text_and_media_positions(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            with patch.object(tool, "CALIB_FILE", str(folder / "new-calib.json")):
                text_preset, text_from_preset = tool.load_text_calibration("English")
            media_preset, media_from_preset = tool.load_calibration("media.json", folder / "new-media.json")
            self.assertTrue(text_from_preset and media_from_preset)
            self.assertIn("version_selector", text_preset)
            self.assertEqual(tool.validate_calibration(text_preset)[0], "English")
            tool.validate_media_calibration(media_preset, [("cover", 0, ""), ("image", 3, ""), ("video", 0, "")])
            tool.check_preset_size(text_preset, (2560, 1440), lambda cn, en: en)
            with self.assertRaisesRegex(ValueError, "16:9"):
                tool.check_preset_size(text_preset, (1600, 1200), lambda cn, en: en)

    def test_frozen_application_file_uses_exe_not_internal_source(self):
        executable = str(Path(tempfile.gettempdir()) / '便携工具' / '工具.exe')
        with patch.object(tool.sys, 'frozen', True, create=True), patch.object(tool.sys, 'executable', executable):
            self.assertEqual(tool.application_file(), Path(executable).resolve())
        with patch.object(tool.sys, 'frozen', False, create=True):
            self.assertEqual(tool.application_file(), Path(tool.__file__).resolve())

    def test_elevation_relaunch_arguments_for_source_and_frozen(self):
        from unittest.mock import Mock
        for frozen, expected in ((False, ['tool.py', '带 空格']), (True, ['带 空格'])):
            with self.subTest(frozen=frozen):
                run = Mock(return_value=33)
                with patch.object(tool.sys, 'frozen', frozen, create=True), \
                     patch.object(tool.sys, 'argv', ['tool.py', '带 空格']), \
                     patch.object(tool, '_api', side_effect=[lambda: False, run]):
                    with self.assertRaises(SystemExit) as result:
                        tool.elevate()
                self.assertEqual(result.exception.code, 0)
                self.assertEqual(run.call_args.args[3], tool.subprocess.list2cmdline(expected))
                self.assertEqual(run.call_args.args[4], str(tool.APP_DIR))

    def test_empty_history_does_not_read_following_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'template.xlsx'
            tool.write_template(source)
            cells = {(1, 2): '简体中文', (16, 1): '版本更新记录',
                     (17, 1): '说明：可留空', (19, 1): '关卡标签',
                     (20, 1): '控制设备', (20, 2): '键盘鼠标、触屏、手柄'}
            ws = tool._Worksheet('Sheet1', cells, 20, 2)
            with patch.object(tool, '_read_worksheet', return_value=ws):
                data, rows, active = tool.read_table_rows(source, log=lambda _: None)
            self.assertEqual(data['version'], {})
            self.assertEqual((rows, active), ([], 16))
            cells[(18, 2)] = '实际更新说明'
            with patch.object(tool, '_read_worksheet', return_value=ws):
                data, rows, active = tool.read_table_rows(source, log=lambda _: None)
            self.assertEqual(data['version'][tool.LANGS[0]], '实际更新说明')
            self.assertEqual((rows, active), ([18], 18))

    def test_clipboard_uses_full_width_pointer_and_transfers_ownership(self):
        text = '中文 한국어 日本語 😀'
        buffer = ctypes.create_string_buffer(1024)
        with patch.object(tool.kernel32, 'GlobalAlloc', return_value=123), \
             patch.object(tool.kernel32, 'GlobalLock', return_value=ctypes.addressof(buffer)), \
             patch.object(tool.kernel32, 'GlobalUnlock'), \
             patch.object(tool.kernel32, 'GlobalFree') as free, \
             patch.object(tool.user32, 'OpenClipboard', return_value=True) as opened, \
             patch.object(tool.user32, 'EmptyClipboard', return_value=True), \
             patch.object(tool.user32, 'SetClipboardData', return_value=123), \
             patch.object(tool.user32, 'CloseClipboard') as close:
            tool.set_clipboard(text, owner=123)
            opened.assert_called_once_with(123)
            expected = text.encode('utf-16-le') + b'\0\0'
            self.assertEqual(buffer.raw[:len(expected)], expected)
            free.assert_not_called()
            close.assert_called_once()


class WizardTests(unittest.TestCase):
    def test_excel_update_row_applies_on_preview_and_fill_without_mixing_rows(self):
        tool.enable_physical_pixels()
        root = tool.tk.Tk(); root.withdraw()
        app = tool.App(root)
        try:
            with tempfile.TemporaryDirectory() as folder:
                workbook = Path(folder) / 'Update history.xlsx'
                tool.write_template(workbook)
                xml_path = 'xl/worksheets/sheet1.xml'
                with zipfile.ZipFile(workbook) as book:
                    parts = {member: book.read(member) for member in book.namelist()}
                sheet = ET.fromstring(parts[xml_path])
                namespace = '{' + tool._XLSX_NS['main'] + '}'
                sheet_data = sheet.find(namespace + 'sheetData')
                for row_number, values in ((18, {'A': '0.05', 'B': '第二条更新', 'D': 'Second update'}),
                                           (19, {'A': 'Instructions: example only', 'D': 'Example only'}),
                                           (20, {'A': '版本 0.04', 'D': 'Older update'}),
                                           (22, {'A': '关卡标签', 'D': 'Metadata'})):
                    row = ET.SubElement(sheet_data, namespace + 'row', r=str(row_number))
                    for col, value in values.items():
                        cell = ET.SubElement(row, namespace + 'c', r=f'{col}{row_number}', t='inlineStr')
                        inline = ET.SubElement(cell, namespace + 'is')
                        ET.SubElement(inline, namespace + 't').text = value
                parts[xml_path] = ET.tostring(sheet)
                with zipfile.ZipFile(workbook, 'w') as book:
                    for member, content in parts.items():
                        book.writestr(member, content)
                original = workbook.read_bytes()

                app.path.set(str(workbook))
                app.sheet.set(tool._xlsx_sheets(workbook)[0])
                app.preview()
                self.assertEqual(app.update_text_row.get(), '16')
                self.assertTrue(app.previous_update.instate(['disabled']))
                row_controls = app.next_update.master.pack_slaves()
                self.assertEqual(row_controls[row_controls.index(app.next_update) + 1], app.preview_button)
                app.field_vars['version'].set(True)
                app.content.texts['name']['简体中文'] = '临时名称'
                app.version_row.set(4)
                app.next_update.invoke()
                self.assertEqual(app.update_text_row.get(), '18')
                self.assertEqual({cell[1]: cell[-1] for cell in app.current_plan() if cell[2] == 'version'},
                                 {'简体中文': '第二条更新', 'English': 'Second update'})
                self.assertTrue(app.lang_checks[2].instate(['!disabled']))
                panel = tool.ContentPreview(app)
                panel.tree.selection_set(str(panel.rows.index(('English', 'version'))))
                panel.select_item()
                self.assertEqual(panel.editor.get('1.0', 'end-1c'), 'Second update')
                panel.editor.delete('1.0', 'end')
                panel.editor.insert('1.0', 'Reviewed update')
                panel.next_update.invoke()
                self.assertEqual(panel.update_box.get(), '20')
                self.assertEqual(panel.editor.get('1.0', 'end-1c'), 'Older update')
                self.assertEqual(app.update_text_row.get(), '18')
                self.assertEqual(app.content.texts['version']['English'], 'Second update')
                panel.previous_update.invoke()
                self.assertEqual(panel.editor.get('1.0', 'end-1c'), 'Reviewed update')
                panel.window.destroy()
                self.assertEqual(app.update_text_row.get(), '18')
                self.assertEqual(app.content.texts['version']['English'], 'Second update')

                panel = tool.ContentPreview(app)
                index = panel.update_box['values'].index('20')
                panel.update_box.current(index)
                panel.update_box.event_generate('<<ComboboxSelected>>')
                self.assertEqual(panel.use_button.cget('text'), '使用第 20 行')
                self.assertEqual(panel.editor.get('1.0', 'end-1c'), 'Older update')
                panel.editor.delete('1.0', 'end')
                panel.editor.insert('1.0', 'Chosen update')
                panel.use_button.invoke()
                self.assertEqual(app.update_text_row.get(), '20')
                self.assertTrue(app.next_update.instate(['disabled']))
                plan = app.current_plan()
                self.assertEqual([cell[-1] for cell in plan if cell[2] == 'version'], ['Chosen update'])
                self.assertIn('临时名称', [cell[-1] for cell in plan])
                self.assertEqual(app.version_row.get(), 4)
                self.assertEqual(workbook.read_bytes(), original)
                app.previous_update.invoke()
                self.assertEqual(app.update_text_row.get(), '18')
                for invalid in ('0', '18.5', '1', '23'):
                    with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                        app.update_text_row.set(invalid)
                        app.current_plan()
                app.update_text_row.set('20')
                self.assertIn('Older update', [cell[-1] for cell in app.current_plan()])
                app.update_text_row.set('18')
                app.next_update.invoke()
                self.assertEqual(app.update_text_row.get(), '20')
                app.update_text_row.set('')
                self.assertIn('Older update', [cell[-1] for cell in app.current_plan()])
                self.assertEqual(app.update_text_row.get(), '20')
        finally:
            app.close()

    def test_preview_has_native_maximize_and_restores_editor_state(self):
        tool.enable_physical_pixels()
        root = tool.tk.Tk(); root.withdraw()
        app = tool.App(root)
        app.content = tool.ContentSelection({'name': {'简体中文': '原文'}})
        try:
            panel = tool.ContentPreview(app)
            root.update_idletasks()
            get_style = tool._api(tool.user32, 'GetWindowLongW',
                                  [tool.wintypes.HWND, ctypes.c_int], tool.wintypes.LONG)
            hwnd = int(str(panel.window.frame()), 0)
            self.assertTrue(get_style(hwnd, -16) & 0x00010000)  # WS_MAXIMIZEBOX
            panel.editor.delete('1.0', 'end')
            panel.editor.insert('1.0', '预览中的改动')
            size = (panel.window.winfo_width(), panel.window.winfo_height())
            panel.window.state('zoomed')
            root.update_idletasks()
            self.assertEqual(panel.window.state(), 'zoomed')
            self.assertGreater(panel.window.winfo_height(), size[1])
            panel.window.state('normal')
            root.update_idletasks()
            self.assertEqual((panel.window.winfo_width(), panel.window.winfo_height()), size)
            self.assertEqual(panel.editor.get('1.0', 'end-1c'), '预览中的改动')
            self.assertEqual(root.grab_current(), panel.window)
            panel.apply()
            self.assertIsNone(root.grab_current())
            self.assertEqual(app.content.texts['name']['简体中文'], '预览中的改动')
        finally:
            app.close()

    def test_content_preview_cancel_and_apply_match_the_next_fill_plan(self):
        tool.enable_physical_pixels()
        root = tool.tk.Tk(); root.withdraw()
        app = tool.App(root)
        original = {'name': {'简体中文': '原始名称'}, 'version': {'简体中文': 'v1\n含 空格'}}
        try:
            app.path.set('local.xlsx'); app.sheet.set('Stage')
            app.content_source = ('local.xlsx', 'Stage')
            app.content = tool.ContentSelection(original)
            app.field_vars['version'].set(True)
            panel = tool.ContentPreview(app)
            panel.editor.delete('1.0', 'end'); panel.editor.insert('1.0', '取消的修改')
            panel.commit(); panel.window.destroy()
            self.assertEqual(app.current_plan()[0][-1], '原始名称')
            panel = tool.ContentPreview(app)
            panel.editor.delete('1.0', 'end'); panel.editor.insert('1.0', '本次名称')
            panel.commit()
            version_index = panel.rows.index(('简体中文', 'version'))
            panel.tree.selection_set(str(version_index)); panel.select_item()
            panel.enabled.set(False); panel.commit()
            panel.apply()
            self.assertEqual([cell[-1] for cell in app.current_plan()], ['本次名称'])
            self.assertEqual(original['name']['简体中文'], '原始名称')
            self.assertEqual(original['version']['简体中文'], 'v1\n含 空格')
            app.ui_language.set('English'); app.translate_ui()
            self.assertEqual(app.version_row.get(), 1)
            self.assertEqual(app.version_box.get(), 'Dropdown row 1')
        finally:
            app.close()

    def test_recapturing_one_version_row_preserves_table_other_rows_and_old_target(self):
        import json
        tool.enable_physical_pixels()
        root = tool.tk.Tk(); root.withdraw()
        app = tool.App(root)
        c = calibration()
        c['version_selector'] = {'dropdown': [.5, .25], 'option': [.5, .34],
                                 'options': {'1': [.5, .34], '2': [.5, .38]}}
        try:
            with tempfile.TemporaryDirectory() as folder, \
                 patch.object(tool, 'CALIB_FILE', str(Path(folder) / 'calib.json')), \
                 patch.object(tool, 'geometry', return_value=((0, 0), (962, 564), 96)), \
                 patch.object(app, 'log_geometry'):
                wizard = tool.VersionCalibrationWizard(app, 42, c, 3)
                self.assertEqual(len(wizard.steps), 2)
                wizard.captured = {'version_dropdown': [.5, .25], 'version_option_3': [.5, .42]}
                wizard.save()
                if not Path(tool.CALIB_FILE).exists():
                    self.fail(wizard.status.cget('text'))
                saved = json.loads(Path(tool.CALIB_FILE).read_text(encoding='utf-8'))
                self.assertEqual(saved['top'], c['top'])
                self.assertEqual(saved['dialogs'], c['dialogs'])
                self.assertEqual(saved['version_selector']['option'], [.5, .34])
                self.assertEqual(saved['version_selector']['options']['1'], [.5, .34])
                self.assertEqual(saved['version_selector']['options']['3'], [.5, .42])
        finally:
            app.close()

    def test_back_cancels_pending_capture_and_keeps_recorded_points(self):
        tool.enable_physical_pixels()
        root = tool.tk.Tk()
        root.withdraw()
        app = tool.App(root)
        try:
            with patch.object(tool, 'geometry', return_value=((0, 0), (962, 564), 96)):
                wizard = tool.CalibrationWizard(app, 42, resume=False)
                wizard.captured['top'] = (.3, .2)
                wizard.go(1)
                wizard.capture()
                old = wizard.generation
                wizard.go(0)
                self.assertIsNone(wizard.pending)
                self.assertEqual(wizard.index, 0)
                wizard.countdown(0, 1, old)
                self.assertNotIn('top_next', wizard.captured)
                self.assertIn('top', wizard.captured)
                self.assertTrue(wizard.next.instate(['!disabled']))
                wizard.close()
        finally:
            app.close()

    def test_bad_bottom_spacing_is_rejected_at_capture(self):
        tool.enable_physical_pixels()
        root = tool.tk.Tk(); root.withdraw()
        app = tool.App(root)
        try:
            with patch.object(tool, 'geometry', return_value=((0, 0), (962, 564), 96)), \
                 patch.object(tool, 'cursor_pos', return_value=(289, 293)):
                wizard = tool.CalibrationWizard(app, 42, resume=False)
                wizard.captured = tool.restore_captured(calibration(), True, False)
                index = next(i for i, step in enumerate(wizard.steps) if step[0] == 'bottom_next')
                wizard.go(index)
                previous = wizard.captured['bottom_next']
                wizard.countdown(0, index, wizard.generation)
                self.assertEqual(wizard.index, index)
                self.assertEqual(wizard.captured['bottom_next'], previous)
                self.assertIn('Deutsch', str(wizard.status.cget('text')))
                wizard.close()
        finally:
            app.close()


class RegressionTests(unittest.TestCase):
    def test_adjacent_row_check_identifies_the_bad_step(self):
        with self.assertRaises(tool.CalibrationError) as raised:
            tool.validate_row_spacing('bottom', (.3, .8), .1, 6, (1920, 1080))
        self.assertEqual(raised.exception.step, 'bottom_next')
        self.assertIn('Deutsch', raised.exception.cn)

    def test_cell_outside_table_stops_even_if_inside_window(self):
        data = calibration()
        data['cells']['version'][1] = .95
        with self.assertRaises(tool.Stopped):
            tool.checked_cell_point(data, 0, 'version')

    def test_legacy_bottom_is_not_reused(self):
        old = calibration(); old['schema'] = 2
        old['bottom']['row'] *= 2
        captured = tool.restore_captured(old, True, False)
        self.assertIn('top', captured)
        self.assertNotIn('bottom', captured)
        self.assertNotIn('bottom_next', captured)
        with self.assertRaises(tool.CalibrationError):
            tool.validate_calibration(old)

    def test_sendinput_structure_and_rejected_input(self):
        self.assertEqual(ctypes.sizeof(tool.INPUT), 40 if ctypes.sizeof(ctypes.c_void_p)==8 else 28)
        def send(count, pointer, size):
            packet = ctypes.cast(pointer, ctypes.POINTER(tool.INPUT)).contents
            self.assertEqual(packet.type, 0)
            self.assertEqual(packet.data.mi.dwFlags, 0x0800)
            self.assertEqual(packet.data.mi.mouseData, (-120) & 0xFFFFFFFF)
            self.assertEqual(size, ctypes.sizeof(tool.INPUT))
            return 1
        with patch.object(tool.user32, 'SendInput', side_effect=send):
            tool.scroll_notch(-1)
        with patch.object(tool.user32, 'SendInput', return_value=0):
            with self.assertRaises(tool.ScrollRejected):
                tool.scroll_notch(1)


if __name__ == '__main__':
    unittest.main()
