from util import IDObject, NamedIDObject, SortedDict
from util import BiMultiDict, MultiDict, SortedFrozenSet

class Value(IDObject):
    '''
       Holds a collection of ties that make up a net.
    '''
    def __init__(self, src, dsts=()):
        super().__init__()
        self._src = src
        src._set_output(self)

        self._dsts = frozenset(dsts)

        for dst, dst_port in dsts:
            dst._add_input(dst_port, self)

    @property
    def src(self):
        return self._src

    @property
    def dsts(self):
        return self._dsts

    def __repr__(self):
        return f'{self.src} -> {self.dsts}'

class Operation(NamedIDObject):
    def __init__(self, name : str, opcode :str):
        super().__init__(name)
        self._inputs = BiMultiDict()  # port <-> value
        self._output = None
        self._opcode = opcode

    @property
    def inputs(self) -> BiMultiDict:
        return self._inputs

    def _add_input(self, port, net) -> None:
        assert port not in self.inputs, '\n%s\n%s\n%s\n' % (self, port, net)
        self._inputs[port] = net

    def _set_output(self, net) -> None:
        assert self.output is None
        self._output = net

    @property
    def output(self):
        return self._output

    @property
    def opcode(self):
        return self._opcode

    @property
    def duplicate(self):
        #return False
        return self.opcode == 'const'

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

        self._operations = SortedFrozenSet(_ops.values())
        self._values     = SortedFrozenSet(_values)

    @property
    def operations(self) -> SortedFrozenSet:
        return self._operations

    @property
    def values(self) -> SortedFrozenSet:
        return self._values
