# Miliastra Preview Autofill

[![简体中文](./assets/readme-zh.svg)](./README.md) [![English](./assets/readme-en.svg)](./README.en.md)

Fill the multilingual preview fields of a Miliastra Wonderland stage from an Excel workbook on Windows.

1. Download the Windows x64 ZIP from [Releases](https://github.com/Xiami13743/miliastra-preview-autofill/releases/latest). Extract the whole ZIP and run `千星奇域-预览信息-一键填写.exe` next to its `_internal` folder. Approve the Windows administrator prompt if it appears. Choose **English** in the **Language** menu at the top right.
2. Click **Export Excel Template**. Replace the examples with your own stage info under the appropriate language headers. The input rows are 2 for **Stage Name**, 9 for **Gameplay Details**, 12 for **Stage Description**, and 16 for **Update Log**. Clear the Update Log example for a first release. Save the workbook and use **① Open Filled Excel** to load it. Select the worksheet and the fields and languages you want to fill. Open **Select / Preview** next to **Next update** to review, deselect, or edit individual entries. Use the title-bar maximize button for more space. Click **Use this content** to apply your choices in the tool. Reopening the workbook, switching worksheets, or closing the tool resets these edits.
3. In Genshin Impact, open **Stage Details > Multilanguage Settings**. If any languages are missing, use **Add Language > Select All > OK** so the table contains all 15. Scroll to the top and select the language marked **Default** in the tool's **Stage Default Language (Row 1)** menu. The tool moves that language to the first row and calculates the positions of the other rows. For an English default, the first three rows are English, Simplified Chinese, and Traditional Chinese.
4. Click **④ Check positions** to verify the order and pointer targets in both views. The tool uses your saved positions or its built-in preset. If a target is off, open **③ Calibrate**. Click **Capture** in the tool, move the pointer to the **center of the indicated cell, icon, or OK button** within five seconds, and hold it there. Open the editor in the game before you capture its text box or **OK** button.
5. Click **⑤ Fill all** after checking the targets. Review the resulting text in Genshin Impact and submit it yourself. Press **F9** to stop.

For the first release of a stage, leave **Update Log** unchecked. For a later update, select it. **Update text row (Excel)** shows the detected row, usually 16 in the template. Click **Previous update** or **Next update** to jump between rows with update text, or type a worksheet row number. The tool reads the selected row's language columns and skips blank cells. Changing rows reloads the update text and keeps your edits to other fields. Switching worksheets selects the first update in that sheet.

The preview has its own row menu and previous and next buttons. Click **Use row N** to apply the chosen row and your preview edits to the main window. Click **Cancel** to return to the previous selection.

Choose the **Game version** separately. For example, send **Excel row 18 → Dropdown row 2**. The four dropdown rows follow the visible options from top to bottom. **④ Check positions** opens the Update Log editor at the end and leaves the pointer on the chosen option for review. Click the editor's **×** to return to the language list before **⑤ Fill all**. If the position is off, **Recapture version positions** records the dropdown button and the chosen row.

**Keep current version** fills the update text without changing the version. **Original calibrated option** uses the single target recorded by an older tool. A custom position for the selected row takes priority. Otherwise, the tool uses the built-in dropdown and option together, without mixing custom and preset points. Spaces and line breaks count toward the preview's character totals; the tool does not shorten your text.

The text and media presets come from v0.3.6 at a client area of 1920×1080 and 150% Windows scaling. They use proportional positions for a 16:9 game layout. The same text calibration applies when the default language changes. Keep your saved calibration files next to the executable when upgrading. Check the positions again after resizing the window or changing display scaling.

The first four dropdown positions are based on a player's screenshot. Excel row selection, content preview, and the position check in v0.3.9 have local regression coverage. Use **④** to verify the position in the game.

For cover images, screenshots or a video, close the multilingual table and scroll the right panel all the way down. Open **Cover / Images / Video** in the tool and select your files. Click **Check positions**, adjust with **Calibrate media** if needed, then click **Fill media files** and check the thumbnails in the game.
