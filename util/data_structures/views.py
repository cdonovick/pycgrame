import weakref

from collections.abc import Mapping, Sequence, Set
'''A collection of adabters to make immutable data structures'''

class MapView(Mapping):
    __slot__ = '_ref', '__weakref__'

    def __init__(self, map):
        if not isinstance(map, Mapping):
            raise ValueError()
        self._ref = weakref.ref(map)

    def __getitem__(self, idx):
        map = self._ref()
        try:
            return map.__getitem__(idx)
        except AttributeError as e:
            if map is None:
                raise RuntimeError('Viewed object has been garbage collected')
            else:
                raise e

    def __iter__(self):
        map = self._ref()
        try:
            return map.__iter__()
        except AttributeError as e:
            if map is None:
                raise RuntimeError('Viewed object has been garbage collected')
            else:
                raise e

    def __len__(self):
        map = self._ref()
        try:
            return map.__len__()
        except AttributeError as e:
            if map is None:
                raise RuntimeError('Viewed object has been garbage collected')
            else:
                raise e

    def __repr__(self):
        map = self._ref()
        try:
            return f'{self.__class__.__name__}({map.__repr__()})'
        except AttributeError as e:
            if map is None:
                raise RuntimeError('Viewed object has been garbage collected')
            else:
                raise e

    def keys(self):
        map = self._ref()
        try:
            return map.keys()
        except AttributeError as e:
            if map is None:
                raise RuntimeError('Viewed object has been garbage collected')
            else:
                raise e

    def values(self):
        map = self._ref()
        try:
            return map.values()
        except AttributeError as e:
            if map is None:
                raise RuntimeError('Viewed object has been garbage collected')
            else:
                raise e

    def items(self):
        map = self._ref()
        try:
            return map.items()
        except AttributeError as e:
            if map is None:
                raise RuntimeError('Viewed object has been garbage collected')
            else:
                raise e



class SequenceView(Sequence):
    __slot__ = '_ref', '__weakref__'

    def __init__(self, seq):
        if not isinstance(seq, Sequence):
            raise ValueError()
        self._ref = weakref.ref(seq)

    def __getitem__(self, idx):
        seq = self._ref()
        try:
            return seq.__getitem__(idx)
        except AttributeError as e:
            if seq is None:
                raise RuntimeError('Viewed object has been garbage collected')
            else:
                raise e

    def __len__(self):
        seq = self._ref()
        try:
            return seq.__len__()
        except AttributeError as e:
            if seq is None:
                raise RuntimeError('Viewed object has been garbage collected')
            else:
                raise e

    def __repr__(self):
        seq = self._ref()
        try:
            return f'{self.__class__.__name__}({seq.__repr__()})'
        except AttributeError as e:
            if seq is None:
                raise RuntimeError('Viewed object has been garbage collected')
            else:
                raise e

class SetView(Set):
    __slot__ = '_ref', '__weakref__'

    def __init__(self, set_):
        if not isinstance(set_, Set):
            raise ValueError()
        self._ref = weakref.ref(set_)

    def __contains__(self, elem):
        set_ = self._ref()
        try:
            return set_.__contains__(elem)
        except AttributeError as e:
            if set_ is None:
                raise RuntimeError('Viewed object has been garbage collected')
            else:
                raise e

    def __iter__(self):
        set_ = self._ref()
        try:
            return set_.__iter__()
        except AttributeError as e:
            if set_ is None:
                raise RuntimeError('Viewed object has been garbage collected')
            else:
                raise e

    def __len__(self):
        set_ = self._ref()
        try:
            return set_.__len__()
        except AttributeError as e:
            if set_ is None:
                raise RuntimeError('Viewed object has been garbage collected')
            else:
                raise e
    
    def __repr__(self):
        set_ = self._ref()
        try:
            return f'{self.__class__.__name__}({set.__repr__()})'
        except AttributeError as e:
            if set_ is None:
                raise RuntimeError('Viewed object has been garbage collected')
            else:
                raise e
