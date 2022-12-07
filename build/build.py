"""
py build/build.py full-build aliyun
py build/build.py full-build local
"""
if 1:
    import sys
    from lk_utils import xpath
    sys.path.insert(0, xpath('..', True))

import os
from collections import defaultdict
from os.path import exists

from argsense import cli
from lk_utils import dumps
from lk_utils import fs

from depsland import __version__
from depsland import bat_2_exe as _b2e
from depsland import paths
from depsland.manifest import dump_manifest
from depsland.manifest import load_manifest
from depsland.utils import ziptool

print(':v2', f'depsland version: {__version__}')


@cli.cmd()
def full_build(oss_scheme: str, add_python_path=True):
    root_i = paths.project.root
    root_o = '{dist}/{version}'.format(
        dist=paths.project.dist,
        version=f'depsland-{__version__}'
    )
    assert not exists(root_o)
    os.mkdir(root_o)
    
    # make empty dirs
    os.mkdir(f'{root_o}/apps')
    os.mkdir(f'{root_o}/apps/.bin')
    os.mkdir(f'{root_o}/apps/.venv')
    os.mkdir(f'{root_o}/build')
    os.mkdir(f'{root_o}/build/exe')
    os.mkdir(f'{root_o}/conf')
    # os.mkdir(f'{root_o}/depsland')
    os.mkdir(f'{root_o}/dist')
    os.mkdir(f'{root_o}/docs')
    os.mkdir(f'{root_o}/lib')
    # os.mkdir(f'{root_o}/lib/pyside6_lite')
    os.mkdir(f'{root_o}/oss')
    os.mkdir(f'{root_o}/oss/apps')
    os.mkdir(f'{root_o}/oss/test')
    os.mkdir(f'{root_o}/pypi')
    os.mkdir(f'{root_o}/pypi/cache')
    os.mkdir(f'{root_o}/pypi/downloads')
    os.mkdir(f'{root_o}/pypi/index')
    os.mkdir(f'{root_o}/pypi/installed')
    # os.mkdir(f'{root_o}/python')
    # os.mkdir(f'{root_o}/sidework')
    os.mkdir(f'{root_o}/temp')
    os.mkdir(f'{root_o}/temp/.self_upgrade')
    os.mkdir(f'{root_o}/temp/.unittests')
    
    # copy files
    fs.copy_file(f'{root_i}/build/exe/depsland.exe',
                 f'{root_o}/build/exe/depsland.exe')
    fs.copy_file(f'{root_i}/build/exe/desktop.exe',
                 f'{root_o}/build/exe/desktop.exe')
    fs.copy_file(f'{root_i}/build/exe/launcher.ico',
                 f'{root_o}/build/exe/launcher.ico')
    fs.copy_file(f'{root_i}/build/exe/setup.exe',
                 f'{root_o}/setup.exe')
    fs.copy_tree(f'{root_i}/build/setup_wizard',
                 f'{root_o}/build/setup_wizard')
    fs.copy_file(f'{root_i}/build/depsland_setup.py',
                 f'{root_o}/build/depsland_setup.py')
    fs.copy_tree(f'{root_i}/depsland',
                 f'{root_o}/depsland')
    fs.make_link(f'{root_i}/lib/pyside6_lite',
                 f'{root_o}/lib/pyside6_lite')
    fs.copy_tree(f'{root_i}/sidework',
                 f'{root_o}/sidework')
    fs.copy_file(f'{root_i}/.depsland_project',
                 f'{root_o}/.depsland_project')
    if oss_scheme == 'local':
        fs.copy_file(f'{root_i}/conf/depsland.yaml',
                     f'{root_o}/conf/depsland.yaml')
    else:
        fs.copy_file(f'{root_i}/conf/depsland_for_dev.yaml',
                     f'{root_o}/conf/depsland.yaml')
    if add_python_path:
        fs.make_link(f'{root_i}/python',
                     f'{root_o}/python')
    
    # init files
    dump_manifest(load_manifest(f'{root_i}/manifest.json'),
                  f'{root_o}/manifest.pkl')
    dumps(defaultdict(list), f'{root_o}/pypi/index/dependencies.pkl')
    dumps(defaultdict(list), f'{root_o}/pypi/index/name_2_versions.pkl')
    dumps({}, f'{root_o}/pypi/index/name_id_2_paths.pkl')
    dumps({}, f'{root_o}/pypi/index/updates.pkl')
    
    print(':t', 'see result at ' + fs.relpath(root_o))


