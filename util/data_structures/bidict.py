from collections.abc import MutableMapping

__all__ = ['BiDict']

class BiDict(MutableMapping):
    __slots__ = '_d', '_i', '__weakref__'
    def __init__(self, d=dict()):
        self._d = dict()
        self._i = dict()

        for k,v in d.items():
            self[k] = v

    def __getitem__(self, key):
        return self._d[key]

    def __setitem__(self, key, val):
        if key in self._d:
            del self[key]
        if val in self._i:
            del self.I[val]
            #raise ValueError(f'{val} is bound to {self._i[val]}'

        self._d[key] = val
        self._i[val] = key
        #self._attest()

    def __delitem__(self, key):
        if key not in self._d:
            raise KeyError()

        val = self._d[key]
        del self._i[val]
        del self._d[key]
        #self._attest()

    def __iter__(self):
        yield from self._d.keys()

    def __repr__(self):
        c = []
        for k,v in self.items():
            c.append('{}:{}'.format(k,v))
        s = 'BiDict({' + ', '.join(c) + '})'
        return s

    def __len__(self):
        return len(self._d)

    @property
    def I(self):
        t = BiDict()
        t._d = self._i
        t._i = self._d
        #t._attest()
        return t

    def _attest(self):
        for k,v in self._d.items():
            assert v in self._i
            assert k == self._i[v], '\nk: %s\nv: %s\n%s' % (k, v, self._i[v])


        for k,v in self._i.items():
            assert v in self._d
            assert k == self._d[v]
