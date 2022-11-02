import os
import typing as t
from collections import namedtuple

from lk_utils import dumps
from lk_utils import fs

from ... import config
from ... import paths
from ...manifest import T as T0
from ...manifest import get_app_info
from ...manifest import init_manifest
from ...manifest import load_manifest
from ...oss import OssPath
from ...oss import get_oss_server
from ...utils import compare_version
from ...utils import get_file_hash
from ...utils import get_updated_time
from ...utils import make_temp_dir
from ...utils import ziptool


# noinspection PyTypedDict
class T:
    Path = str
    Scheme = t.Literal[
        'root',
        'all', 'all_dirs',
        'top', 'top_files', 'top_dirs'
    ]
    
    ManifestA = T0.Manifest
    ManifestB = t.TypedDict('ManifestB', {
        'appid'          : str,
        'name'           : str,
        'version'        : str,
        'start_directory': Path,
        'assets'         : t.Dict[
            Path,  # must be relative path
            Info := t.NamedTuple('Info', (
                ('type', t.Literal['file', 'dir']),
                ('scheme', Scheme),
                ('updated_time', int),
                ('hash', t.Optional[str]),  # if type is dir, the hash is None
                ('uid', str),  # the uid will be used as key to filename in oss.
            ))
        ],
        'dependencies'   : t.Dict[str, str],
        'pypi'           : t.Dict[str, None],
        #   the values are meaningless, just for compatible with ManifestA.
        'launcher'       : t.TypedDict('Launcher', {
            'command'   : str,
            'desktop'   : bool,
            'start_menu': bool,
        }),
    })
    
    Action = t.Literal['append', 'update', 'delete']
    DiffResult = t.Iterator[
        t.Tuple[
            Action,
            Path,
            #   tuple[origin_path, new_zipped_file]
            t.Tuple[t.Optional[str], t.Optional[str]]
            #   tuple[old_uid, new_uid]
        ]
    ]


AssetInfo = namedtuple('AssetInfo', (
    'type', 'scheme', 'updated_time', 'hash', 'uid'
))


# -----------------------------------------------------------------------------

def main(manifest_file: str) -> None:
    appinfo = get_app_info(manifest_file)
    
    if not appinfo['history']:
        _upload(
            new_src_dir=appinfo['src_dir'],
            new_app_dir=appinfo['dst_dir'],
            old_app_dir=''
        )
    else:
        _upload(
            new_src_dir=appinfo['src_dir'],
            new_app_dir=appinfo['dst_dir'],
            old_app_dir='{}/{}/{}'.format(
                paths.Project.apps,
                appinfo['appid'],
                appinfo['history'][0]
            )
        )
    
    appinfo['history'].insert(0, appinfo['version'])
    dumps(appinfo['history'], paths.apps.get_history_versions(appinfo['appid']))


def _upload(new_src_dir: str, new_app_dir: str, old_app_dir: str) -> None:
    manifest_new: T.ManifestA = load_manifest(f'{new_src_dir}/manifest.json')
    manifest_old: T.ManifestB = (
        load_manifest(f'{old_app_dir}/manifest.pkl') if old_app_dir
        else init_manifest(manifest_new['appid'], manifest_new['name'])
    )
    print(':l', manifest_new, manifest_old)
    _check_manifest(manifest_new, manifest_old)
    print('updating manifest: [red]{}[/] -> [green]{}[/]'.format(
        manifest_old['version'], manifest_new['version']
    ), ':r')
    
    oss = get_oss_server()
    oss_path = OssPath(manifest_new['appid'])
    print(oss_path)
    
    for action, zipped_file, (old_uid, new_uid) in _find_assets_differences(
            manifest_new, manifest_old,
            saved_file=(manifest_new_pkl := f'{new_app_dir}/manifest.pkl'),
    ):
        # the path's extension is: '.zip' or '.fzip'
        print(':sri', action, fs.filename(zipped_file),
              f'[dim]([red]{old_uid}[/] -> [green]{new_uid}[/])[/]')
        if config.debug_mode:
            continue
        match action:
            case 'append':
                oss.upload(zipped_file, f'{oss_path.assets}/{new_uid}')
            case 'update':
                # delete old, upload new.
                oss.delete(f'{oss_path.assets}/{old_uid}')
                oss.upload(zipped_file, f'{oss_path.assets}/{new_uid}')
            case 'delete':
                oss.delete(f'{oss_path.assets}/{old_uid}')
    print(':i0s')
    
    for action, whl_name, whl_path in _find_pypi_differences(
            manifest_new, manifest_old
    ):
        print(':sri', action, '[{}]{}[/]'.format(
            'green' if action == 'append' else 'red',
            whl_name
        ))
        if config.debug_mode:
            continue
        match action:
            case 'append':
                oss.upload(whl_path, f'{oss_path.pypi}/{whl_name}')
            case 'delete':
                oss.delete(f'{oss_path.pypi}/{whl_name}')
    
    assert os.path.exists(manifest_new_pkl)
    oss.upload(manifest_new_pkl, oss_path.manifest)


def _check_manifest(
        manifest_new: T.ManifestA, manifest_old: T.ManifestB,
) -> None:
    assert manifest_new['appid'] == manifest_old['appid']
    v_new, v_old = manifest_new['version'], manifest_old['version']
    assert compare_version(v_new, '>', v_old), (v_new, v_old)


