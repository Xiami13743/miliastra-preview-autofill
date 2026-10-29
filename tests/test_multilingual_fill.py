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

    def test_accepted_wheel_without_page_confirmation_never_moves_to_cells(self):
        plan = tool.build_plan({'name': {tool.LANGS[9]: 'Test'}}, [tool.LANGS[9]], ['name'])
        tool.do_fill(plan, calibration(), 42, self.logs.append, tr=lambda cn, en: en,
                     clipboard_owner=123, confirm_page=lambda _: False)
        self.assertEqual([e[1] for e in self.events if e[0] == 'click'], [])
        self.assertEqual([e[1] for e in self.events if e[0] == 'move'], [(.3, .44)])
        self.assertFalse(any(e[0] == 'clipboard' for e in self.events))
        self.assertIn('Page not confirmed', self.logs[-1])


class DataTests(unittest.TestCase):
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
                self.assertTrue(all(tool.LANGS[0] in data[key] for key, _ in tool.FIELDS))
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
