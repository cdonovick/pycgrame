import typing as tp
from util import IDObject, NamedIDObject, SortedDict
from util import BiMultiDict, MultiDict, SortedFrozenSet, MapView

class Value(IDObject):
    '''
       Holds a collection of ties that make up a net.
    '''
    _src  : tp.Optional['Operation']
    _dsts : tp.AbstractSet['Operation']

    def __init__(self, src, dsts=()):
        super().__init__()
        self._src = src
        src._set_output(self)

        self._dsts = frozenset(dsts)

        for dst, dst_port in dsts:
            dst._add_input(dst_port, self)

    @property
    def src(self) -> tp.Optional['Operation']:
        return self._src

    @property
    def dsts(self) -> tp.AbstractSet['Operation']:
        return self._dsts

    def __repr__(self) -> str:
        return f'{self.src} -> {self.dsts}'

class Operation(NamedIDObject):
    _inputs : tp.MutableMapping[str, Value]
    _output : tp.Optional[Value]
    _opcode : str
    _duplicate : bool

    def __init__(self, name : str, opcode :str):
        super().__init__(name)
        self._inputs = BiMultiDict()  # port <-> value
        self._output = None
        self._opcode = opcode
        self._duplicate = False

    @property
    def inputs(self) -> MapView[str, Value]:
        return MapView(self._inputs)

    def _add_input(self, port : str, val : Value) -> None:
        assert port not in self.inputs, '\n%s\n%s\n%s\n' % (self, port, val)
        self._inputs[port] = val

    def _set_output(self, val : Value) -> None:
        assert self.output is None
        self._output = val

    @property
    def output(self) -> tp.Optional[Value]:
        return self._output

    @property
    def opcode(self) -> str:
        return self._opcode

    @property
    def duplicate(self) -> bool:
        return self._duplicate

    def allow_duplicate(self):
        self._duplicate = True

class Design(NamedIDObject):
    def __init__(self, mods : dict, ties : set, name : str = ""):
        super().__init__(name)

        #build operations
        _ops = dict()
        for mod_name, opcode in mods.items():
            _ops[mod_name] = Operation(mod_name, opcode)

        #gather values
        _ties = MultiDict() # src -> (dst, dst_port)
        for src_name, dst_name, dst_port in ties:
            _ties[_ops[src_name]] = (_ops[dst_name], dst_port)


        #build actual val objects
        _values = set()
        for src in _ties:
            _values.add(Value(src, _ties[src]))

        self._operations = frozenset(_ops.values())
        self._values     = frozenset(_values)

    @property
    def operations(self) -> tp.AbstractSet[Operation]:
        return self._operations

    @property
    def values(self) -> tp.AbstractSet[Value]:
        return self._values
