import os
import typing as t
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from os.path import exists
from time import time

from lk_utils import dumps
from lk_utils import fs
from lk_utils import loads

from ... import paths
from ...manifest import T as T0
from ...manifest import diff_manifest
from ...manifest import dump_manifest
from ...manifest import get_last_installed_version
from ...manifest import init_manifest
from ...manifest import load_manifest
from ...oss import T as T1
from ...oss import get_oss_client
from ...platform import create_launcher
from ...platform import sysinfo
from ...platform.launcher import create_desktop_shortcut
from ...pypi import pypi
from ...utils import compare_version
from ...utils import init_target_tree
from ...utils import make_temp_dir
from ...utils import ziptool
from ...utils.verspec import semver_parse


class T(T0):
    LauncherInfo = T0.Launcher  # alias
    Oss = T1.Oss
    Path = str


# -----------------------------------------------------------------------------


def install_by_appid(
    appid: str, upgrade: bool = True, reinstall: bool = False
) -> None:
    m1, m0 = _get_manifests(appid)
    if m0 is None:
        m0 = init_manifest(appid, m1['name'])
    install(m1, m0, upgrade, reinstall)


def install_local(
    manifest_file: T.Path, upgrade: bool = True, reinstall: bool = False
) -> None:
    m1 = load_manifest(manifest_file)
    
    if exists(d := '{}/.oss'.format(m1['start_directory'])):
        custom_oss_root = d
    else:
        custom_oss_root = None
    
    init_target_tree(
        m1,
        d := '{}/{}/{}'.format(paths.project.apps, m1['appid'], m1['version']),
    )
    m1.start_directory = d
    
    appid, name = m1['appid'], m1['name']
    if x := _get_dir_to_last_installed_version(appid):
        m0 = load_manifest(f'{x}/manifest.pkl')
    else:
        m0 = init_manifest(appid, name)
    
    install(m1, m0, upgrade, reinstall, custom_oss_root)


def install(
    manifest_new: T.Manifest,
    manifest_old: T.Manifest = None,
    upgrade: bool = True,
    reinstall: bool = False,
    custom_oss_root: T.Path = None,
) -> None:
    """
    download and install assets from oss & pypi to the target directory of \
    `manifest_new`.
    this is an incremental operation. we download only the different parts and \
    try to reuse existed stuff as much as possible.
    usually the target directory is `<depsland.paths.apps>/<appid>/<version>`.
    """
    appid = manifest_new['appid']
    if _check_version(manifest_new, manifest_old):
        if upgrade:
            # install first, then uninstall old.
            _install(manifest_new, manifest_old, custom_oss_root)
            # TODO: for safety consideration, below is temporarily disabled, \
            #   wait for a future version that supports complete auto-upgrade.
            # _uninstall(
            #     appid, m0['version'],
            #     remove_venv=False, remove_bin=False
            # )
        else:
            print(
                'new version available but not installed. you can use '
                '`depsland install -u {appid}` or `depsland upgrade {appid}` '
                'to get it.'.format(appid=appid)
            )
    else:  # TODO
        if reinstall:
            from .uninstall import main as _uninstall
            # assert m0['version'] == m1['version']
            _uninstall(appid, manifest_old['version'])
            install_by_appid(appid, upgrade=False, reinstall=False)
        else:
            print(
                'current version is up to date. you can use `depsland '
                'install -r {appid}` or `depsland reinstall {appid}` to force '
                'reinstall it.'.format(appid=appid)
            )


def _install(
    manifest_new: T.Manifest,
    manifest_old: T.Manifest,
    custom_oss_root: T.Path = None,
) -> None:
    dir_m = make_temp_dir()
    
    if custom_oss_root:
        print('use local oss server', ':v2')
        oss = get_oss_client(manifest_new['appid'], server='local')
        oss.path.root = custom_oss_root
    else:
        oss = get_oss_client(manifest_new['appid'])
    print(oss.path)
    
    _install_files(manifest_new, manifest_old, oss, dir_m)
    _install_packages(manifest_new, manifest_old, dir_m)
    _create_launchers(manifest_new)
    
    _save_history(manifest_new['appid'], manifest_new['version'])
    _save_manifest(manifest_new)
    
    print(':rt', '[green]installation done[/]')


# -----------------------------------------------------------------------------
# callees for `install_by_appid`


