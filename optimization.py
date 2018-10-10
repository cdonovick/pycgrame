from abc import ABCMeta, abstractmethod
import functools as ft
import itertools as it
import typing as tp
import mrrg
import design
from mrrg import MRRG, Node
from design import Design, Operation
from modeler import Modeler, Model, _get_path
from constraints import ConstraintGeneratorType
from smt_switch_types import Solver, Term, Sort
from util import BiDict, BiMultiDict
from util import AutoPartial

EvalType = tp.Callable[[MRRG, Design, Model], int]
OptGeneratorType = tp.Callable[[int, int], ConstraintGeneratorType]
NodeFilter = tp.Callable[[Node], bool]

T = tp.TypeVar('T')
WrappedType = tp.Callable[[NodeFilter], T]

class Optimizer:
    init_func  : ConstraintGeneratorType
    eval_func  : EvalType
    limit_func : OptGeneratorType

    def __init__(self,
            node_filter   : NodeFilter,
            init_wrapper  : WrappedType[ConstraintGeneratorType],
            eval_wrapper  : WrappedType[EvalType],
            limit_wrapper : WrappedType[OptGeneratorType],
            ):

        self.init_func  = init_wrapper(node_filter)
        self.eval_func  = eval_wrapper(node_filter)
        self.limit_func = limit_wrapper(node_filter)


@AutoPartial(1)
def init_popcount_ite(
        node_filter : NodeFilter,
        cgra : MRRG,
        design : Design,
        vars : Modeler,
        solver : Solver) -> Term:

    nodes = [n for n in cgra.all_nodes if node_filter(n)]
    bv = solver.BitVec(len(nodes).bit_length())
    zero = solver.TheoryConst(bv, 0)
    one  = solver.TheoryConst(bv, 1)

    expr = ft.reduce(solver.BVAdd,
            map(lambda x : solver.Ite(x == 0, zero, one),
                (ft.reduce(solver.BVOr,
                    (vars[n, v] for v in design.values)
                ) for n in nodes)
            )
        )

    pop_count = vars.init_var(node_filter, bv)
    return expr == pop_count

@AutoPartial(1)
def init_popcount_concat(
        node_filter : NodeFilter,
        cgra : MRRG,
        design : Design,
        vars : Modeler,
        solver : Solver) -> Term:

    nodes = [n for n in cgra.all_nodes if node_filter(n)]
    width = len(nodes).bit_length()
    zero = solver.TheoryConst(solver.BitVec(width - 1), 0)
    zeroExt = ft.partial(solver.Concat, zero)
    expr = ft.reduce(solver.BVAdd,
            map(zeroExt,
                (ft.reduce(solver.BVOr,
                    (vars[n, v] for v in design.values)
                ) for n in nodes)
            )
        )

    pop_count = vars.init_var(node_filter, expr.sort)
    return expr == pop_count

@AutoPartial(1)
def init_popcount_bithack(
        node_filter : NodeFilter,
        cgra : MRRG,
        design : Design,
        vars : Modeler,
        solver : Solver) -> Term:

    def _build_grouped_mask(k, n):
        '''
        build_grouped_mask :: int -> int -> Term
        returns the unique int m of length n that matches the following RE
        ((0{0,k} 1{k}) | (1{0,k})) (0{k} 1{k})*
        '''
        m = 0
        for i in range(k):
            m |= 1 << i
        c = 2*k
        while c < n:
            m |= m << c
            c *= 2
        return solver.TheoryConst(solver.BitVec(n), m)

    def _is_power_of_2(x : int) -> bool:
        return x & (x - 1) == 0

    def _floor_log2(x : int) -> int:
        return x.bit_length() - 1

    def _prev_power_of_2(x : int) -> int:
        return 1 << _floor_log2(x - 1)

    def _next_power_of_2(x : int) -> int:
        return 1 << x.bit_length()


    constraints = []
    vs = [vars[n, v] for n in cgra.all_nodes if node_filter(n) for v in design.values]
    width = len(vs)
    # build a bitvector from the concanation of bits
    bv = vars.anonymous_var(solver.BitVec(width))

    for idx,v in enumerate(vs):
        constraints.append(bv[idx] == v)

    # Boolector can't handle lshr on non power of 2, so zero extend
    if solver.solver_name == 'Boolector' and not _is_power_of_2(width):
        l = _next_power_of_2(width)
        bv = solver.Concat(solver.TheoryConst(solver.BitVec(l - width), 0), bv)

    width = bv.sort.width
    pop_count = vars.init_var(node_filter, bv.sort)

    if width <= 1:
        constraints.append(pop_count == bv)
        return solver.And(constraints)
    elif width == 2:
        constraints.append(pop_count == (bv & 1) + (bv >> 1))
        return solver.And(constraints)

    max_shift = _prev_power_of_2(width)

    def _mask_shift_add(x, shift):
        mask = _build_grouped_mask(shift, width)
        return (x & mask) + ((x >> shift) & mask)

    shifts = it.takewhile(lambda n : n <= max_shift, (1 << i for i in it.count()))
    x = ft.reduce(_mask_shift_add, shifts, bv)

    constraints.append(pop_count == x)
    return solver.And(constraints)


