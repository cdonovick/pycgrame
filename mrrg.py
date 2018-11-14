import typing as tp
from util.data_structures import make_restricted, BiDict, BiMultiDict, MapView, RestrictedDict
from util import IDObject, NamedIDObject

from abc import ABCMeta, abstractmethod

_R_BiMultiDict = make_restricted(BiMultiDict)

class Node(NamedIDObject, metaclass=ABCMeta):
    @abstractmethod
    def __init__(self,
                name : str,
                input_ports  : tp.Set[str],
                output_ports : tp.Set[str],
            ):
        super().__init__(name)
        assert not (input_ports & output_ports)
        self._inputs = _R_BiMultiDict(input_ports)
        self._outputs = _R_BiMultiDict(output_ports)

    @property
    def input_ports(self) -> tp.Set[str]:
        return self._inputs.valid_keys()

    @property
    def output_ports(self) -> tp.Set[str]:
        return self._outputs.valid_keys()


    @property
    def inputs(self) -> tp.Mapping[str, 'Node']:
        return MapView(self._inputs)

    @property
    def outputs(self) -> tp.Mapping[str, 'Node']:
        return MapView(self._outputs)

class FunctionalUnit(Node):
    def __init__(self,
            name : str,
            input_ports  : tp.Set[str],
            output_ports : tp.Set[str],
            op           : tp.Set[str],
            ):
        super().__init__(name, input_ports, output_ports)
        self.ops = op
        self._operands = RestrictedDict(range(len(input_ports)))

    @property
    def operands(self) -> tp.Mapping[str, 'FU_Port']:
        return MapView(self._operands)


class _LineNode(Node):
    def __init__(self,
            name : str,
            input_ports  : tp.Set[str],
            output_ports : tp.Set[str],
            ):
        assert len(output_ports) == len(input_ports) == 1
        super().__init__(name, input_ports, output_ports)

    @property
    def input(self):
        for input in self.inputs.values(): return input

    @property
    def input_port(self):
        for input in self.input_ports: return input

    @property
    def output_port(self):
        for output in self.output_ports: return output


class FU_Port(_LineNode):
    def __init__(self,
            name : str,
            input_ports  : tp.Set[str],
            output_ports : tp.Set[str],
            operand : str,
            ):
        super().__init__(name, input_ports, output_ports)
        self.operand = operand

    @property
    def output(self):
        assert len(self.outputs) == 1
        for output in self.outputs.values(): return output

class Register(_LineNode):
    def __init__(self,
            name : str,
            input_ports  : tp.Set[str],
            output_ports : tp.Set[str],
            ):
        super().__init__(name, input_ports, output_ports)


class Mux(Node):
    def __init__(self,
            name : str,
            input_ports  : tp.Set[str],
            output_ports : tp.Set[str],
            ):
        super().__init__(name, input_ports, output_ports)

def wire(src : Node, src_port : str, dst : Node, dst_port : str):
    src._outputs[src_port] = dst
    assert (dst_port not in dst.inputs) or (dst.inputs[dst_port] == src), \
            (dst, dst.inputs[dst_port], src)
    dst._inputs[dst_port] = src
    if isinstance(dst, FunctionalUnit):
        assert isinstance(src, FU_Port)
        assert src.operand not in dst.operands
        dst._operands[src.operand] = src

def unwire(src : Node, src_port : str, dst : Node, dst_port : str):
    assert (src_port, dst) in src._outputs.items()
    src._outputs.del_kvpair(src_port, dst)
    assert (src_port, dst) not in src.outputs.items()

    assert (dst_port, src) in dst._inputs.items()
    del dst._inputs[dst_port]
    assert (dst_port, src) not in dst.inputs.items()

    if isinstance(dst, FunctionalUnit):
        assert src.operand in dst.operands
        del dst._operands[src.operand]



class MRRG:
    def __init__(self, cgra, *, contexts=1):
        all = dict()
        route = dict()
        fu = dict()


        reg = dict()
        mux = dict()

        for i in range(contexts):
            for loc, block in cgra.blocks.items():
                for inst in block.instances.values():
                    idx = i, loc, inst
                    name = f'{inst.type_}_{inst.name}_{i}_{loc[0]}_{loc[1]}'
                    if inst.type_ == 'Register':
                        all[idx] = route[idx] = reg[idx] = Register(name, inst.input_ports, inst.output_ports)
                    else:
                        all[idx] = fu[idx] = FunctionalUnit(name, inst.input_ports, inst.output_ports, **inst.args)

                for inst in block.muxes.values():
                    name = f'Mux_{inst.name}_{i}_{loc[0]}_{loc[1]}'
                    idx = i, loc, inst
                    all[idx] = route[idx] = mux[idx] = Mux(name, inst.input_ports, inst.output_ports)

                for inst in block.ports.values():
                    name = f'Port_{inst.name}_{i}_{loc[0]}_{loc[1]}'
                    idx = i, loc, inst
                    all[idx] = route[idx] = FU_Port(name, inst.input_ports, inst.output_ports, inst.operand)

        for i in range(contexts):
            for src_address, dst_address in cgra.ties.items():
                if src_address is None:
                    continue
                src_loc, src_inst, src_port = src_address
                dst_loc, dst_inst, dst_port = dst_address
                src = all[i, src_loc, src_inst]
                if isinstance(src, Register):
                    dst = all[(i+1)%contexts, dst_loc, dst_inst]
                else:
                    dst = all[i, dst_loc, dst_inst]

                wire(src, src_port, dst, dst_port)

        self._route = route
        self._all = all
        self._fu = fu

    @property
    def functional_units(self) -> tp.ValuesView[FunctionalUnit]:
        return self._fu.values()

    @property
    def routing_nodes(self) -> tp.ValuesView[tp.Union[Mux, Register, FU_Port]]:
        return self._route.values()

    @property
    def all_nodes(self) -> tp.ValuesView[Node]:
        return self._all.values()

