import weakref

from abc import ABCMeta
from collections.abc import Mapping
import sys
from functools import reduce
import operator

class frozendict(Mapping):
    __slot__ = '_d', '__weakref__', '_hash'
    def __init__(self, *args, **kwargs):
        self._d = dict(*args, **kwargs)
        self._hash = None

    def __getitem__(self, key):
        return self._d.__getitem__(key)

    def __iter__(self):
        return self._d.__iter__()

    def __len__(self):
        return self._d.__len__()
    
    def __repr__(self):
        return f'{self.__class__.__name__}({self._d.__repr__()})'

    def _cached_hash(self):
        return self._hash

    def __hash__(self):
        if sys.hash_info.width >= 32:
            h = 1099511628211
        else: 
            h = 16777619
        self._hash = reduce(operator.xor, map(hash, self._d), h)
        self.__hash__ = self._cached_hash
        return self._hash