def _check_update(manifest_new: T.Manifest, manifest_old: T.Manifest) -> bool:
    return compare_version(
        manifest_new['version'], '>', manifest_old['version']
    )


def _check_version(new: T.Manifest, old: T.Manifest) -> bool:
    return compare_version(new['version'], '>', old['version'])


def _get_dir_to_last_installed_version(appid: str) -> t.Optional[str]:
    if last_ver := get_last_installed_version(appid):
        dir_ = '{}/{}/{}'.format(paths.project.apps, appid, last_ver)
        assert exists(dir_), dir_
        return dir_
    return None


def _get_manifests(appid: str) -> t.Tuple[T.Manifest, t.Optional[T.Manifest]]:
    def download_new() -> T.Manifest:
        tmp_dir = make_temp_dir()
        oss = get_oss_client(appid)
        oss.download(oss.path.manifest, x := f'{tmp_dir}/manifest.pkl')
        manifest_new = load_manifest(x)
        manifest_new.start_directory = '{}/{}/{}'.format(
            paths.project.apps,
            manifest_new['appid'],
            manifest_new['version'],
        )
        init_target_tree(manifest_new)
        fs.move(x, manifest_new['start_directory'] + '/manifest.pkl')
        return manifest_new
    
    def find_old() -> t.Optional[T.Manifest]:
        if x := _get_dir_to_last_installed_version(appid):
            return load_manifest(f'{x}/manifest.pkl')
        else:
            print(
                'no previous version found, it may be your first time to '
                f'install "{appid}"'
            )
            print(
                '[dim]be noted the first-time installation may consume a '
                'long time. depsland will try to reduce the consumption in '
                'the succeeding upgrades/installations.[/]',
                ':r',
            )
            return None
    
    new, old = download_new(), find_old()
    return new, old


# -----------------------------------------------------------------------------
# callees for main process.


def _install_files(
    manifest_new: T.Manifest,
    manifest_old: T.Manifest,
    oss: T.Oss,
    temp_dir: T.Path,
) -> None:
    root0 = manifest_old['start_directory']
    root1 = manifest_new['start_directory']
    
    diff = diff_manifest(manifest_new, manifest_old)
    
    def copy_from_old(i: str, o: str, t: str) -> None:
        # `o` must not be child path of `i`.
        assert not o.startswith(i + '/')
        print('{} -> {}'.format(i, fs.relpath(o, root1)))
        # TODO: shall we use `fs.move` to make it faster?
        if t == 'file':
            fs.copy_file(i, o, True)
        else:
            fs.copy_tree(i, o, True)
    
    def download_from_oss(i: str, m: str, o: str) -> None:
        print(fs.relpath(o, root1))
        oss.download(i, m)
        ziptool.extract_file(m, o, overwrite=True)
    
    for action, relpath, (info0, info1) in diff['assets']:
        if action == 'ignore':
            path0 = fs.normpath(f'{root0}/{relpath}')
            path1 = fs.normpath(f'{root1}/{relpath}')
            if os.path.exists(path0):
                copy_from_old(path0, path1, info1.type)
                continue
            else:
                print('turn ignore to append action')
                action = 'append'
        
        if action in ('append', 'update'):
            path_i = '{}/{}'.format(oss.path.assets, info1.uid)  # an url
            path_m = fs.normpath(  # an intermediate file (zip)
                '{}/{}.{}'.format(
                    temp_dir,
                    info1.uid,
                    'zip' if info1.type == 'dir' else 'fzip',
                )
            )
            path_o = fs.normpath(f'{root1}/{relpath}')  # a file or a directory
            download_from_oss(path_i, path_m, path_o)


