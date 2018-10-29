import heapq
import itertools as it
import typing as tp
_C = it.count()
_REMOVED = object()
__ALL__ = ['PriorityQueue']


class MinHeap(tp.Sequence):
    __slots__ = ('h',)
    h : tp.MutableSequence
    def __init__(self):
        self.h = []

    def push(self, x):
        heapq.heappush(self.h, x)

    def pop(self):
        return heapq.heappop(self.h)

    def __getitem__(self, i):
        return self.h[i]

    def __len__(self):
        return len(self.h)

    def peek(self):
        return self.h[0]

class MaxHeap(MinHeap):
    __slots__ = ()
    def push(self, x):
        return super().push(MaxHeapObj(x))

    def pop(self):
        return super().pop().val

    def __getitem__(self, i):
        return super().__getitem__(i).val


class MaxHeapObj:
    __slots__ = ('val',)

    def __init__(self, val):
        self.val = val
    def __lt__(self, other):
        return self.val > other.val
    def __eq__(self, other):
        return self.val == other.val

class PriorityQueue(tp.MutableMapping[tp.Any, int]):
    def __init__(self, min=True):
        self._entry_finder = dict()
        if min:
            self._pq = MinHeap()
        else:
            self._pq = MaxHeap()

    def __getitem__(self, elem) -> int:
        entry = self._entry_finder[elem]
        if entry[-1] is _REMOVED:
            raise KeyError()
        else:
            assert entry[-1] == elem
            return entry[0]

    def __setitem__(self, elem, priority):
        if elem in self._entry_finder:
            del self[elem]
        entry = [priority, next(_C), elem]
        self._entry_finder[elem] = entry
        self._pq.push(entry)

    def __delitem__(self, elem):
        entry = self._entry_finder.pop(elem)
        entry[-1] = _REMOVED


    def pop(self):
        return self.popitem()[0]

    def popitem(self):
        pq = self._pq
        while pq:
            priority, _, elem = pq.pop()
            if elem is not _REMOVED:
                del self._entry_finder[elem]
                return elem, priority
        raise KeyError()

    def __len__(self):
        return self._entry_finder.__len__()

    def __iter__(self):
        for priority, _,elem in self._entry_finder.values():
            assert entry[-1] is not _REMOVED
            yield elem

    def peekitem(self):
        pq = self._pq
        while pq:
            priority, _, elem = pq.peek()
            if elem is not _REMOVED:
                return elem, priority
            pq.pop()

    def peek(self):
        return self.peekitem()[0]



