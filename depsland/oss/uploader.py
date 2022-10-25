import os
import shutil
import typing as t
from collections import namedtuple
from lk_utils import dumps
from lk_utils import fs
from lk_utils import loads
from uuid import uuid1
from .oss import get_oss_server
from ..profile_reader import get_manifest
from ..utils import compare_version
from ..utils import create_temporary_directory
from ..utils import get_file_hash
from ..utils import get_updated_time
from ..utils import ziptool


class T:
    Path = str
    Scheme = t.Literal[
        '', 'only_root',
        'all_assets', 'all_folders',
        'top_assets', 'top_files', 'top_folders',
    ]
    ManifestA = t.TypedDict('ManifestA', {
        'appid'  : str,
        'name'   : str,
        'version': str,
        'assets' : t.Dict[Path, Scheme],
        # 'exclusions': t.List[Path],
    })
    ManifestB = t.TypedDict('ManifestB', {
        'appid'  : str,
        'name'   : str,
        'version': str,
        'assets' : t.Dict[
            Path,
            Info := t.NamedTuple('Info', (
                ('scheme', Scheme),
                ('updated_time', int),
                ('hash', t.Optional[str]),
                ('key', _Key := str),
                #   a key is a form of `<uuid><ext>`. `uuid` is random
                #   generated by uuid library; `ext` is either '.zip' (for
                #   directory) or '.fzip' (for file).
            ))
        ]
    })
    
    Action = t.Literal['append', 'update', 'delete']
    DiffResult = t.Iterator[
        t.Tuple[
            Action,
            Path,
            t.Tuple[t.Optional[_Key], t.Optional[_Key]]
            #   tuple[old_key, new_key]
        ]
    ]


Info = namedtuple('Info', ('scheme', 'updated_time', 'hash', 'key'))


# -----------------------------------------------------------------------------

def main(new_app_dir: str, old_app_dir: str) -> None:
    manifest_new: T.ManifestA = get_manifest(f'{new_app_dir}/manifest.json')
    manifest_old: T.ManifestB = (
        loads(f'{old_app_dir}/manifest.pkl') if old_app_dir else {
            'appid'  : manifest_new['appid'],
            'name'   : manifest_new['name'],
            'version': '0.0.0',
            'assets' : {},
        }
    )
    _check_manifest(manifest_new, manifest_old)
    print('updating manifest: [red]{}[/] -> [green]{}[/]'.format(
        manifest_old['version'], manifest_new['version']
    ), ':r')
    
    oss_svr = get_oss_server()
    # bucket = 'apps/{}'.format(manifest_new['appid'])
    bucket = 'depsland/{}'.format(manifest_new['appid'])
    print(bucket)
    
    for action, zipped_file, (old_key, new_key) in _find_differences(
            manifest_new, manifest_old,
            saved_file=f'{new_app_dir}/manifest.pkl',
    ):
        # the path's extension is: '.zip' or '.fzip'
        print(':sri', action, fs.filename(zipped_file),
              f'[dim]([red]{old_key}[/] -> [green]{new_key}[/])[/]')
        # continue  # TEST: uncomment this line for offline test
        
        match action:
            case 'append':
                oss_svr.upload(zipped_file, f'{bucket}/{new_key}')
            case 'update':
                # delete old, upload new.
                oss_svr.delete(f'{bucket}/{old_key}')
                oss_svr.upload(zipped_file, f'{bucket}/{new_key}')
            case 'delete':
                oss_svr.delete(f'{bucket}/{old_key}')


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
    saved_data: T.ManifestB = {
        'appid'  : manifest_new['appid'],
        'name'   : manifest_new['name'],
        'version': manifest_new['version'],
        'assets' : {},
    }
    
    assets_new = manifest_new['assets']
    assets_old = manifest_old['assets']
    
    def get_new_info(path_i: str, scheme_i) -> T.Info:
        return Info(
            scheme=scheme_i,
            updated_time=get_updated_time(path_i),
            hash=get_file_hash(path_i) if os.path.isfile(path_i) else None,
            key='{}.{}'.format(
                uuid1().hex, 'fzip' if os.path.isfile(path_i) else 'zip'
            )
        )
    
    # noinspection PyTypeChecker
    for path_old in assets_old.keys():
        if path_old not in assets_new:
            yield ('delete',
                   path_old,
                   (assets_old[path_old].key, None))
    # noinspection PyTypeChecker
    for path_i, scheme_i in assets_new.items():
        if scheme_i == '':
            scheme_i = 'all_assets'
        
        info_new = get_new_info(path_i, scheme_i)
        info_old = assets_old.get(path_i)
        
        if info_old and not _compare(info_new, info_old):
            # no difference
            continue
        
        path_o = _copy_assets(path_i, temp_dir, scheme_i)
        if scheme_i == 'only_root':
            path_o = ''
        else:
            path_o = _compress(path_o, f'{temp_dir}/{info_new.key}')
        
        if info_old is None:
            yield 'append', path_o, (None, info_new.key)
        else:
            yield 'update', path_o, (info_old.key, info_new.key)
        
        saved_data['assets'][path_i] = info_new
    
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


def _compress(path_i: T.Path, file_o: str) -> str:
    if file_o.endswith('.zip'):
        ziptool.compress_dir(path_i, file_o)
    else:  # file_o.endswith('.fzip'):
        ziptool.compress_file(path_i, file_o)
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
