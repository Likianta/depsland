"""
FIXME: not ready on macos and linux.
"""
from sys import platform
from textwrap import dedent

from lk_utils import dumps
from lk_utils import fs

from ...manifest import T
from ...manifest import load_manifest
from ...utils import bat_2_exe


def build(manifest_file: str, gen_exe: bool = True) -> None:
    """
    what does this function do:
        - create a dist folder
        - create a launcher (exe or bat)
    """
    manifest = load_manifest(manifest_file)
    
    dir_i = manifest['start_directory']
    dir_o = '{}/dist/{}-{}'.format(
        dir_i, manifest['appid'], manifest['version']
    )
    fs.make_dirs(dir_o)
    
    if platform == 'darwin':  # TEST
        from ...utils.gen_app import gen_app
        gen_app(manifest, f'{dir_o}/{manifest["name"]}.app')
    elif platform == 'win32':
        _create_bat(manifest, f'{dir_o}/launcher.bat')
        
        if gen_exe:
            bat_2_exe(
                f'{dir_o}/launcher.bat',
                f'{dir_o}/launcher.exe',
                icon=manifest['launcher']['icon'],  # noqa
                remove_bat=True
            )
    else:
        raise NotImplementedError
    
    print(':t', 'build done. see result in "dist/{}-{}"'.format(
        manifest['appid'], manifest['version']
    ))


def _create_bat(manifest: T.Manifest, file: str) -> None:
    command = dedent('''
        @echo off
        set PYTHONPATH={app_dir};{pkg_dir}
        {py} %*
    ''').strip().format(
        app_dir=r'{}\{}\{}'.format(
            r'%DEPSLAND%\apps', manifest['appid'], manifest['version']
        ),
        pkg_dir=r'{}\.venv\{}'.format(
            r'%DEPSLAND%\apps', manifest['appid']
        ),
        py=r'"%DEPSLAND%\python\python.exe"',
    )
    dumps(command, file)
