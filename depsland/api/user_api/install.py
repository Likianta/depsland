import os
import typing as t
from textwrap import dedent

from lk_utils import dumps
from lk_utils import fs
from lk_utils import loads

from ... import paths
from ...manifest import T as T0
from ...manifest import compare_manifests
from ...manifest import init_manifest
from ...manifest import init_target_tree
from ...manifest import load_manifest
from ...normalization import normalize_name
from ...normalization import normalize_version_spec
from ...oss import T as T1
from ...oss import get_oss_client
from ...pypi import pypi
from ...utils import bat_2_exe
from ...utils import compare_version
from ...utils import make_temp_dir
from ...utils import ziptool


class T:
    AssetInfo = T0.AssetInfo
    LauncherInfo = T0.Launcher1
    Manifest = T0.Manifest1
    ManifestPypi = t.Dict[str, None]
    Oss = T1.Oss
    Path = str


def main(appid: str) -> t.Optional[T.Path]:
    """
    depsland install <url>
    """
    dir_i: T.Path  # the dir to last installed version (if exists)
    dir_m: T.Path = make_temp_dir()  # a temp dir to store downloaded assets
    dir_o: T.Path  # the dir to the new version
    
    oss = get_oss_client(appid)
    print(oss.path)
    
    # -------------------------------------------------------------------------
    
    def get_manifest_new() -> T.Manifest:
        nonlocal dir_m, oss
        file_i = oss.path.manifest
        file_o = f'{dir_m}/manifest.pkl'
        oss.download(file_i, file_o)
        return load_manifest(file_o)
    
    def get_manifest_old() -> T.Manifest:
        nonlocal dir_i, manifest_new
        dir_i = _get_dir_to_last_installed_version(appid)
        if dir_i:
            return load_manifest(f'{dir_i}/manifest.pkl')
        else:
            print('no previous version found, it may be your first time to '
                  f'install {appid}')
            print('[dim]be noted the first-time installation may consume a '
                  'long time. depsland will try to reduce the consumption in '
                  'the succeeding upgrades/installations.[/]', ':r')
            return init_manifest(manifest_new['appid'], manifest_new['name'])
    
    manifest_new = get_manifest_new()
    manifest_old = get_manifest_old()
    print(':l', manifest_new)
    if _check_update(manifest_new, manifest_old) is False:
        print('no update available', ':v4s')
        return None
    
    # -------------------------------------------------------------------------
    
    def init_dir_o() -> T.Path:
        nonlocal manifest_new
        
        dir_o = '{}/{}/{}'.format(
            paths.project.apps,
            manifest_new['appid'],
            manifest_new['version']
        )
        if os.path.exists(dir_o):
            # FIXME: ask user turn to upgrade or reinstall command.
            raise FileExistsError(dir_o)
        
        manifest_new['start_directory'] = dir_o
        init_target_tree(manifest_new, dir_o)
        return dir_o
    
    dir_o = init_dir_o()
    
    # -------------------------------------------------------------------------
    
    _install_files(manifest_new, manifest_old, oss, dir_m)
    _install_custom_packages(manifest_new, manifest_old, oss)
    _install_dependencies(manifest_new)
    _create_launcher(manifest_new)
    
    fs.move(f'{dir_m}/manifest.pkl', f'{dir_o}/manifest.pkl', True)
    return dir_o


def main2(manifest_new: T.Manifest, manifest_old: T.Manifest) -> None:
    """
    TODO: leave one of `main` and `main2`, remove another one.
        currently `main` has no usage and is little behind of update schedule.
    """
    dir_m = make_temp_dir()
    
    if os.path.exists(d := manifest_new['start_directory'] + '/.oss'):
        print('use local oss server', ':v2')
        oss = get_oss_client(manifest_new['appid'], server='local')
        oss.path.root = d
    else:
        oss = get_oss_client(manifest_new['appid'])
    print(oss.path)
    
    _install_files(manifest_new, manifest_old, oss, dir_m)
    _install_custom_packages(manifest_new, manifest_old, oss)
    _install_dependencies(manifest_new)
    _create_launcher(manifest_new)


def _check_update(
        manifest_new: T.Manifest,
        manifest_old: T.Manifest,
) -> bool:
    return compare_version(
        manifest_new['version'], '>', manifest_old['version']
    )


# -----------------------------------------------------------------------------

