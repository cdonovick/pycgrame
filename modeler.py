import typing as tp
import itertools as it
from collections.abc import Mapping
import mrrg
import design
from smt_switch_types import Solver, Term, Sort
from util import BiDict, BiMultiDict

Model = tp.Mapping[tp.Any, int]
ModelReader = tp.Callable[[mrrg.MRRG, design.Design, Model], tp.Any]

class Modeler(Mapping):
    _var_counter = it.count()
    _solver : Solver
    _vars : tp.MutableMapping[tp.Any, Term]

    def __init__(self, solver : Solver):
        self._solver = solver
        self._vars = dict()

    def init_var(self, key, sort : Sort) -> Term:
        assert key not in self._vars, key
        self._vars[key] = t = self.anonymous_var(sort)
        return t

    def __getitem__(self, key) -> Term:
        return self._vars.__getitem__(key)

    def __iter__(self) -> tp.Iterator:
        return self._vars.__iter__()

    def __len__(self) -> int:
        return self._vars.__len__()

    def save_model(self) -> Model:
        solver = self._solver
        d = dict()
        for k,v in self._vars.items():
            d[k] = solver.GetValue(v).as_int()

        return d

    def reset(self) -> None:
        self._vars = dict()

    @classmethod
    def gen_name(cls) -> str:
        return f'V_{next(cls._var_counter)}'

    def anonymous_var(self, sort : Sort) -> Term:
        return self._solver.DeclareConst(self.gen_name(), sort)


def _get_path(
        model : Model,
        src_node : mrrg.Node,
        value : design.Value,
        dst : tp.Tuple[design.Operation, int],
        dst_node : mrrg.Node) -> tp.Iterable[mrrg.Node]:
    assert dst in value.dsts
    path = []
    node = dst_node
    while node != src_node:
        path.append(node)
        next = None
        for n in node.inputs.values():
            if model[n, value, dst] == 1:
                assert next is None
                next = n
        if next is None:
            return
        node = next
    path.append(src_node)
    yield from reversed(path)

def model_checker(cgra : mrrg.MRRG, design : design.Design, vars : Model) -> None:
    F_map = BiMultiDict()
    R_map = BiMultiDict()

    for op in design.operations:
        for pe in cgra.functional_units:
            if vars[pe, op] == 1:
                if not op.duplicate:
                    assert op not in F_map
                    assert pe not in F_map.I
                F_map[op] = pe
        assert op in F_map

    for node in cgra.all_nodes:
        for value in design.values:
            if vars[node, value] == 1:
                assert node not in R_map.I
                R_map[value] = node

    for node in cgra.all_nodes:
        for value in design.values:
            for dst in value.dsts:
                if vars[node, value, dst] == 1:
                    assert vars[node, value] == 1

    for op in design.operations:
        value = op.output
        if value is not None:
            for dst in value.dsts:
                assert dst[0] in F_map
                for _dst_node in F_map[dst[0]]:
                    dst_node = _dst_node.operands[dst[1]]
                    reached = False
                    for pe in F_map[op]:
                        assert pe in R_map[value]
                        if vars[pe, value, dst]:
                            for n in _get_path(vars, pe, value, dst, dst_node):
                                assert vars[n, value, dst] == 1
                                if n == dst_node:
                                    assert not reached
                                    reached = True
                    assert reached

def routing_stats(cgra : mrrg.MRRG, design : design.Design, vars : Model) -> None:
    F_map = BiMultiDict()

    for pe in cgra.functional_units:
        for op in design.operations:
            if vars[pe, op] == 1:
                F_map[op] = pe
    reg = set()
    mux = set()
    for op in design.operations:
        value = op.output
        if value is not None:
            for pe in F_map[op]:
                for dst in value.dsts:
                    assert dst[0] in F_map
                    for _dst_node in F_map[dst[0]]:
                        dst_node = _dst_node.operands[dst[1]]
                        for node in _get_path(vars, pe, value, dst, dst_node):
                            if isinstance(node, mrrg.Register):
                                reg.add(node)
                            elif isinstance(node, mrrg.Mux):
                                mux.add(node)

    print(f'Total muxes: {len(mux)}')
    print(f'Total register: {len(reg)}')


def model_info(cgra : mrrg.MRRG, design : design.Design, vars : Model) -> None:
    F_map = BiMultiDict()

    for op in design.operations:
        for pe in cgra.functional_units:
            if vars[pe, op] == 1:
                F_map[op] = pe
                print(f'{op.name}({op.opcode}): {pe.name}')

    for op in design.operations:
        value = op.output
        if value is not None:
            for dst in value.dsts:
                assert dst[0] in F_map
                for _dst_node in F_map[dst[0]]:
                    dst_node = _dst_node.operands[dst[1]]
                    for pe in F_map[op]:
                        if vars[pe, value, dst]:
                            print(f'{op.name}->{dst[0].name}:{dst[1]}')
                            for n in _get_path(vars, pe, value, dst, dst_node):
                                assert vars[n, value, dst] == 1
                                print(f'\t{n.name}')