def _find_assets_differences(
        manifest_new: T.ManifestA, manifest_old: T.ManifestB,
        saved_file: T.Path,
) -> T.DiffResult:
    temp_dir = make_temp_dir()
    root_dir_i = manifest_new['start_directory']
    saved_data: T.ManifestB = {
        'appid'          : manifest_new['appid'],
        'name'           : manifest_new['name'],
        'version'        : manifest_new['version'],
        'start_directory': fs.parent_path(saved_file),
        'assets'         : {},  # update later
        'dependencies'   : manifest_new['dependencies'],
        'pypi'           : {x: None for x in manifest_new['pypi'].keys()},
        'launcher'       : manifest_new['launcher'],
    }
    
    assets_new = manifest_new['assets']
    assets_old = manifest_old['assets']
    
    def get_new_info(abspath: T.Path, scheme: T.Scheme) -> T.Info:
        return AssetInfo(  # noqa
            type=(t := 'file' if fs.isfile(abspath) else 'dir'),
            scheme=scheme,
            updated_time=(utime := get_updated_time(abspath)),
            hash=(hash_ := get_file_hash(abspath) if t == 'file' else None),
            uid=hash_ or str(utime),
        )
    
    def update_saved_data(abspath: T.Path, info_new: T.Info) -> None:
        relpath = fs.relpath(abspath, start=root_dir_i)
        # print(':v', abspath, relpath)
        saved_data['assets'][relpath] = info_new
    
    for (key, abspath, info) in _iterate_assets(manifest_old):
        if key not in assets_new:
            yield 'delete', abspath, (info.uid, None)
    for (key_i, abspath_i, scheme_i) in _iterate_assets(manifest_new):
        info_i = get_new_info(abspath_i, scheme_i)
        info_j = assets_old.get(key_i)
        
        if info_j and _is_same_info(info_i, info_j):
            # no difference
            print(':vs', 'no difference', key_i)
            update_saved_data(abspath_i, info_i)
            continue
        
        if scheme_i == 'root':
            pass
        else:
            path_o = _copy_assets(abspath_i, temp_dir, scheme_i)
            path_o = _compress(path_o, path_o + (
                '.zip' if info_i.type == 'dir' else '.fzip'
            ))
            if info_j is None:
                yield 'append', path_o, (None, info_i.uid)
            else:
                yield 'update', path_o, (info_j.uid, info_i.uid)
        update_saved_data(abspath_i, info_i)
    
    print(':lv', saved_data)
    dumps(saved_data, saved_file)
    fs.remove_tree(temp_dir)


def _find_pypi_differences(
        manifest_new: T.ManifestA, manifest_old: T.ManifestB
) -> t.Iterator[t.Tuple[T.Action, str, t.Optional[T.Path]]]:
    """
    this function is much simpler than `_find_assets_differences`.
    yields: iter[tuple[literal['delete', 'append'], filename, filepath]]
    """
    pypi_new: t.Dict[str, str] = manifest_new['pypi']
    pypi_old: t.Dict[str, None] = manifest_old['pypi']
    for fn in pypi_old:
        if fn not in pypi_new:
            yield 'delete', fn, None
    for fn, fp in pypi_new.items():
        if fn not in pypi_old:
            yield 'append', fn, fp


# -----------------------------------------------------------------------------

def _compress(path_i: T.Path, file_o: T.Path) -> T.Path:
    if file_o.endswith('.zip'):
        ziptool.compress_dir(path_i, file_o)
    else:  # file_o.endswith('.fzip'):
        fs.move(path_i, file_o)
        # ziptool.compress_file(path_i, file_o)
    return file_o


def _copy_assets(
        path_i: T.Path,
        root_dir_o: T.Path,
        scheme: T.Scheme
) -> T.Path:
    def safe_make_dir(dirname: str) -> str:
        sub_temp_dir = make_temp_dir(root_dir_o)
        os.mkdir(out := '{}/{}'.format(sub_temp_dir, dirname))
        return out
    
    if os.path.isdir(path_i):
        dir_o = safe_make_dir(os.path.basename(path_i))
    else:
        sub_temp_dir = make_temp_dir(root_dir_o)
        file_o = '{}/{}'.format(sub_temp_dir, os.path.basename(path_i))
        fs.make_link(path_i, file_o)
        return file_o
    
    match scheme:
        case 'root':
            pass
        case 'all':
            fs.make_link(path_i, dir_o, True)
        case 'all_dirs':
            fs.clone_tree(path_i, dir_o, True)
        case 'top':
            for dn in fs.find_dir_names(path_i):
                os.mkdir('{}/{}'.format(dir_o, dn))
            for f in fs.find_files(path_i):
                file_i = f.path
                file_o = '{}/{}'.format(dir_o, f.name)
                fs.make_link(file_i, file_o)
        case 'top_files':
            for f in fs.find_files(path_i):
                file_i = f.path
                file_o = '{}/{}'.format(dir_o, f.name)
                fs.make_link(file_i, file_o)
        case 'top_dirs':
            for dn in fs.find_dir_names(path_i):
                os.mkdir('{}/{}'.format(dir_o, dn))
    
    return dir_o


def _is_same_info(info_new: T.Info, info_old: T.Info) -> bool:
    if info_new.scheme != info_old.scheme:
        return False
    if info_new.type != info_old.type:
        return False
    if info_new.uid != info_old.uid:
        return False
    return True


def _iterate_assets(
        manifest: t.Union[T.ManifestA, T.ManifestB]
) -> t.Iterator[t.Tuple[str, str, t.Union[T.Scheme, T.Info]]]:
    #   yields: iter[tuple[relpath, abspath, scheme_or_info]]
    start_directory = manifest['start_directory']
    for relpath, value in manifest['assets'].items():
        yield relpath, fs.normpath(f'{start_directory}/{relpath}'), value