def _install_files(
        manifest_new: T.Manifest,
        manifest_old: T.Manifest,
        oss: T.Oss,
        temp_dir: T.Path
) -> None:
    root0 = manifest_old['start_directory']
    root1 = manifest_new['start_directory']
    
    diff = compare_manifests(manifest_new, manifest_old)
    
    def download_from_oss(i: str, m: str, o: str) -> None:
        print(fs.relpath(o, root1))
        oss.download(i, m)
        ziptool.decompress_file(m, o, overwrite=True)
    
    def copy_from_old(i: str, o: str, t: str) -> None:
        # `o` must not be child path of `i`.
        assert not o.startswith(i + '/')
        print('{} -> {}'.format(i, fs.relpath(o, root1)))
        # TODO: shall we use `fs.move` to make it faster?
        if t == 'file':
            fs.copy_file(i, o, True)
        else:
            fs.copy_tree(i, o, True)
    
    for action, relpath, (info0, info1) in diff['assets']:
        if action == 'ignore':
            path0 = f'{root0}/{relpath}'
            path1 = f'{root1}/{relpath}'
            if os.path.exists(path0):
                copy_from_old(path0, path1, info1.type)
                continue
            else:
                print('turn ignore to append action')
                action = 'append'
        
        if action in ('append', 'update'):
            path_i = '{}/{}'.format(oss.path.assets, info1.uid)  # an url
            path_m = fs.normpath('{}/{}.{}'.format(
                # an intermediate file (zip)
                temp_dir, info1.uid,
                'zip' if info1.type == 'dir' else 'fzip'
            ))
            path_o = f'{root1}/{relpath}'  # a file or a directory
            download_from_oss(path_i, path_m, path_o)


def _install_custom_packages(
        manifest_new: T.Manifest,
        manifest_old: T.Manifest,
        oss: T.Oss,
) -> None:
    pypi0: T.ManifestPypi = manifest_old['pypi']
    pypi1: T.ManifestPypi = manifest_new['pypi']
    downloads_dir = paths.pypi.downloads
    
    for name in pypi1:
        if name not in pypi0:
            if not os.path.exists(f'{downloads_dir}/{name}'):
                print('download package (whl) from oss', name)
                oss.download(
                    f'{oss.path.pypi}/{name}',
                    f'{downloads_dir}/{name}',
                )


def _install_dependencies(manifest: T.Manifest, dst_dir: str = None) -> None:
    if dst_dir is None:
        dst_dir = paths.apps.make_packages(
            manifest['appid'], clear_exists=True
        )
    # note: make sure `dst_dir` does exist.
    
    packages = {}
    for name, vspec in manifest['dependencies'].items():
        name = normalize_name(name)
        vspecs = tuple(normalize_version_spec(name, vspec))
        packages[name] = vspecs
    print(':vl', packages)
    
    name_ids = tuple(pypi.install(packages, include_dependencies=True))
    pypi.save_index()
    pypi.linking(name_ids, dst_dir)


def _create_launcher(manifest: T.Manifest) -> None:
    appid = manifest['appid']
    appname = manifest['name']
    version = manifest['version']
    command: str = manifest['launcher']['command']
    
    if command:
        if command.startswith('py '):
            if not command.startswith('py -m '):
                # fix script path to be abspath
                # e.g. 'py src/main.py'
                #   -> 'py %DEPSLAND%/apps/{appid}/.../src/main.py'
                command = 'py {app_dir}/{script}'.format(
                    app_dir=f'%DEPSLAND%/apps/{appid}/{version}',
                    script=command[3:]
                )
            # replace 'py' with python interpreter path.
            command = command.replace(
                'py', r'%DEPSLAND%\python\python.exe', 1
            )
    
    # bat command
    command = dedent('''
        @echo off
        set PYTHONPATH={app_dir};{pkg_dir}
        {cmd} %*
    ''').strip().format(
        app_dir=r'{}\{}\{}'.format(
            r'%DEPSLAND%\apps', appid, version
        ),
        pkg_dir=r'{}\.venv\{}'.format(
            r'%DEPSLAND%\apps', appid
        ),
        cmd=command,
    )
    
    # bat to exe
    dumps(command, bat_file := '{apps}/{appid}/{version}/{appid}.bat'.format(
        apps=paths.project.apps, appid=appid, version=version
    ))
    # TODO: how to add icon, and control whether to show console?
    if not (exe_file := bat_2_exe(bat_file)):
        # user may not have installed `gen-exe`.
        # see detailed error prompt in `bat_2_exe`.
        return
    fs.remove_file(bat_file)
    
    # create shortcuts
    if manifest['launcher']['cli_tool']:
        fs.copy_file(exe_file, '{}/{}.exe'.format(
            paths.project.apps_launcher, appid,
        ))
    if manifest['launcher']['desktop']:
        # https://www.blog.pythonlibrary.org/2010/01/23/using-python-to-create
        # -shortcuts/
        from win32com.client import Dispatch
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortCut('{}/{}.lnk'.format(
            paths.system.desktop, appname
        ))
        shortcut.Targetpath = exe_file
        # shortcut.WorkingDirectory = paths.project.apps
        shortcut.IconLocation = exe_file
        shortcut.save()
        # # fs.copy_file(exe_file, '{}/{}.exe'.format(
        # #     paths.system.desktop, appname
        # # ))
    if manifest['launcher']['start_menu']:
        # WARNING: not tested
        fs.copy_file(exe_file, '{}/{}.exe'.format(
            paths.system.start_menu, appname
        ))


# -----------------------------------------------------------------------------

def _get_dir_to_last_installed_version(appid: str) -> t.Optional[T.Path]:
    dir_ = '{}/{}'.format(paths.project.apps, appid)
    history_file = paths.apps.get_history_versions(appid)
    if os.path.exists(history_file):
        last_ver = loads(history_file)[0]
        out = f'{dir_}/{last_ver}'
        assert os.path.exists(out)
        return out
    return None
