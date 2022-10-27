import os
import shutil
import typing as t
from collections import namedtuple
from lk_utils import dumps
from lk_utils import fs
from uuid import uuid1
from .oss import OssPath
from .oss import get_oss_server
from .. import config
from ..profile_reader import T as T0
from ..profile_reader import get_manifest
from ..utils import compare_version
from ..utils import create_temporary_directory
from ..utils import get_file_hash
from ..utils import get_updated_time
from ..utils import ziptool


class T:
    Path = str
    Scheme = t.Literal[
        'only_root',
        'all_assets', 'all_folders',
        'top_assets', 'top_files', 'top_folders',
    ]
    ManifestA = T0.Manifest
    ManifestB = t.TypedDict('ManifestB', {
        'appid'       : str,
        'name'        : str,
        'version'     : str,
        'assets'      : t.Dict[
            Path,  # must be relative path
            Info := t.NamedTuple('Info', (
                ('file_type', t.Literal['file', 'dir']),
                ('scheme', Scheme),
                ('updated_time', int),
                ('hash', t.Optional[str]),
                ('key', _Key := str),
                #   a key is a form of `<uuid><ext>`. `uuid` is random
                #   generated by uuid library; `ext` is either '.zip' (for
                #   directory) or '.fzip' (for file).
            ))
        ],
        'dependencies': t.Dict[str, str]
    })
    
    Action = t.Literal['append', 'update', 'delete']
    DiffResult = t.Iterator[
        t.Tuple[
            Action,
            Path,
            #   tuple[origin_path, new_zipped_file]
            t.Tuple[t.Optional[str], t.Optional[str]]
            #   tuple[old_key, new_key]
        ]
    ]


Info = namedtuple('Info', (
    'file_type', 'scheme', 'updated_time', 'hash', 'key'
))


# -----------------------------------------------------------------------------

def main(new_app_dir: str, old_app_dir: str) -> None:
    manifest_new: T.ManifestA = get_manifest(f'{new_app_dir}/manifest.json')
    manifest_old: T.ManifestB = (
        get_manifest(f'{old_app_dir}/manifest.pkl') if old_app_dir else {
            'appid'       : manifest_new['appid'],
            'name'        : manifest_new['name'],
            'version'     : '0.0.0',
            'assets'      : {},
            'dependencies': {},
            # 'dependencies': manifest_new['dependencies'],
        }
    )
    print(':l', manifest_new, manifest_old)
    _check_manifest(manifest_new, manifest_old)
    print('updating manifest: [red]{}[/] -> [green]{}[/]'.format(
        manifest_old['version'], manifest_new['version']
    ), ':r')
    
    oss = get_oss_server()
    oss_path = OssPath(manifest_new['appid'])
    print(oss_path)
    
    for action, zipped_file, (old_key, new_key) in _find_differences(
        manifest_new, manifest_old,
        saved_file=(manifest_new_pkl := f'{new_app_dir}/manifest.pkl'),
    ):
        # the path's extension is: '.zip' or '.fzip'
        print(':sri', action, fs.filename(zipped_file),
              f'[dim]([red]{old_key}[/] -> [green]{new_key}[/])[/]')
        if config.debug_mode:
            continue
        match action:
            case 'append':
                oss.upload(zipped_file, f'{oss_path.assets}/{new_key}')
            case 'update':
                # delete old, upload new.
                oss.delete(f'{oss_path.assets}/{old_key}')
                oss.upload(zipped_file, f'{oss_path.assets}/{new_key}')
            case 'delete':
                oss.delete(f'{oss_path.assets}/{old_key}')
    
    assert os.path.exists(manifest_new_pkl)
    oss.upload(manifest_new_pkl, oss_path.manifest)


def _check_manifest(
        manifest_new: T.ManifestA, manifest_old: T.ManifestB,
) -> None:
    assert manifest_new['appid'] == manifest_old['appid']
    v_new, v_old = manifest_new['version'], manifest_old['version']
    assert compare_version(v_new, '>', v_old), (v_new, v_old)


