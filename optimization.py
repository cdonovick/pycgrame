import functools as ft
import typing as tp
import mrrg
import design
from mrrg import MRRG
from design import Design
from modeler import Modeler, Model
from constraints import ConstraintGeneratorType
from smt_switch_types import Solver, Term, Sort
from util import term

EvalType = tp.Callable[[MRRG, Design, Model], int]
OptGeneratorType = tp.Callable[[int], ConstraintGeneratorType]

def init_popcount(node_filter : tp.Callable[[mrrg.Node], bool]) -> ConstraintGeneratorType:
    p = ft.partial(_init_popcount, node_filter)
    p.__name__ = f'{init_popcount.__name__}({node_filter.__name__})'
    p.__qualname__ = f'{init_popcount.__qualname__}({node_filter.__qualname__})'
    return p

# HACK OH GOD THE HACKINESS
__pop_count = None
def _init_popcount_ite(
        node_filter : tp.Callable[[mrrg.Node], bool],
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
    global __pop_count
    __pop_count = vars.init_var('pop_count', bv)
    return expr == __pop_count

def _init_popcount_concat(
        node_filter : tp.Callable[[mrrg.Node], bool],
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
    global __pop_count
    __pop_count = vars.init_var('pop_count', expr.sort)
    return expr == __pop_count

def _init_popcount_shannon(
        node_filter : tp.Callable[[mrrg.Node], bool],
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

def count(node_filter : tp.Callable[[mrrg.Node], bool]) -> EvalType:
    p = ft.partial(_count, node_filter)
    p.__name__ = f'{count.__name__}({node_filter.__name__})'
    p.__qualname__ = f'{count.__qualname__}({node_filter.__qualname__})'
    return p

def _count(
        node_filter : tp.Callable[[mrrg.Node], bool],
        cgra : MRRG,
        design : Design,
        vars : Model) -> int:

    s = sum(vars[node, value]
            for node in cgra.all_nodes
            for value in design.values
            if node_filter(node))
    return s

def limit_popcount(n : int) -> ConstraintGeneratorType:
    p = ft.partial(_limit_popcount, n)
    p.__name__ = f'{limit_popcount.__name__}({n})'
    p.__qualname__ = f'{limit_popcount.__qualname__}({n})'
    return p

def _limit_popcount_total(
        n : int,
        cgra : MRRG,
        design : Design,
        vars : Model,
        solver : Solver) -> Term:
    v = __pop_count
    if n < 0:
        assert 0
    elif n.bit_length() > v.sort.width:
        assert 0
    else:
        return solver.BVUle(v, n)

def _limit_popcount_shannon(
        n : int,
        cgra : MRRG,
        design : Design,
        vars : Model,
        solver : Solver) -> Term:

    if n < 0:
        assert 0
    elif n > len(__pop_count):
        assert 0
    else:
        v = __pop_count[n]
        return v == 1

def mux_filter(node : mrrg.Node) -> bool:
    return isinstance(node, mrrg.Mux)

def route_filter(node : mrrg.Node) -> bool:
    return not isinstance(node, mrrg.FunctionalUnit)

_init_popcount = _init_popcount_concat
_limit_popcount = _limit_popcount_total
