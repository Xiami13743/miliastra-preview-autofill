"""Media regression checks; all native input is mocked, no game interaction."""
import ctypes
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_multilingual_fill import tool


def calibration():
    return {"schema": 1, "size": [1920, 1080], "dpi": 144,
            "points": {"cover": [.3, .4], "image_first": [.53, .57],
                       "image_next": [.62, .57], "video": [.53, .77]}}


class MediaPlanTests(unittest.TestCase):
    def test_pasted_paths_quotes_multiple_files_and_row_limits(self):
        with tempfile.TemporaryDirectory() as folder:
            png = Path(folder) / '图片 1.png'; png.write_bytes(b'\x89PNG\r\n\x1a\n' + b'x')
            jpg = Path(folder) / '图片 2.jpg'; jpg.write_bytes(b'\xff\xd8\xff' + b'x')
            incoming = tool.pasted_path_lines(f'"{png}"\r\n "{jpg}" \r\n')
            self.assertEqual(incoming, [str(png), str(jpg)])
            current = ['existing'] * 6
            result = tool.merge_pasted_media(current, 2, incoming)
            self.assertEqual(result[2:4], [str(png.resolve()), str(jpg.resolve())])
            self.assertEqual(result[:2] + result[4:], ['existing'] * 4)
            self.assertEqual(current, ['existing'] * 6)
            for index in (0, 4, 5):
                with self.assertRaises(ValueError):
                    tool.merge_pasted_media(current, index, incoming)
            bad = Path(folder) / 'bad.mp4'; bad.write_bytes(b'video')
            with self.assertRaises(ValueError):
                tool.merge_pasted_media(current, 2, [str(png), str(bad)])

    def test_cover_optional_images_compact_and_video_last(self):
        with tempfile.TemporaryDirectory() as folder:
            png = Path(folder) / '封面.png'; png.write_bytes(b'\x89PNG\r\n\x1a\n' + b'X' * 20)
            jpg = Path(folder) / '展示图.jpg'; jpg.write_bytes(b'\xff\xd8\xff' + b'X' * 20)
            video = Path(folder) / '视频.mp4'; video.write_bytes(b'video content')
            plan = tool.media_plan(str(png), ['', str(jpg), '', str(png)], str(video))
            self.assertEqual([(k, i) for k, i, _ in plan], [('cover', 0), ('image', 0), ('image', 1), ('video', 0)])
            self.assertTrue(all(Path(p).is_absolute() for _, _, p in plan))
            self.assertEqual(tool.media_plan(video=str(video)), [('video', 0, str(video.resolve()))])
            self.assertEqual(len(tool.media_plan(images=[str(png)])), 1)

    def test_bad_media_rejected_before_any_input(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / 'fake.png'; bad.write_bytes(b'not an image')
            with self.assertRaises(ValueError):
                tool.media_plan(cover=str(bad))
            bad.write_bytes(b'\x89PNG\r\n\x1a\n' + b'0' * (5 * 1024 * 1024))
            with self.assertRaises(ValueError):
                tool.media_plan(images=[str(bad)])
            video = Path(folder) / 'large.mp4'
            with video.open('wb') as stream:
                stream.truncate(300 * 1024 * 1024 + 1)
            with self.assertRaises(ValueError):
                tool.media_plan(video=str(video))
        with self.assertRaises(ValueError):
            tool.media_plan()
        with self.assertRaises(ValueError):
            tool.media_plan(images=['a'] * 5)

    def test_calibrated_slot_spacing_and_bounds(self):
        data = calibration()
        self.assertAlmostEqual(tool.media_point(data, 'image', 3)[0], .8)
        tool.validate_media_calibration(data, [('image', 3, 'x')])
        data['points']['image_next'] = [.8, .57]
        with self.assertRaises(tool.CalibrationError):
            tool.validate_media_calibration(data, [('image', 3, 'x')])
        data['points']['image_next'] = [.5, .57]
        with self.assertRaises(tool.CalibrationError) as caught:
            tool.media_point(data, 'image', 1)
        self.assertEqual(caught.exception.step, 'image_next')
        del data['points']['video']
        with self.assertRaises(tool.CalibrationError):
            tool.validate_media_calibration(data, [('video', 0, 'x')])


class MediaFlowTests(unittest.TestCase):
    def setUp(self):
        self.logs = []
        self.stop = False
        patches = [patch.object(tool.user32, 'GetForegroundWindow', return_value=42),
                   patch.object(tool.user32, 'IsWindowEnabled', return_value=True),
                   patch.object(tool, 'game_file_dialogs', return_value=[]),
                   patch.object(tool, 'pause', side_effect=lambda seconds, stop: tool.check_stop(stop))]
        for p in patches:
            p.start(); self.addCleanup(p.stop)

    def test_partial_images_run_in_order_without_submit(self):
        plan = [('cover', 0, 'cover.png'), ('image', 0, 'a.png'), ('image', 1, 'b.png'), ('video', 0, 'v.mp4')]
        with patch.object(tool, 'open_media_file') as upload:
            tool.do_media(plan, calibration(), 42, self.logs.append)
            self.assertEqual([c.args[2] for c in upload.call_args_list], ['cover.png', 'a.png', 'b.png', 'v.mp4'])
            self.assertEqual([tuple(c.args[1]) for c in upload.call_args_list], [(.3, .4), (.53, .57), (.62, .57), (.53, .77)])
        self.assertIn('自己点', self.logs[-1])

    def test_failure_stops_remaining_uploads(self):
        with patch.object(tool, 'open_media_file', side_effect=RuntimeError('file picker stayed open')) as upload:
            with self.assertRaises(RuntimeError):
                tool.do_media([('image', 0, 'a.png'), ('image', 1, 'b.png')], calibration(), 42, self.logs.append)
            self.assertEqual(upload.call_count, 1)

    def test_stop_between_files_prevents_next_click(self):
        def upload(*args, **kwargs):
            self.stop = True
        with patch.object(tool, 'open_media_file', side_effect=upload) as mocked:
            with self.assertRaises(tool.Stopped):
                tool.do_media([('image', 0, 'a.png'), ('image', 1, 'b.png')], calibration(), 42, self.logs.append, should_stop=lambda: self.stop)
            self.assertEqual(mocked.call_count, 1)

    def test_probe_only_moves_no_file_dialog(self):
        with patch.object(tool, 'open_media_file') as upload, patch.object(tool, 'move_to') as move, \
             patch.object(tool, 'screen_point', side_effect=lambda pt, hwnd: pt):
            tool.do_media([('image', 0, 'a.png'), ('video', 0, 'v.mp4')], calibration(), 42, self.logs.append, probe=True)
            upload.assert_not_called()
            self.assertEqual(move.call_count, 2)

    def test_existing_dialog_prevents_click(self):
        with patch.object(tool, 'game_file_dialogs', return_value=[99]), patch.object(tool, 'click') as click:
            with self.assertRaises(tool.Stopped):
                tool.open_media_file(42, (.3, .4), 'x.png', lambda: False, 123)
            click.assert_not_called()

    def test_f9_while_opening_picker_prevents_any_paste(self):
        def click_and_stop(*args):
            self.stop = True
        with patch.object(tool, 'click', side_effect=click_and_stop), \
             patch.object(tool, 'screen_point', return_value=(10, 20)), \
             patch.object(tool, 'set_clipboard') as clipboard, patch.object(tool, 'combo') as keys:
            with self.assertRaises(tool.Stopped):
                tool.open_media_file(42, (.3, .4), 'x.png', lambda: self.stop, 123)
            clipboard.assert_not_called()
            keys.assert_not_called()


class NativeDialogTests(unittest.TestCase):
    def test_native_filename_control_ignores_unrelated_edit(self):
        def enumerate_children(hwnd, callback, arg):
            for child in (10, 20):
                callback(child, arg)
            return 1
        with patch.object(tool.user32, 'EnumChildWindows', side_effect=enumerate_children), \
             patch.object(tool, 'window_class', return_value='Edit'), \
             patch.object(tool.user32, 'IsWindowVisible', return_value=True), \
             patch.object(tool.user32, 'GetAncestor', side_effect=lambda h, _: {10: 11, 20: 21}.get(h, 99)), \
             patch.object(tool.user32, 'GetDlgCtrlID', side_effect=lambda h: 0x47c if h == 21 else 0):
            self.assertEqual(tool.filename_edit(99), 20)

    def test_preexisting_game_dialog_filter_only_returns_game_process(self):
        def enumerate_windows(callback, arg):
            for child in (50, 60, 70):
                callback(child, arg)
            return 1
        with patch.object(tool, 'window_pid', side_effect=lambda h: {42: 100, 50: 100, 60: 200, 70: 100}[h]), \
             patch.object(tool.user32, 'EnumWindows', side_effect=enumerate_windows), \
             patch.object(tool.user32, 'IsWindowVisible', return_value=True), \
             patch.object(tool, 'window_class', side_effect=lambda h: '#32770' if h != 70 else 'OtherWindow'):
            self.assertEqual(tool.game_file_dialogs(42), [50])
            self.assertTrue(tool.same_game_process(50, 42))
            self.assertFalse(tool.same_game_process(60, 42))

    def test_new_cross_process_picker_gets_path_and_open_click(self):
        self._run_filename_case(55)

    def test_reused_cross_process_picker_gets_path_and_open_click(self):
        self._run_filename_case(55, reused=True)

    def test_return_to_game_during_picker_close_is_allowed(self):
        self._run_filename_case(55, closing=True)

    def test_reused_picker_hidden_without_destruction_finishes(self):
        self._run_filename_case(55, closing=True, reused=True, hidden=True)

    def test_two_files_can_reuse_the_same_broker_window(self):
        self._run_filename_case(55, closing=True, reused=True, hidden=True, repeats=2)

    def test_wrong_filename_focus_prevents_paste(self):
        self._run_filename_case(66)

    def test_unrelated_foreground_app_never_receives_path(self):
        with patch.object(tool.user32, 'GetForegroundWindow', side_effect=[42, 88]), \
             patch.object(tool.user32, 'IsWindowEnabled', return_value=True), \
             patch.object(tool, 'game_file_dialogs', return_value=[]), \
             patch.object(tool, 'window_pid', side_effect=lambda h: 100 if h == 42 else 200), \
             patch.object(tool, 'window_class', return_value='Notepad'), \
             patch.object(tool.time, 'monotonic', side_effect=[0, 0, 1]), \
             patch.object(tool, 'screen_point', return_value=(10, 20)), \
             patch.object(tool, 'click') as click, patch.object(tool, 'replace_text') as paste:
            with self.assertRaises(tool.Stopped) as caught:
                tool.open_media_file(42, (.3, .4), 'x.png', lambda: False, 123)
            self.assertIn('200', str(caught.exception))
            self.assertEqual(click.call_count, 1)
            paste.assert_not_called()

    def test_new_non_file_dialog_never_receives_path(self):
        with patch.object(tool.user32, 'GetForegroundWindow', side_effect=[42, 99]), \
             patch.object(tool.user32, 'IsWindowEnabled', return_value=True), \
             patch.object(tool, 'game_file_dialogs', return_value=[]), \
             patch.object(tool, 'window_class', return_value='#32770'), \
             patch.object(tool, 'filename_edit', return_value=None), \
             patch.object(tool.time, 'monotonic', side_effect=[0, 0, 11]), \
             patch.object(tool, 'screen_point', return_value=(10, 20)), \
             patch.object(tool, 'pause'), patch.object(tool, 'click') as click, \
             patch.object(tool, 'replace_text') as paste:
            with self.assertRaises(RuntimeError):
                tool.open_media_file(42, (.3, .4), 'x.png', lambda: False, 123)
            self.assertEqual(click.call_count, 1)
            paste.assert_not_called()

    def test_open_button_uses_native_idok_not_cancel(self):
        with patch.object(tool, 'dialog_children', return_value=[20, 21]), \
             patch.object(tool, 'window_class', return_value='Button'), \
             patch.object(tool.user32, 'GetDlgCtrlID', side_effect=lambda h: 1 if h == 21 else 2), \
             patch.object(tool.user32, 'IsWindowVisible', return_value=True), \
             patch.object(tool.user32, 'IsWindowEnabled', return_value=True):
            self.assertEqual(tool.file_open_button(99), 21)

    def _run_filename_case(self, focus_handle, closing=False, reused=False, hidden=False, repeats=1):
        events = []
        def foreground():
            if not events or (closing and events[-1] == ('click', (700, 320))):
                return 42
            return 99
        def rect(hwnd, pointer):
            r = ctypes.cast(pointer, ctypes.POINTER(tool.wintypes.RECT)).contents
            r.left, r.top, r.right, r.bottom = (100, 200, 500, 240) if hwnd == 55 else (600, 300, 800, 340)
            return 1
        def focus(thread, pointer):
            ctypes.cast(pointer, ctypes.POINTER(tool.GUITHREADINFO)).contents.hwndFocus = focus_handle
            return 1
        with patch.object(tool.user32, 'GetForegroundWindow', side_effect=foreground), \
             patch.object(tool.user32, 'IsWindowEnabled', return_value=True), \
             patch.object(tool, 'game_file_dialogs', return_value=[]), \
             patch.object(tool, 'visible_dialogs', return_value=[99] if reused else []), \
             patch.object(tool, 'window_class', side_effect=lambda h: '#32770' if h == 99 else 'UnityWndClass'), \
             patch.object(tool, 'filename_edit', return_value=55), \
             patch.object(tool, 'file_open_button', return_value=77), \
             patch.object(tool, 'window_pid', side_effect=lambda h: 100 if h == 42 else 200), \
             patch.object(tool.user32, 'GetWindowRect', side_effect=rect), \
             patch.object(tool.user32, 'GetGUIThreadInfo', side_effect=focus), \
             patch.object(tool.user32, 'IsWindow', side_effect=([True] if hidden else ([True, False] if closing else [False])) * repeats), \
             patch.object(tool.user32, 'IsWindowVisible', return_value=not hidden), \
             patch.object(tool, 'activate_media_game', side_effect=lambda hwnd, stop, tr: tool.check_stop(stop)) as activate, \
             patch.object(tool, 'screen_point', return_value=(10, 20)), \
             patch.object(tool, 'click', side_effect=lambda *a: events.append(('click', a[:2]))), \
             patch.object(tool, 'pause', side_effect=lambda secs, stop: tool.check_stop(stop)), \
             patch.object(tool, 'set_clipboard', side_effect=lambda text, stop, owner: events.append(('clipboard', text))), \
             patch.object(tool, 'combo', side_effect=lambda *a: events.append(('keys', a))):
            if focus_handle == 55:
                for _ in range(repeats):
                    tool.open_media_file(42, (.3, .4), r'D:\图片\封面.png', lambda: False, 123)
                self.assertEqual(activate.call_count, repeats)
            else:
                with self.assertRaises(tool.Stopped):
                    tool.open_media_file(42, (.3, .4), r'D:\图片\封面.png', lambda: False, 123)
                activate.assert_not_called()
        expected = [('click', (10, 20)), ('click', (300, 220))]
        if focus_handle == 55:
            expected += [('keys', ('ctrl', 'a')), ('clipboard', r'D:\图片\封面.png'), ('keys', ('ctrl', 'v')), ('click', (700, 320))]
        self.assertEqual(events, expected * repeats)


class MediaClipboardTests(unittest.TestCase):
    def test_explorer_files_use_full_width_borrowed_handle(self):
        paths = [r'D:\图片\第一张.png', r'D:\图片\第二张.jpg']
        handle = 0x12345678ABC
        def query(received, index, buffer, count):
            self.assertEqual(received, handle)
            if index == 0xFFFFFFFF:
                return len(paths)
            if buffer is not None:
                buffer.value = paths[index]
            return len(paths[index])
        with patch.object(tool.user32, 'IsClipboardFormatAvailable', return_value=True), \
             patch.object(tool.user32, 'OpenClipboard', return_value=True), \
             patch.object(tool.user32, 'GetClipboardData', return_value=handle), \
             patch.object(tool.shell32, 'DragQueryFileW', side_effect=query), \
             patch.object(tool.user32, 'CloseClipboard') as close, \
             patch.object(tool.kernel32, 'GlobalFree') as free:
            self.assertEqual(tool.clipboard_file_paths(123), paths)
            close.assert_called_once()
            free.assert_not_called()

    def test_too_many_files_still_closes_clipboard(self):
        with patch.object(tool.user32, 'IsClipboardFormatAvailable', return_value=True), \
             patch.object(tool.user32, 'OpenClipboard', return_value=True), \
             patch.object(tool.user32, 'GetClipboardData', return_value=123), \
             patch.object(tool.shell32, 'DragQueryFileW', return_value=5), \
             patch.object(tool.user32, 'CloseClipboard') as close:
            with self.assertRaises(tool.CalibrationError):
                tool.clipboard_file_paths(123)
            close.assert_called_once()


class MediaActivationTests(unittest.TestCase):
    def test_restore_then_activate_then_wait_for_stable_physical_geometry(self):
        order = []
        first = ((0, 0), (962, 564), 144)
        final = ((0, 0), (1920, 1080), 144)
        with patch.object(tool.user32, 'IsIconic', side_effect=[True] + [False] * 5), \
             patch.object(tool.user32, 'ShowWindow', side_effect=lambda hwnd, cmd: order.append(('restore', cmd))), \
             patch.object(tool.user32, 'GetForegroundWindow', side_effect=[88] + [42] * 5), \
             patch.object(tool.user32, 'SetForegroundWindow', side_effect=lambda hwnd: order.append(('activate', hwnd))), \
             patch.object(tool, 'geometry', side_effect=[first] + [final] * 4) as geometry, \
             patch.object(tool, 'pause'):
            self.assertEqual(tool.activate_media_game(42, lambda: False), final)
            self.assertEqual(order, [('restore', 9), ('activate', 42)])
            self.assertEqual(geometry.call_count, 5)

    def test_restore_failure_stops_before_geometry_and_positioning(self):
        with patch.object(tool.user32, 'IsIconic', return_value=True), \
             patch.object(tool.user32, 'ShowWindow'), \
             patch.object(tool.user32, 'GetForegroundWindow', return_value=88), \
             patch.object(tool.user32, 'SetForegroundWindow', return_value=0), \
             patch.object(tool.time, 'monotonic', side_effect=[0, 0, 6]), \
             patch.object(tool, 'geometry') as geometry, patch.object(tool, 'pause'), patch.object(tool, 'click') as click:
            with self.assertRaises(tool.Stopped):
                tool.activate_media_game(42, lambda: False)
            geometry.assert_not_called()
            click.assert_not_called()

    def test_f9_prevents_restore_and_activation(self):
        with patch.object(tool.user32, 'ShowWindow') as show, patch.object(tool.user32, 'SetForegroundWindow') as activate:
            with self.assertRaises(tool.Stopped):
                tool.activate_media_game(42, lambda: True)
            show.assert_not_called()
            activate.assert_not_called()


class MediaWizardTests(unittest.TestCase):
    def test_only_selected_types_add_capture_points_and_back_works(self):
        tool.enable_physical_pixels()
        root = tool.tk.Tk(); root.withdraw()
        app = tool.App(root)
        try:
            with tempfile.TemporaryDirectory() as folder, \
                 patch.object(tool, 'MEDIA_CALIB_FILE', str(Path(folder) / 'media.json')), \
                 patch.object(tool, 'geometry', return_value=((0, 0), (1920, 1080), 144)):
                wizard = tool.MediaCalibrationWizard(app, 42, [('video', 0, 'x.mp4')])
                self.assertEqual([s[0] for s in wizard.steps], ['video'])
                wizard.close()
                wizard = tool.MediaCalibrationWizard(app, 42, [('cover', 0, 'x.png'), ('image', 0, 'a.png'), ('image', 1, 'b.png'), ('video', 0, 'v.mp4')])
                self.assertEqual([s[0] for s in wizard.steps], ['cover', 'image_first', 'image_next', 'video'])
                wizard.captured['cover'] = (.3, .4)
                wizard.go(1); wizard.capture(); generation = wizard.generation
                wizard.go(0); wizard.countdown(0, 1, generation)
                self.assertNotIn('image_first', wizard.captured)
                wizard.close()
                panel = tool.MediaPanel(app)
                app.media_panel = panel
                app.translate_ui()
                panel.window.withdraw()
                app.ui_language.set('English'); app.translate_ui()
                self.assertEqual(panel.window.title(), f'Cover / Images / Video · v{tool.APP_VERSION}')
                self.assertIn(f'v{tool.APP_VERSION}', root.title())
                self.assertIn(f'当前版本：v{tool.APP_VERSION}', app.logbox.get('1.0', 'end'))
                self.assertIn(str(Path(tool.__file__).resolve()), app.logbox.get('1.0', 'end'))
                with patch.object(tool, 'clipboard_file_paths', return_value=['copied.png']), \
                     patch.object(tool, 'merge_pasted_media', return_value=['', '', 'copied.png', '', '', '']):
                    self.assertEqual(panel.paste(2), 'break')
                    self.assertEqual(panel.paths[2].get(), 'copied.png')
                    panel.paths[2].set('')
                    root.update_idletasks()
                    panel.entries[2].event_generate('<<Paste>>')
                    self.assertEqual(panel.paths[2].get(), 'copied.png')
                self.assertEqual(str(panel.entries[2].cget('state')), 'normal')
                self.assertEqual(str(panel.entries[2].cget('justify')), 'right')
                panel.window.deiconify()
                long_path = 'D:/' + '很长的文件夹/' * 30 + '最后的文件名.png'
                panel.paths[2].set(long_path)
                root.update_idletasks()
                root.update()
                left, right = panel.entries[2].xview()
                self.assertGreater(left, 0)
                self.assertEqual(right, 1)
                self.assertEqual(panel.paths[2].get(), long_path)
        finally:
            app.close()


if __name__ == '__main__':
    unittest.main()
