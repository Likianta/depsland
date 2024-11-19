from lk_utils import fs

from depsland import bat_2_exe as _b2e
from depsland.platform.launcher.make_exe.bat_2_exe_2 import bat_2_exe as _b2e2


def bat_2_exe(
    file_i: str,
    show_console: bool = True,
    uac_admin: bool = False,
    icon: str = fs.xpath('../icon/launcher.ico'),
) -> None:
    """
    args:
        file_i: the file is ".bat" file, which is under ~/build/exe folder.

    kwargs:
        show_console (-c):
        uac_admin (-u):
    """
    # _b2e(
    #     file_bat=file_i,
    #     file_exe=fs.replace_ext(file_i, 'exe'),
    #     icon=icon,
    #     show_console=show_console,
    #     uac_admin=uac_admin,
    # )
    _b2e2(
        file_i=file_i,
        file_o=fs.replace_ext(file_i, 'exe'),
        icon=icon,
        show_console=show_console,
        uac_admin=uac_admin,
    )
