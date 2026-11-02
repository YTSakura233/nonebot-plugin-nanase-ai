import contextlib
from pathlib import Path
import runpy

import setuptools.build_meta as backend

root = Path(__file__).resolve().parents[1]
assert Path.cwd().resolve() == root, 'Run this script from the independent plugin directory'
validation = root/'.validation'
validation.mkdir(exist_ok=True)
with (validation/'build.log').open('w',encoding='utf-8') as log, contextlib.redirect_stdout(log):
    source = backend.build_sdist('dist')
    wheel = backend.build_wheel('dist')
print(f'BUILD_OK {source} {wheel}')
runpy.run_path(str(root/'scripts'/'package_check.py'),run_name='__main__')
