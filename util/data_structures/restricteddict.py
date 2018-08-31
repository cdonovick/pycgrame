from collections import UserDict
from collections.abc import MutableMapping
from abc import ABCMeta, abstractmethod
from functools import wraps
from .views import SetView
__ALL__ = ['RestrictedDict']

class RestrictedDictMixin(MutableMapping, metaclass=ABCMeta):
    __slots__ = ()

    @abstractmethod
    def valid_keys(self):
        pass

    @classmethod
    def __init_subclass__(cls, **kwargs): 
        _setitem = cls.__setitem__
        @wraps(_setitem)
        def __setitem__(self, key, value):
            if key not in self.valid_keys():
                raise KeyError(f'Invalid Key: {key}')
            return _setitem(self, key, value)
        cls.__setitem__ = __setitem__
        
        _setdefault = cls.setdefault
        @wraps(_setdefault)
        def setdefault(self, key, default=None):
            if key not in self.valid_keys():
                raise KeyError(f'Invalid Key: {key}')
            return _setdefault(self, key, default)
            
        cls.setdefault = setdefault
        super().__init_subclass__(**kwargs)


_RESTICTED_TYPES = dict()
def make_restricted(base_dict):
    try:
        return _RESTICTED_TYPES[base_dict]    
    except KeyError:
        return _make_restriced(base_dict)


def _make_restriced(base_dict):
    class RestrictedDict(RestrictedDictMixin):
        __slots__ = ('_d', '_valid_keys', '__weakref__')

        def __init__(self, valid_keys, d={}):
            self._valid_keys = set(valid_keys)
            self._d = base_dict()
            self.update(d)

        def valid_keys(self):
            return SetView(self._valid_keys)

        def __getitem__(self, key):
            return self._d.__getitem__(key)

        def __setitem__(self, key, val):
            return self._d.__setitem__(key, val)

        def __delitem__(self, key):
            return self._d.__delitem__(key)

        def __iter__(self):
            return self._d.__iter__()

        def __len__(self):
            return self._d.__len__()

        def __repr__(self):
            return f'{self.__class__.__name__}({self._valid_keys}, {self._d})'

        def keys(self):
            return self._d.keys()
        def items(self):
            return self._d.items()
        def values(self):
            return self._d.values()

        def __getattr__(self, attr):
            return self._d.__getattribute__(attr)
    return _RESTICTED_TYPES.setdefault(base_dict, RestrictedDict)


RestrictedDict = make_restricted(dict)
