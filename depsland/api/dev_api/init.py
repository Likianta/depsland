import os
import re
from os.path import exists

from lk_utils import dumps
from lk_utils import fs
from lk_utils import loads

from ...manifest import T
from ...manifest import init_manifest


def init(
    manifest_file: str = './manifest.json',
    appname='',
    overwrite=False,
    auto_find_requirements=False
) -> None:
    # init/update parameters
    filepath = fs.normpath(manifest_file, True)
    if exists(filepath):
        if overwrite:
            os.remove(filepath)
        else:
            print(':v3s', 'target already exists!', filepath)
            return
    
    dirpath = fs.parent_path(filepath)
    if not exists(dirpath):
        os.mkdir(dirpath)
        
    dirname = fs.dirname(dirpath)
    if appname == '':
        appname = dirname.replace('-', ' ').replace('_', ' ').title()
    appid = appname.replace(' ', '_').replace('-', '_').lower()
    print(':v2f2', appname, appid)
    
    manifest: T.Manifest = init_manifest(appid, appname)
    manifest.pop('start_directory')  # noqa
    manifest['version'] = '0.1.0'
    manifest['pypi'] = []
    
    if auto_find_requirements:
        if exists(x := f'{dirpath}/requirements.txt'):
            pattern = re.compile(r'([-\w]+)(.*)')
            deps = manifest['dependencies']
            for line in loads(x).splitlines():  # type: str
                if line and not line.startswith('#'):
                    name, ver = pattern.search(line).groups()
                    deps[name] = ver.replace(' ', '')
            print(deps, ':l')
    
    dumps(manifest, x := f'{dirpath}/manifest.json')
    print(f'see manifest file at \n\t"{x}"')
