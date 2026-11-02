"""Inspect local build artifacts and produce a clean, portable source ZIP."""
import ast
import hashlib
import json
from pathlib import Path
import tarfile
import tomllib
import zipfile

root = Path(__file__).resolve().parents[1]
dist = root / 'dist'
version = tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
wheel = dist/f'nonebot_plugin_soruto_ai-{version}-py3-none-any.whl'
sdist = dist/f'nonebot_plugin_soruto_ai-{version}.tar.gz'
with zipfile.ZipFile(wheel) as archive:
    names = set(archive.namelist())
    for asset in ('system_prompt.md','ngwords.txt'):
        assert f'nonebot_plugin_soruto_ai/{asset}' in names
        assert archive.read(f'nonebot_plugin_soruto_ai/{asset}')
    assert not any('.testdeps' in name or 'nonebot_plugin_maimai/' in name for name in names)
    installed = root / '.validation' / f'installed-{version}'
    for member in archive.infolist():
        target = (installed / member.filename).resolve()
        assert target.is_relative_to(installed.resolve())
    archive.extractall(installed)
with tarfile.open(sdist) as archive:
    names = [member.name for member in archive.getmembers()]
    for suffix in ('/.env.example','/UPSTREAM.md','/docs/方案设计.md','/tests/test_native.py','/constraints/ubuntu-py311-fastapi0115.txt'):
        assert any(name.endswith(suffix) for name in names), suffix

for path in (root/'nonebot_plugin_soruto_ai').rglob('*.py'):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(item.name.split('.')[0] not in {'astrbot','telegram','nonebot_plugin_maimai'} for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split('.')[0] not in {'astrbot','telegram','nonebot_plugin_maimai'}

excluded = {'.testdeps','.validation','build','dist','__pycache__','.pytest_cache'}
source_roots = {'nonebot_plugin_soruto_ai','tests','docs','scripts','constraints'}
source_root_files = {'.env.example','.gitignore','.gitattributes','README.md','UPSTREAM.md','pyproject.toml','MANIFEST.in'}
source_zip = dist/f'nonebot-plugin-soruto-ai-{version}-source.zip'
with zipfile.ZipFile(source_zip,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob('*')):
        parts = path.relative_to(root).parts
        if parts[0] not in source_roots and path.relative_to(root).as_posix() not in source_root_files:
            continue
        if path.is_file() and not any(part in excluded or part.endswith('.egg-info') for part in parts):
            assert path.name != '.env'
            archive.write(path,Path(root.name)/path.relative_to(root))
records = {path.name:{'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
           for path in (wheel,sdist,source_zip)}
(dist/'checksums.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
print(json.dumps({'package_check':'passed','files':records},ensure_ascii=False))
