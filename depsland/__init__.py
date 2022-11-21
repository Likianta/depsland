if True:
    import lk_logger
    lk_logger.setup(quiet=True, show_varnames=True)

from . import api
from . import config
from . import launcher
from . import manifest
from . import paths
from . import utils
from .api import init
from .api import install
from .api import publish
from .pip import Pip
from .pip import pip
from .pypi import pypi
from .utils import bat_2_exe

__version__ = '0.3.6b2'
__date__ = '2021-11-21'
