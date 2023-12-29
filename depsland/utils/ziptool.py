import os
import shutil
import typing as t
from zipfile import ZipFile


def compress_dir(dir_i: str, file_o: str, overwrite: bool = None) -> str:
    """
    ref: https://likianta.blog.csdn.net/article/details/126710855
    """
    if os.path.exists(file_o):
        if not _overwrite(file_o, overwrite):
            return file_o
    # if dir_i.endswith('/.'):
    #     dir_i = dir_i[:-2]
    dir_i_parent = os.path.dirname(dir_i)
    with ZipFile(file_o, 'w') as z:
        z.write(dir_i, arcname=os.path.basename(dir_i))
        for root, dirs, files in os.walk(dir_i):
            for fn in files:
                z.write(
                    fp := os.path.join(root, fn),
                    arcname=os.path.relpath(fp, dir_i_parent),
                )
    return file_o


def compress_file(file_i: str, file_o: str, overwrite: bool = None) -> str:
    if os.path.exists(file_o):
        if not _overwrite(file_o, overwrite):
            return file_o
    if file_o.endswith('.fzip'):  # trick: just rename file_i to file_o
        shutil.copyfile(file_i, file_o)
        return file_o
    with ZipFile(file_o, 'w') as z:
        z.write(file_i, arcname=os.path.basename(file_i))
    return file_o


def extract_file(file_i: str, path_o: str, overwrite: bool = None) -> str:
    if os.path.exists(path_o):
        if not _overwrite(path_o, overwrite):
            return path_o
    
    if file_i.endswith('.fzip'):
        file_o = path_o
        shutil.copyfile(file_i, file_o)
        return file_o
    else:
        dir_o = path_o
        # if dir_o.endswith('/.'):
        #     dir_o = dir_o[:-2]
    
    dirname_o = os.path.basename(os.path.abspath(dir_o))
    with ZipFile(file_i, 'r') as z:
        z.extractall(dir_o)
    
    dlist = tuple(
        x for x in os.listdir(dir_o) if x not in ('.DS_Store', '__MACOSX')
    )
    if len(dlist) == 1:
        x = dlist[0]
        if os.path.isdir(f'{dir_o}/{x}'):
            # print(os.listdir(f'{dir_o}/{x}'), ':v')
            if x == dirname_o:
                print(
                    f'move up sub folder [cyan]({x})[/] to be'
                    ' parent',
                    ':vspr',
                )
                dir_m = f'{dir_o}_tmp'
                assert not os.path.exists(dir_m)
                os.rename(dir_o, dir_m)
                shutil.move(f'{dir_m}/{x}', dir_o)
                shutil.rmtree(dir_m)
            else:
                print(
                    f'notice there is only one folder [magenta]({x})[/] in '
                    f'this folder: [yellow]{dir_o}[/]. '
                    '[dim](we don\'t move up it because its name is not same '
                    'with its parent.)[/]',
                    ':r',
                )
    return dir_o


def _overwrite(src: str, scheme: t.Optional[bool]) -> bool:
    """
    args:
        scheme:
            True: overwrite
            False: no overwrite, and raise an FileExistsError
            None: no overwrite, no error (skip)
    returns:
        True tells the caller that we DID overwrite.
        False tells the caller that we CANNOT overwrite.
        the caller should check this value and care about what to do next.
        usually, the caller will go on its work if it True, or return directly \
        if it False.
    """
    if scheme is None:
        return False
    if scheme is True:
        if os.path.isfile(src):
            os.remove(src)
        elif os.path.islink(src):
            os.unlink(src)
        else:
            shutil.rmtree(src)
        return True
    if scheme is False:
        raise FileExistsError(src)
