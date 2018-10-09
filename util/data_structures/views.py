import typing as tp
'''A collection of adabters to make immutable data structures'''

__all__ = ['CollectionView', 'MapView', 'SequenceView', 'SetView']

T_co = tp.TypeVar('T_co', covariant=True)
KT = tp.TypeVar('KT')
VT_co = tp.TypeVar('VT_co', covariant=True)

class CollectionView(tp.Collection[T_co]):
    __slots__ = '_obj',

    _obj : tp.Collection[T_co]

    def __init__(self, obj : tp.Collection[T_co]) -> None:
        self._obj = obj

    def __contains__(self, elem) -> bool:
        return self._obj.__contains__(elem)

    def __iter__(self) -> tp.Iterator[T_co]:
        return self._obj.__iter__()

    def __len__(self) -> int:
        return self._obj.__len__()

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self._obj.__repr__()})'


class MapView(CollectionView[KT], tp.Mapping[KT, VT_co]):
    __slots__ = ()

    _obj : tp.MutableMapping[KT, VT_co]

    def __getitem__(self, idx : KT) -> VT_co:
        return self._obj.__getitem__(idx)

    def values(self) -> tp.ValuesView[VT_co]:
        return self._obj.values()

class SequenceView(CollectionView[T_co], tp.Sequence[T_co]):
    __slots__ = ()

    _obj : tp.MutableSequence[T_co]

    @tp.overload
    def __getitem__(self, idx : int) -> T_co:
        ...

    @tp.overload
    def __getitem__(self, idx : slice) -> tp.Sequence[T_co]:
        ...

    def __getitem__(self, idx):
        return self._obj.__getitem__(idx)


class SetView(CollectionView[T_co], tp.AbstractSet[T_co]):
    __slots__ = ()
    _obj : tp.MutableSet[T_co]
