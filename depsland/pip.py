import re

from lk_logger import lk
from lk_utils import send_cmd
from lk_utils.filesniff import normpath
from yaml import safe_load

from .path_struct import src_struct
from .typehint import List
from .typehint import Set


class Pip:
    
    def __init__(self, pip, local, **kwargs):
        self.head = pip
        template = PipCmdTemplate(pip, local, **kwargs)
        self.get_pip_cmd = template.get_pip_cmd
    
    def change_pip_options(self, **kwargs):
        """
        Keyword Args:
            offline: bool[False]
            pypi_url: str
            pyversion: TPyVersion[src_struct.pyversion]
            cache_dir: TPath[src_struct.cache]
            quiet: bool[False]
        """
        template = PipCmdTemplate(self.head, src_struct.downloads, **kwargs)
        self.get_pip_cmd = template.get_pip_cmd
    
    def test(self):
        lk.loga(send_cmd(f'{self.head} -V'), h='parent')
    
    def download(self, name: str, target=src_struct.downloads):
        return send_cmd(self.get_pip_cmd(
            'download', name, f'--dest="{target}"',
            add_pkg_idx_options=True
        ))
    
    def download_r(self, file, target=src_struct.downloads):
        return send_cmd(self.get_pip_cmd(
            'download -r', file, f'--dest="{target}"',
            add_pkg_idx_options=True
        ))
    
    def install(self, name: str, target=src_struct.site_packages):
        """ install package to `VenvConf.lib_dir` (default). """
        return send_cmd(self.get_pip_cmd(
            'install', name, f'--target="{target}"',
            add_pkg_idx_options=True
        ))
    
    def install_r(self, file, target=src_struct.site_packages):
        return send_cmd(self.get_pip_cmd(
            'install -r', file, f'--target="{target}"',
            add_pkg_idx_options=True
        ))
    
    def show_dependencies(self, name) -> List[str]:
        ret = send_cmd(self.get_pip_cmd('show', name))
        #   -> see example in `self.show_location`
        ret = safe_load(ret)
        if ret['Requires']:
            return ret['Requires'].split(', ')
            #   e.g. {'Requires': 'xlrd, lk-logger, xlsxwriter', ...} -> [
            #       'xlrd', 'lk-logger', 'xlsxwriter']
        else:
            return []
    
    def show_locations(self, name) -> Set[str]:
        ret = send_cmd(self.get_pip_cmd('show', name, '-f'))
        r''' e.g.
            Name: lk-logger
            Version: 3.6.3
            Summary: Advanced logger with source code lineno indicator.
            Home-page:
            Author: Likianta
            Author-email: likianta@foxmail.com
            License: MIT
            Location: e:\programs\python\python39\lib\site-packages
            Requires:
            Required-by: pyportable-installer, lk-utils, lk-qtquick-scaffold
            Files:
              lk_logger-3.6.3.dist-info\INSTALLER
              lk_logger-3.6.3.dist-info\METADATA
              lk_logger-3.6.3.dist-info\RECORD
              lk_logger-3.6.3.dist-info\REQUESTED
              lk_logger-3.6.3.dist-info\WHEEL
              lk_logger\__init__.py
              lk_logger\__pycache__\__init__.cpython-39.pyc
              lk_logger\__pycache__\lk_logger.cpython-39.pyc
              lk_logger\lk_logger.py
        '''
        ret = safe_load(ret.replace('Files:', 'Files: |'))
        ''' -> {
                'Name': 'lk-logger',
                ...
                'Files': 'xxx\nxxx\nxxx\n...'
            }
        '''
        
        # analyse files root dirs
        out = set()
        for f in ret['Files'].split('\n'):
            if f == '':
                continue
            if f.startswith('.'):
                #   e.g. '..\..\Scripts\vba_extract.py'
                assert f.startswith('..\\..\\Scripts\\')
                out.add('../../Scripts/{}'.format(
                    normpath(f[14:]).split('/', 1)[0]
                ))
            else:
                out.add(normpath(f).split('/', 1)[0])
        return out
    
    # def analyse(self, name):
    #     ret = send_cmd(self.get_pip_cmd('show', name, '-f'))
    #     r''' e.g.
    #         Name: lk-logger
    #         Version: 3.6.3
    #         Summary: Advanced logger with source code lineno indicator.
    #         Home-page:
    #         Author: Likianta
    #         Author-email: likianta@foxmail.com
    #         License: MIT
    #         Location: e:\programs\python\python39\lib\site-packages
    #         Requires:
    #         Required-by: pyportable-installer, lk-utils, lk-qtquick-scaffold
    #         Files:
    #           lk_logger-3.6.3.dist-info\INSTALLER
    #           lk_logger-3.6.3.dist-info\METADATA
    #           lk_logger-3.6.3.dist-info\RECORD
    #           lk_logger-3.6.3.dist-info\REQUESTED
    #           lk_logger-3.6.3.dist-info\WHEEL
    #           lk_logger\__init__.py
    #           lk_logger\__pycache__\__init__.cpython-39.pyc
    #           lk_logger\__pycache__\lk_logger.cpython-39.pyc
    #           lk_logger\lk_logger.py
    #     '''
    #     ret = safe_load(ret.replace('Files:', 'Files: |'))
    #     ''' -> {
    #             'Name': 'lk-logger',
    #             ...
    #             'Files': 'xxx\nxxx\nxxx\n...'
    #         }
    #     '''
    #
    #     dependencies = ret['Requires'].split(', ')
    #     top_folders = set(split(f)[0] for f in ret['Files'].split('\n'))
    #     return dependencies, top_folders