# HACK OH GOD THE HACKINESS
__pop_count = None
@AutoPartial(1)
def init_popcount_shannon(
        node_filter : NodeFilter,
        cgra : MRRG,
        design : Design,
        vars : Modeler,
        solver : Solver) -> Term:
    nodes = []
    for node in cgra.all_nodes:
        if node_filter(node):
            for value in design.values:
                v = vars[node, value]
                v = ~v
                nodes.append(v)
    it = iter(enumerate(nodes))

    c = []
    _, x = next(it)
    c.append(x)

    for k, x in it:
        t = x & c[-1]
        for i in range(k - 1, 0, -1):
            c[i] = c[i] | (c[i-1] & x)
        c[0] = c[0] | x
        c.append(t)

    c = list(reversed(c))
    global __pop_count
    __pop_count = c
    return True


@AutoPartial(1)
def count(
        node_filter : NodeFilter,
        cgra : MRRG,
        design : Design,
        vars : Model) -> int:

    s = sum(vars[node, value]
            for node in cgra.all_nodes
            for value in design.values
            if node_filter(node))
    return s

@AutoPartial(1)
def smart_count(
        node_filter : NodeFilter,
        cgra : MRRG,
        design : Design,
        vars : Model) -> int:

    F_map = BiMultiDict()

    for pe in cgra.functional_units:
        for op in design.operations:
            if vars[pe, op] == 1:
                F_map[op] = pe
    used = set()
    for op in design.operations:
        value = op.output
        if value is not None:
            for pe in F_map[op]:
                for dst in value.dsts:
                    for _dst_node in F_map[dst[0]]:
                        dst_node = _dst_node.operands[dst[1]]
                        for node in _get_path(vars, pe, value, dst, dst_node):
                            if node_filter(node):
                                used.add(node)
    return len(used)


@AutoPartial(1) #node_filter
@AutoPartial(3) #l, n
def limit_popcount_total(
        node_filter : NodeFilter,
        l : int,
        n : int,
        cgra : MRRG,
        design : Design,
        vars : Modeler,
        solver : Solver) -> Term:
    v = vars[node_filter]
    if n < 0 or n < l:
        assert 0
    elif n.bit_length() > v.sort.width or l.bit_length() > v.sort.width:
        assert 0
    else:
    #    return solver.BVUle(v, n)
        return solver.And(solver.BVUle(l, v), solver.BVUle(v, n))


@AutoPartial(1)
@AutoPartial(3)
def limit_popcount_shannon(
        node_filter : NodeFilter,
        l : int,
        n : int,
        cgra : MRRG,
        design : Design,
        vars : Modeler,
        solver : Solver) -> Term:

    if n < 0:
        assert 0
    elif n > len(__pop_count):
        assert 0
    else:
        v = __pop_count[n]
        return v == 1


def mux_filter(node : Node) -> bool:
    return isinstance(node, mrrg.Mux)

def mux_reg_filter(node :  Node) -> bool:
    return isinstance(node, (mrrg.Mux, mrrg.Register))

def route_filter(node : Node) -> bool:
    return not isinstance(node, mrrg.FunctionalUnit)

def no_filter(node : Node) -> bool:
    return True
