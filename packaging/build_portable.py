"""Build a Windows x64 onedir ZIP. Run with the dedicated build venv Python."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
NAME = '千星奇域-预览信息-一键填写'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--work', type=Path, default=ROOT / 'build')
    parser.add_argument('--calibration-dir', type=Path, help='Explicitly authorized calibration files to include')
    args = parser.parse_args()
    source = ROOT / f'{NAME}.py'
    import ast
    tree = ast.parse(source.read_text(encoding='utf-8'))
    version = next(ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'APP_VERSION' for t in node.targets))
    output, work = args.output.resolve(), args.work.resolve()
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    package = output / NAME
    # Do not overwrite old packages or personal calibration files.
    if package.exists():
        raise SystemExit(f'Output already exists: {package}; use a fresh output directory.')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--onedir', '--windowed',
                    '--noupx', '--name', NAME, '--manifest', str(ROOT / 'packaging/windows.manifest'),
                    '--distpath', str(output), '--workpath', str(work / 'pyinstaller'),
                    '--specpath', str(work), str(source)], check=True)
    for file in ('README.md', 'LICENSE', 'CHANGELOG.md'):
        shutil.copy2(ROOT / file, package / file)
    (package / '模板').mkdir()
    shutil.copy2(ROOT / '模板/多语言填写模板.xlsx', package / '模板/多语言填写模板.xlsx')
    (package / '使用说明.txt').write_text(
        f'{NAME} v{version} · Windows 10/11 x64 便携版\n\n'
        f'1. 完整解压 ZIP 到你自己的文件夹。\n2. 双击 {NAME}.exe。\n'
        '3. 首次启动如弹出管理员权限提示，请选择“是”。\n'
        '4. 不需要安装 Python、Excel 或其他运行库。\n\n'
        '请保留 _internal 文件夹，不能只复制 exe。\n'
        '校准文件保存在 exe 旁边。更新前保留你自己的三个 calib JSON 文件。\n'
        '完整步骤见 README.md。F9 随时停止，游戏最终“提交”由你手动点击。\n'
        '本版本已由使用者真机测试通过；使用前仍请在自己的游戏中核对位置。\n', encoding='utf-8-sig')
    authorized_calibration = set()
    if args.calibration_dir:
        details = []
        for name in ('多语言填选-calib.json', '多语言填选-calib-draft.json', '多语言填选-media-calib.json'):
            original = args.calibration_dir.resolve() / name
            if not original.is_file():
                continue
            data = json.loads(original.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not data.get('size') or not data.get('dpi'):
                raise ValueError(f'Invalid calibration: {name}')
            shutil.copy2(original, package / name)
            authorized_calibration.add(name)
            details.append(f'{name}：客户区 {data["size"][0]}×{data["size"][1]}，DPI {data["dpi"]}，缩放 {data["dpi"] / 96:.0%}。')
        if '多语言填选-calib.json' not in authorized_calibration:
            raise ValueError('A saved text calibration is required when --calibration-dir is used')
        (package / '校准说明.txt').write_text('此包经使用者授权，附带其最新校准。\n\n' + '\n'.join(details) +
            '\n\n使用前先点④核对；媒体使用“核对媒体位置”。布局、分辨率或缩放不同时请重新校准。\n'
            '这些坐标来自已实测环境，不代表所有电脑都已验证。更新时保留你自己的校准数据。\n', encoding='utf-8-sig')
    licenses = package / 'licenses'
    licenses.mkdir()
    shutil.copy2(Path(sys.base_prefix) / 'LICENSE.txt', licenses / 'Python-LICENSE.txt')
    dist = importlib.metadata.distribution('pyinstaller')
    copying = next(f for f in dist.files if str(f).endswith('licenses/COPYING.txt'))
    shutil.copy2(dist.locate_file(copying), licenses / 'PyInstaller-COPYING.txt')
    # The Tcl/Tk hook includes its data trees; retain any license shipped by CPython.
    for folder in (Path(sys.base_prefix) / 'tcl').glob('*'):
        for leaf in ('license.terms', 'license.terms.txt'):
            if (folder / leaf).is_file():
                shutil.copy2(folder / leaf, licenses / f'{folder.name}-{leaf}')
    manifest = {'version': version, 'platform': 'Windows x64',
                'pyinstaller': importlib.metadata.version('pyinstaller'), 'files': []}
    for path in sorted(package.rglob('*')):
        if path.is_file():
            relative = path.relative_to(package).as_posix()
            if ('calib' in relative.lower() and relative not in authorized_calibration) or path.suffix.lower() in ('.gil', '.gia'):
                raise RuntimeError(f'Private file in package: {relative}')
            manifest['files'].append({'path': relative, 'size': path.stat().st_size,
                                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    (package / '文件校验.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    archive = output / f'{NAME}-v{version}-Windows-x64-便携版.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as book:
        for path in sorted(package.rglob('*')):
            if path.is_file():
                book.write(path, path.relative_to(output))
    print(json.dumps({'zip': str(archive), 'bytes': archive.stat().st_size,
                      'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