@cli.cmd()
def min_build(add_python_packages=False):  # DELETE
    root_i = paths.project.root
    root_o = '{dist}/{version}'.format(
        dist=paths.project.dist,
        version=f'depsland-{__version__}-(patch)'
    )
    assert not exists(root_o)
    os.mkdir(root_o)
    
    # make empty dirs
    os.mkdir(f'{root_o}/apps')
    os.mkdir(f'{root_o}/build')
    os.mkdir(f'{root_o}/build/exe')
    os.mkdir(f'{root_o}/conf')
    # os.mkdir(f'{root_o}/depsland')
    os.mkdir(f'{root_o}/docs')
    os.mkdir(f'{root_o}/pypi')
    os.mkdir(f'{root_o}/pypi/cache')
    os.mkdir(f'{root_o}/pypi/downloads')
    os.mkdir(f'{root_o}/pypi/index')
    os.mkdir(f'{root_o}/pypi/installed')
    os.mkdir(f'{root_o}/python')
    # os.mkdir(f'{root_o}/sidework')
    os.mkdir(f'{root_o}/temp')
    os.mkdir(f'{root_o}/temp/.fake_oss_storage')
    os.mkdir(f'{root_o}/temp/.self_upgrade')
    os.mkdir(f'{root_o}/temp/.unittests')
    
    # copy files
    fs.copy_file(f'{root_i}/build/exe/depsland.exe',
                 f'{root_o}/build/exe/depsland.exe')
    fs.copy_file(f'{root_i}/build/exe/desktop.exe',
                 f'{root_o}/build/exe/desktop.exe')
    fs.copy_file(f'{root_i}/build/exe/setup_patch.exe',
                 f'{root_o}/setup.exe')
    fs.copy_file(f'{root_i}/build/depsland_setup.py',
                 f'{root_o}/build/depsland_setup.py')
    fs.copy_file(f'{root_i}/conf/depsland.yaml',
                 f'{root_o}/conf/depsland.yaml')
    fs.copy_file(f'{root_i}/conf/oss_client.yaml',
                 f'{root_o}/conf/oss_client.yaml')
    fs.copy_tree(f'{root_i}/depsland',
                 f'{root_o}/depsland')
    fs.copy_tree(f'{root_i}/sidework',
                 f'{root_o}/sidework')
    if add_python_packages:
        os.mkdir(f'{root_o}/python/Lib')
        fs.make_link(f'{root_i}/python/Lib/site-packages',
                     f'{root_o}/python/Lib/site-packages')
    else:
        os.mkdir(f'{root_o}/python/Lib')
        os.mkdir(f'{root_o}/python/Lib/site-packages')
    
    # init files
    dump_manifest(load_manifest(f'{root_i}/manifest.json'),
                  f'{root_o}/manifest.pkl')
    dumps(defaultdict(list), f'{root_o}/pypi/index/dependencies.pkl')
    dumps(defaultdict(list), f'{root_o}/pypi/index/name_2_versions.pkl')
    dumps({}, f'{root_o}/pypi/index/name_id_2_paths.pkl')
    dumps({}, f'{root_o}/pypi/index/updates.pkl')
    
    print(':t', 'see result at', fs.relpath(root_o))


# -----------------------------------------------------------------------------

@cli.cmd()
def bat_2_exe(file_i: str, show_console=True, uac_admin=False):
    """
    args:
        file_i: the file is ".bat" file, which is under ~/build/exe folder.
        
    kwargs:
        show_console (-c):
        uac_admin (-u):
    """
    _b2e(
        file_i,
        icon=xpath('exe/launcher.ico'),
        show_console=show_console,
        uac_admin=uac_admin
    )


@cli.cmd()
def build_all_launchers():
    for f in fs.find_files(xpath('exe'), '.bat'):
        print(':i', f.name)
        _b2e(f.path, icon=xpath('exe/launcher.ico'))


@cli.cmd()
def compress_to_zip():
    dir_i = '{}/{}'.format(paths.project.dist, f'depsland-{__version__}')
    file_o = '{}/{}'.format(paths.project.dist, f'depsland-{__version__}.zip')
    ziptool.compress_dir(dir_i, file_o, overwrite=True)
    print(':t', 'see result at', fs.relpath(file_o))


if __name__ == '__main__':
    cli.run()
