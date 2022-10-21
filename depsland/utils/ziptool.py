import os
import shutil
from zipfile import ZipFile


def compress_dir(dir_i: str, file_o: str, overwrite: bool = None) -> None:
    """
    ref: https://likianta.blog.csdn.net/article/details/126710855

    args:
        overwrite:
            True: overwrite
            False: not overwrite, and raise an FileExistsError
            None: not overwrite, no error (just return)
    """
    if os.path.exists(file_o):
        if overwrite is True:
            os.remove(file_o)
        elif overwrite is False:
            raise FileExistsError(file_o)
        else:
            return
    
    dir_i_parent = os.path.dirname(dir_i)
    with ZipFile(file_o, 'w') as z:
        z.write(dir_i, arcname=os.path.basename(dir_i))
        for root, dirs, files in os.walk(dir_i):
            for fn in files:
                z.write(
                    fp := os.path.join(root, fn),
                    arcname=os.path.relpath(fp, dir_i_parent),
                )


def compress_file(file_i: str, file_o: str, overwrite: bool = None) -> None:
    if os.path.exists(file_o):
        if overwrite is True:
            os.remove(file_o)
        elif overwrite is False:
            raise FileExistsError(file_o)
        else:
            return
    
    if file_o.endswith('.fzip'):  # trick: just rename file_i to file_o
        shutil.copyfile(file_i, file_o)
        return
    
    with ZipFile(file_o, 'w') as z:
        z.write(file_i, arcname=os.path.basename(file_i))


def unzip_file(file_i: str, dir_o: str, overwrite: bool = None) -> None:
    if os.path.exists(dir_o):
        if overwrite is True:
            shutil.rmtree(dir_o)
        elif overwrite is False:
            raise FileExistsError(dir_o)
        else:
            return
    
    dirname_o = os.path.basename(os.path.abspath(dir_o))
    with ZipFile(file_i, 'r') as z:
        z.extractall(dir_o)
    
    dlist = tuple(x for x in os.listdir(dir_o)
                  if x not in ('.DS_Store', '__MACOSX'))
    if len(dlist) == 1:
        x = dlist[0]
        if os.path.isdir(f'{dir_o}/{x}'):
            if x == dirname_o:
                print(f'move up sub folder ({x}) to be parent')
                dir_m = f'{dir_o}_tmp'
                assert not os.path.exists(dir_m)
                os.rename(dir_o, dir_m)
                shutil.move(f'{dir_m}/{x}', dir_o)
                shutil.rmtree(dir_m)
            else:
                print(f'notice there is only one folder [magenta]({x})[/] in '
                      f'this folder: [yellow]{dir_o}[/]. '
                      f'[dim](we don\'t move up it because its name is not '
                      f'same with parent.)[/]', ':r')
