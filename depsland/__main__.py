import os
import sys
import typing as t
from os.path import exists

from argsense import CommandLineInterface
from lk_utils import fs

from . import __path__
from . import __version__
from . import api
from . import paths
from .manifest import T
from .manifest import get_last_installed_version

# fix sys.argv
if len(sys.argv) > 1 and sys.argv[1].endswith('.exe'):
    # e.g. ['E:\depsland_app\depsland\__main__.py',
    #       'E:\depsland_app\depsland.exe', ...]
    sys.argv.pop(1)

cli = CommandLineInterface('depsland')
print(
    'depsland [red][dim]v[/]{}[/] [dim]({})[/]'.format(
        __version__, __path__[0]
    ),
    ':r',
)


@cli.cmd()
def about() -> None:
    """
    show basic information about depsland.
    """
    # ref: the rich text (with gradient color) effect is copied from
    #   likianta/lk-logger project.
    from random import choice
    
    from lk_logger.control import _blend_text  # noqa
    
    from . import __date__
    from . import __path__
    from . import __version__
    
    color_pairs_group = (
        ('#0a87ee', '#9294f0'),  # calm blue -> light blue
        ('#2d34f1', '#9294f0'),  # ocean blue -> light blue
        ('#ed3b3b', '#d08bf3'),  # rose red -> violet
        ('#f38cfd', '#d08bf3'),  # light magenta -> violet
        ('#f47fa4', '#f49364'),  # cold sandy -> camel tan
    )
    
    color_pair = choice(color_pairs_group)
    colorful_title = _blend_text(
        '♥ depsland v{} ♥'.format(__version__), color_pair
    )
    print(f'[b]{colorful_title}[/]', ':rs1')
    
    print(':rs1', '[cyan]released at [u]{}[/][/]'.format(__date__))
    print(':rs1', '[magenta]located at [u]{}[/][/]'.format(__path__[0]))


@cli.cmd()
def self_location() -> None:
    print('[green b u]{}[/]'.format(fs.xpath('..', True)), ':s1r')


@cli.cmd()
def welcome(confirm_close: bool = False) -> None:
    """
    show welcome message and exit.
    """
    from textwrap import dedent
    
    from rich.markdown import Markdown
    
    from . import __date__
    from . import __version__
    
    print(
        ':r1',
        Markdown(
            dedent('''
            # DEPSLAND
            
            Depsland is a python apps manager for non-developer users.
            
            - Version: {}
            - Release date: {}
            - Author: {}
            - Official site: {}
            ''').format(
                __version__,
                __date__,
                'Likianta (likianta@foxmail.com)',
                'https://github.com/likianta/depsland',
            )
        ),
    )
    
    if confirm_close:
        input('press enter to close window...')


@cli.cmd()
def launch_gui(_app_token: str = None) -> None:
    """
    launch depsland gui.
    
    args:
        _app_token: an appid or a path to a manifest file.
            if given, the app will launch and instantly install it.
    """
    try:
        pass
    except ModuleNotFoundError:
        print(
            'launching GUI failed. you may forget to install qt for python '
            'library (suggest `pip install pyside6` etc.)',
            ':v4',
        )
        return
    if _app_token and os.path.isfile(_app_token):
        _app_token = fs.abspath(_app_token)
    
    # import os
    # os.environ['QT_API'] = 'pyside6_lite'
    from .ui import launch_app
    
    launch_app(_app_token)


# -----------------------------------------------------------------------------
# ordered by lifecycle


@cli.cmd()
def init(
    target: str = '.',
    app_name: str = '',
    force_create: bool = False,
    auto_find_requirements: bool = False,
) -> None:
    """
    create a "manifest.json" file in project directory.
    
    kwargs:
        target (-t): given the directory to the project, or a path to the -
            manifest file.
            if the directory doesn't exist, will create it.
            if it is the manifest file path, we recommend you using -
            'manifest.json' as its file name.
            if target already exists, will stop and return. you can pass `-f` -
            to overwrite.
            be noticed the file extension can only be '.json'.
        appname (-n): if not given, will use directory name as app name.
        auto_find_requirements (-a):
        force_create (-f):
    """
    manifest_file = _get_manifest_path(target, ensure_exists=False)
    api.init(manifest_file, app_name, force_create, auto_find_requirements)


@cli.cmd()
def build(target: str = '.', gen_exe: bool = True) -> None:
    """
    build your python application based on manifest file.
    the build result is stored in "dist" directory.
    [dim i](if "dist" not exists, it will be auto created.)[/]
    
    kwargs:
        target (-t):
    
    tip:
        if you want to add a custom icon, you need to define it in manifest.
    """
    api.build(_get_manifest_path(target), gen_exe)


@cli.cmd()
def publish(target='.', full_upload=False) -> None:
    """
    publish dist assets to oss.
    if you configured a local oss server, it will generate assets to -
    `~/oss/apps/<appid>/<version>` directory.
    
    kwargs:
        target (-t):
        full_upload (-f): if true, will upload all assets, ignore the files -
            which may already exist in oss (they all will be overwritten).
            this option is useful if you found the oss server not work properly.
    """
    api.publish(_get_manifest_path(target), full_upload)


@cli.cmd()
def install(appid: str, upgrade=True, reinstall=False) -> None:
    """
    install an app from oss by querying appid.
    
    kwargs:
        upgrade (-u):
        reinstall (-r):
    """
    api.install_by_appid(appid, upgrade, reinstall)