def _install_packages(
    manifest_new: T.Manifest,
    manifest_old: T.Manifest,
    dist_dir: T.Path = None,
) -> None:
    if dist_dir is None:
        dist_dir = paths.apps.make_packages(
            manifest_new['appid'], manifest_new['version'], clear_exists=True
        )
    
    total_diff = diff_manifest(manifest_new, manifest_old)
    package_ids = set()
    tasks_ignitor = []  # list[T.PackageInfo]
    action: T.Action
    info0: T.PackageInfo
    info1: T.PackageInfo
    pkg_id: T.PackageId
    pkg_name: T.PackageName
    for action, pkg_name, (info0, info1) in total_diff['dependencies']:
        if action == 'delete':
            continue
        pkg_id = info1['id']
        if action in ('append', 'update'):
            tasks_ignitor.append(info1)
        package_ids.add(pkg_id)
    
    if tasks_ignitor:
        print(len(tasks_ignitor))
        # we will have IO heavy tasks, so promoting max workers is fine.
        # http://c.biancheng.net/view/2627.html
        # https://stackoverflow.com/questions/42541893
        thread_pool = ThreadPoolExecutor(max_workers=len(tasks_ignitor))
        
        def download_and_install(info: T.PackageInfo) -> None:
            path0 = pypi.download_one(
                info['id'], info['appendix'].get('custom_url')
            )
            path1 = pypi.install_one(info['id'], path0)
            # update indexes
            pypi.add_to_index(path0, 0)
            pypi.add_to_index(path1, 1)
            pypi.dependencies[info['id']] = list(info['dependencies'])
            pypi.updates[info['name']] = int(time())
        
        tasks = [
            thread_pool.submit(download_and_install, info)
            for info in tasks_ignitor
        ]
        [x.result() for x in tasks]
        pypi.save_indexes()
    
    if package_ids:
        pypi.linking(package_ids, dist_dir)
    else:
        def fast_link_venv(dst_dir: T.Path) -> None:
            print('fast link venv from old version')
            assert (
                manifest_old['version'] != '0.0.0'
            ), 'cannot do fast linking from a void version'
            src_dir = paths.apps.get_packages(
                manifest_old['appid'], manifest_old['version']
            )
            fs.make_link(src_dir, dst_dir, True)
        
        fast_link_venv(dist_dir)


def _create_launchers(manifest: T.Manifest) -> None:
    create_launcher(
        manifest,
        exe_file := '{apps}/{appid}/{version}/{name}'.format(
            apps=paths.project.apps,
            appid=manifest['appid'],
            version=manifest['version'],
            name=(
                sysinfo.IS_WINDOWS and
                manifest['name'] + '.exe' or
                manifest['appid'] + '.sh'
            ),
        ),
    )
    
    if sysinfo.IS_WINDOWS:
        launcher: T.LauncherInfo = manifest['launcher']
        if not launcher['show_console']:
            # since console-less application is hard to debug if failed at \
            # startup, we provide a "debug" launcher for user.
            create_launcher(
                manifest,
                path_o='{dir}/{name} (Debug).exe'.format(
                    dir=fs.parent(exe_file),
                    name=manifest['name'],
                ),
                debug=True,
                # keep_bat=False,
                uac_admin=True,
            )
        if launcher['enable_cli']:
            fs.copy_file(exe_file, '{}/{}.exe'.format(
                paths.apps.bin, manifest['appid']
            ))
        if launcher['add_to_desktop']:
            create_desktop_shortcut(
                file_i=exe_file,
                file_o='{}/{}.lnk'.format(
                    paths.system.desktop, manifest['name']
                ),
            )
        if launcher['add_to_start_menu']:
            # WARNING: not tested
            fs.copy_file(
                exe_file, '{}/{}.exe'.format(
                    paths.system.start_menu, manifest['name']
                )
            )


def _save_history(appid: str, version: str) -> None:
    file = paths.apps.get_installation_history(appid)
    if os.path.exists(file):
        data: list = loads(file).splitlines()
    else:
        data = []
    data.insert(0, version)
    dumps(data, file)


def _save_manifest(manifest: T.Manifest) -> None:
    file_o = '{}/{}/{}/manifest.pkl'.format(
        paths.project.apps, manifest['appid'], manifest['version']
    )
    dump_manifest(manifest, file_o)


# -----------------------------------------------------------------------------


def _resolve_conflicting_name_ids(name_ids: t.Iterable[str]) -> t.Iterable[str]:
    """
    if there are multiple versions for one name, for example 'lk_utils-2.4.1'
    and 'lk_utils-2.5.0', remain the most latest version.
    FIXME: this may not be a good idea, better to raise an error right once.
    """
    name_2_versions = defaultdict(list)
    for nid in name_ids:
        a, b = nid.split('-', 1)
        name_2_versions[a].append(b)
    if conflicts := {k: v for k, v in name_2_versions.items() if len(v) > 1}:
        print(
            'found {} conflicting name ids'.format(len(conflicts)),
            conflicts,
            ':lv3',
        )
        for v in conflicts.values():
            v.sort(key=lambda x: semver_parse(x), reverse=True)
        return (f'{k}-{v[0]}' for k, v in name_2_versions.items())
    else:
        return name_ids