def _find_differences(
        manifest_new: T.ManifestA, manifest_old: T.ManifestB,
        saved_file: T.Path,
) -> T.DiffResult:
    temp_dir = create_temporary_directory()
    root_dir_i = manifest_new['start_directory']
    saved_data: T.ManifestB = {
        'appid'       : manifest_new['appid'],
        'name'        : manifest_new['name'],
        'version'     : manifest_new['version'],
        'assets'      : {},
        'dependencies': manifest_new['dependencies'],
    }
    
    assets_new = manifest_new['assets']
    assets_old = manifest_old['assets']
    
    def get_new_info(path_i: str, scheme_i) -> T.Info:
        return Info(
            file_type=(t := 'file' if fs.isfile(path_i) else 'dir'),
            scheme=scheme_i,
            updated_time=get_updated_time(path_i),
            hash=get_file_hash(path_i) if t == 'file' else None,
            key='{}.{}'.format(
                uuid1().hex, 'fzip' if os.path.isfile(path_i) else 'zip'
            )
        )
    
    def update_saved_data(path: str, info_new: T.Info) -> None:
        relpath = fs.relpath(path, start=root_dir_i)
        saved_data['assets'][relpath] = info_new
    
    # noinspection PyTypeChecker
    for path_old in assets_old.keys():
        if path_old not in assets_new:
            yield ('delete',
                   path_old,
                   (assets_old[path_old].key, None))
    # noinspection PyTypeChecker
    for path_i, scheme_i in assets_new.items():
        info_new = get_new_info(path_i, scheme_i)
        info_old = assets_old.get(path_i)
        
        if info_old and not _compare(info_new, info_old):
            # no difference
            print(':vs', 'no difference', path_i)
            update_saved_data(path_i, info_new)
            continue
        
        if scheme_i == 'only_root':
            pass
        else:
            path_o = _copy_assets(path_i, temp_dir, scheme_i)
            path_o = _compress(path_o, path_o + (
                '.zip' if info_new.file_type == 'dir' else '.fzip'
            ))
            if info_old is None:
                yield ('append',
                       path_o,
                       (None, info_new.key))
            else:
                yield ('update',
                       path_o,
                       (info_old.key, info_new.key))
        update_saved_data(path_i, info_new)
    
    print(':lv', saved_data)
    dumps(saved_data, saved_file)
    shutil.rmtree(temp_dir)


# -----------------------------------------------------------------------------

def _compare(info_new: T.Info, info_old: T.Info) -> bool:
    if info_new.scheme != info_old.scheme:
        return True
    if info_new.updated_time > info_old.updated_time:
        return True
    if info_new.hash is not None:
        if info_new.hash != info_old.hash:
            return True
    return False


def _compress(path_i: T.Path, file_o: T.Path) -> T.Path:
    if file_o.endswith('.zip'):
        ziptool.compress_dir(path_i, file_o)
    else:  # file_o.endswith('.fzip'):
        fs.move(path_i, file_o)
        # ziptool.compress_file(path_i, file_o)
    return file_o


def _copy_assets(path_i: T.Path, root_dir_o: str, scheme: T.Scheme) -> T.Path:
    def safe_make_folder(dirname: str) -> str:
        sub_temp_dir = create_temporary_directory(root_dir_o)
        os.mkdir(out := '{}/{}'.format(sub_temp_dir, dirname))
        return out
    
    if os.path.isdir(path_i):
        dir_o = safe_make_folder(os.path.basename(path_i))
    else:
        sub_temp_dir = create_temporary_directory(root_dir_o)
        file_o = '{}/{}'.format(sub_temp_dir, os.path.basename(path_i))
        fs.make_link(path_i, file_o)
        return file_o
    
    match scheme:
        case 'only_root':
            pass
        case 'all_assets':
            fs.make_link(path_i, dir_o, True)
        case 'all_folders':
            fs.clone_tree(path_i, dir_o, True)
        case 'top_assets':
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
        case 'top_folders':
            for dn in fs.find_dir_names(path_i):
                os.mkdir('{}/{}'.format(dir_o, dn))
    
    return dir_o
