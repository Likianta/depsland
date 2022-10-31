from pathlib import Path

from genexe.generate_exe import generate_exe
from lk_utils import loads


def bat_2_exe(file_i, file_o, icon='', show_console=True):
    data_r: list[str] = loads(file_i).splitlines()
    # data_w = ' && '.join(format_cmd(*data_r))
    data_w = ' && '.join(data_r).strip()
    
    # https://github.com/silvandeleemput/gen-exe
    # https://blog.csdn.net/qq981378640/article/details/52980741
    data_w = data_w.replace('%~dp0', '{EXE_DIR}').replace('%cd%', '{EXE_DIR}')
    if data_w.endswith('%*'): data_w = data_w[:-3]
    
    generate_exe(
        target=Path(file_o),
        command=data_w,
        icon_file=Path(icon) if icon else None,
        show_console=show_console
    )


if __name__ == '__main__':
    bat_2_exe('depsland_setup.bat', 'depsland_setup.exe')
