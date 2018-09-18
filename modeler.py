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
    _vars : tp.Mapping[tp.Any, Term]
    def __init__(self, solver : Solver):
        self._solver = solver
        self._vars = dict()

    def init_var(self, key, sort : Sort) -> Term:
        assert key not in self._vars
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
        self._vars : Model = dict()

    @classmethod
    def gen_name(cls) -> str:
        return f'V_{next(cls._var_counter)}'

    def anonymous_var(self, sort : Sort) -> Term:
        return self._solver.DeclareConst(self.gen_name(), sort)


def _get_path(
        model : Model,
        node : mrrg.Node,
        value : design.Value,
        dst : design.Operation,
        dst_node : mrrg.Node) -> tp.Iterable[mrrg.Node]:
    yield node
    if node != dst_node:
        next = None
        for n in node.outputs.values():
            if model[n, value, dst] == 1:
                assert next is None
                next = n
        assert next is not None
        yield from _get_path(model, next, value, dst, dst_node)


def model_checker(cgra : mrrg.MRRG, design : design.Design, vars : Model) -> None:
    F_map = BiDict()
    R_map = BiMultiDict()

    for op in design.operations:
        for pe in cgra.functional_units:
            if vars[pe, op] == 1:
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
        pe = F_map[op]
        value = op.output
        if value is not None:
            dsts = {(F_map[dst].operands[port]) for dst, port in value.dsts}
            assert pe in R_map[value]
            for dst in value.dsts:
                assert dst[0] in F_map
                dst_node = F_map[dst[0]].operands[dst[1]]
                node = pe
                for n in _get_path(vars, pe, value, dst, dst_node):
                    assert vars[n, value, dst] == 1

def model_info(cgra : mrrg.MRRG, design : design.Design, vars : Model) -> None:
    F_map = BiDict()

    for pe in cgra.functional_units:
        for op in design.operations:
            if vars[pe, op] == 1:
                F_map[op] = pe
                print(f'{op.name}({op.opcode}): {pe.name}')

    for op in design.operations:
        value = op.output
        if value is not None:
            pe = F_map[op]
            dsts = {(F_map[dst].operands[port]) for dst, port in value.dsts}
            for dst in value.dsts:
                assert dst[0] in F_map
                dst_node = F_map[dst[0]].operands[dst[1]]
                print(f'{op.name}->{dst[0].name}:{dst[1]}')
                for node in _get_path(vars, pe, value, dst, dst_node):
                    print(f'\t{node.name}')