class PipCmdTemplate:
    
    def __init__(
            self,
            pip,
            local,
            offline=False,
            pypi_url='https://pypi.python.org/simple/',
            pyversion=src_struct.pyversion,
            cache_dir=src_struct.cache,
            quiet=False,
    ):
        if offline is False:
            assert pypi_url
            host = re.search(r'https?://([^/]+)', pypi_url).group(1)
        else:
            host = ''
        
        # setup options
        self._template = pip + ' {action} {name} {options}'
        
        self._general_options = (
            f'--cache-dir="{cache_dir}"',
            f'--disable-pip-version-check',
            f'--no-python-version-warning',
            f'--quiet' if quiet else '',
            f'--trusted-host {host}' if host else '',
        )
        
        from .utils import pyversion_2_num
        self._pkg_idx_options = (
            f'--find-links="{local}"' if local else '',
            f'--index-url {pypi_url}' if not offline else '',
            f'--no-index' if offline else '',
            f'--only-binary=:all:',
            f'--python-version {pyversion_2_num(pyversion)}' if pyversion else '',
        )
    
    @property
    def template(self):
        return self._template
    
    @property
    def general_options(self):
        return ' '.join(self._general_options)
    
    @property
    def pkg_idx_options(self):
        return ' '.join(self._pkg_idx_options)
    
    def get_pip_cmd(self, action, name,
                    *custom_options,
                    add_general_options=True,
                    add_pkg_idx_options=False):
        options = []
        options.extend(custom_options)
        if add_general_options:
            options.extend(self._general_options)
        if add_pkg_idx_options:
            options.extend(self._pkg_idx_options)
        
        out = self._template.format(
            action=action, name=name, options=' '.join(options)
        )
        # lk.logt('[D2023]', out)
        return out


# if True:
#     from os.path import exists
#     from lk_utils import loads
#     from .path_struct import conf_dir
#
#     _options = {'quiet': False}
#     if exists(f := f'{conf_dir}/internal.yaml'):
#         _options.update(loads(f)['pip_options'])

_options = {'quiet': False}

default_pip = Pip(
    f'{src_struct.interpreter} -m pip',
    src_struct.downloads, **_options
)