@cli.cmd()
def upgrade(appid: str) -> None:
    """
    upgrade an app from oss by querying appid.
    """
    api.install_by_appid(appid, upgrade=True, reinstall=False)


@cli.cmd()
def uninstall(appid: str, version: str = None) -> None:
    """
    uninstall an application.
    """
    if version is None:
        version = get_last_installed_version(appid)
    if version is None:
        print(f'{appid} is already uninstalled.')
        return
    api.uninstall(appid, version)


# @cli.cmd()
# def self_upgrade() -> None:
#     """
#     upgrade depsland itself.
#     """
#     api.self_upgrade()


# -----------------------------------------------------------------------------


@cli.cmd()
def show(appid: str, version: str = None) -> None:
    """
    show manifest of an app.
    """
    from .manifest import load_manifest
    
    if version is None:
        version = get_last_installed_version(appid)
    assert version is not None
    dir_ = '{}/{}/{}'.format(paths.project.apps, appid, version)
    manifest = load_manifest(f'{dir_}/manifest.pkl')
    print(manifest, ':l')


@cli.cmd()
def view_manifest(manifest: str = '.') -> None:
    from .manifest import load_manifest
    
    manifest = load_manifest(_get_manifest_path(manifest))
    print(manifest, ':l')


@cli.cmd(transport_help=True)
def run(appid: str, *args, _version: str = None, **kwargs) -> None:
    """
    a general launcher to start an installed app.
    """
    print(sys.argv, ':lv')
    
    version = _version or get_last_installed_version(appid)
    if not version:
        print(':v4', f'cannot find installed version of {appid}')
        return
    
    import subprocess
    
    import lk_logger
    from argsense import args_2_cargs
    
    from .manifest import load_manifest
    from .manifest import parse_script_info
    
    manifest = load_manifest(
        '{}/{}/{}/manifest.pkl'.format(paths.project.apps, appid, version)
    )
    assert manifest['version'] == version
    command, args0, kwargs0 = parse_script_info(manifest)
    os.environ['DEPSLAND'] = paths.project.root
    os.environ['PYTHONPATH'] = '.;{app_dir};{pkg_dir}'.format(
        app_dir=manifest['start_directory'],
        pkg_dir=paths.apps.get_packages(appid, version),
    )
    
    # print(':v', args, kwargs)
    lk_logger.unload()
    subprocess.run(
        (
            *command,
            *args_2_cargs(*args0, **kwargs0),
            *args_2_cargs(*args, **kwargs),
        ),
        cwd=manifest['start_directory'],
    )


# -----------------------------------------------------------------------------


@cli.cmd()
def rebuild_pypi_index(full: bool = False) -> None:
    """
    rebuild local pypi index. this may resolve some historical problems caused -
    by pip network issues.
    
    kwargs:
        full (-f): if a package is downloaded but not installed, will perform -
            a `pip install` action.
    """
    from .doctor import rebuild_pypi_index
    
    rebuild_pypi_index(perform_pip_install=full)


@cli.cmd()
def get_package_size(
    name: str, version: str = None, include_dependencies: bool = False
) -> None:
    """
    kwargs:
        include_dependencies (-d):
    """
    from .pypi import insight
    
    insight.measure_package_size(name, version, include_dependencies)


# -----------------------------------------------------------------------------


def _check_version(new: T.Manifest, old: T.Manifest) -> bool:
    from .utils import compare_version
    
    return compare_version(new['version'], '>', old['version'])


def _get_dir_to_last_installed_version(appid: str) -> t.Optional[str]:
    if last_ver := get_last_installed_version(appid):
        dir_ = '{}/{}/{}'.format(paths.project.apps, appid, last_ver)
        assert exists(dir_), dir_
        return dir_
    return None


def _get_manifests(appid: str) -> t.Tuple[t.Optional[T.Manifest], T.Manifest]:
    from .manifest import load_manifest
    from .oss import get_oss_client
    from .utils import init_target_tree
    from .utils import make_temp_dir
    
    temp_dir = make_temp_dir()
    
    oss = get_oss_client(appid)
    oss.download(oss.path.manifest, x := f'{temp_dir}/manifest.pkl')
    manifest_new = load_manifest(x)
    manifest_new.start_directory = '{}/{}/{}'.format(
        paths.project.apps, manifest_new['appid'], manifest_new['version']
    )
    init_target_tree(manifest_new)
    fs.move(x, manifest_new['start_directory'] + '/manifest.pkl')
    
    if x := _get_dir_to_last_installed_version(appid):
        manifest_old = load_manifest(f'{x}/manifest.pkl')
    else:
        print(
            'no previous version found, it may be your first time to install '
            f'{appid}'
        )
        print(
            '[dim]be noted the first-time installation may consume a long '
            'time. depsland will try to reduce the consumption in the '
            'succeeding upgrades/installations.[/]',
            ':r',
        )
        manifest_old = None
    
    return manifest_old, manifest_new


def _get_manifest_path(target: str, ensure_exists=True) -> str:
    """return an abspath to manifest file."""
    if target.endswith('.json'):
        out = fs.normpath(target, True)
    else:
        assert not os.path.isfile(target)
        if not os.path.exists(target):
            os.mkdir(target)
        out = fs.normpath(f'{target}/manifest.json', True)
    if ensure_exists:
        assert exists(out)
    print(out, ':pvs')
    return out


def _run_cli():
    """this function is for poetry to generate script entry point."""
    cli.run()


if __name__ == '__main__':
    cli.run()
