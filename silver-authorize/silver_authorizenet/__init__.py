from ._version import get_versions
import tests
__version__ = get_versions()['version']
del get_versions
