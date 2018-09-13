import functools as ft
import typing as tp
import mrrg
import design
from mrrg import MRRG
from design import Design
from modeler import Modeler, Model
from constraints import ConstraintGeneratorType
from smt_switch_types import Solver, Term, Sort

EvalType = tp.Callable[[MRRG, Design, Model], int]
OptGeneratorType = tp.Callable[[int], ConstraintGeneratorType]

def count_muxes(cgra : MRRG, design : Design, vars : Model) -> int:
    used = set()
    for mux in cgra.routing_nodes:
        if not isinstance(mux, mrrg.Mux):
            continue
        for value in design.values:
            if vars[mux, value] == 1:
                assert mux not in used
                used.add(mux)
    return len(used)

def limit_muxes(n : int) -> ConstraintGeneratorType:
    p = ft.partial(_limit_muxes, n)
    p.__name__ = f'{limit_muxes.__name__}({n})'
    p.__qualname__ = f'{limit_muxes.__qualname__}({n})'
    return p

def _limit_muxes(n : int, cgra : MRRG, design : Design, vars : Model, solver : Solver) -> Term:
    c = 0
    for mux in cgra.routing_nodes:
        if isinstance(mux, mrrg.Mux):
            c += 1
    bv = solver.BitVec(max(c, n).bit_length() + 1)
    zero = solver.TheoryConst(bv, 0)
    one  = solver.TheoryConst(bv, 1)
    expr = None

    for mux in cgra.routing_nodes:
        if not isinstance(mux, mrrg.Mux):
            continue
        s_expr = None
        for value in design.values:
            if s_expr is None:
                s_expr = vars[mux, value]
            else:
                s_expr = solver.BVOr(s_expr, vars[mux, value])
        if expr is None:
            expr = solver.Ite(s_expr == 0, zero, one)
        else:
            expr = expr + solver.Ite(s_expr == 0, zero, one)

    if expr is not None:
        return expr <= n
    else:
        assert 0
        return True

def count_route(cgra : MRRG, design : Design, vars : Model) -> int:
    used = set()
    for node in cgra.routing_nodes:
        for value in design.values:
            if vars[node, value] == 1:
                assert node not in used
                used.add(node)
    return len(used)


def limit_route(n : int) -> ConstraintGeneratorType:
    p = ft.partial(_limit_route, n)
    p.__name__ = f'{limit_route.__name__}({n})'
    p.__qualname__ = f'{limit_route.__qualname__}({n})'
    return p

def _limit_route(n : int, cgra : MRRG, design : Design, vars : Model, solver : Solver) -> Term:
    bv = solver.BitVec(max(len(cgra.routing_nodes).bit_length(), n.bit_length()) +  1)
    zero = solver.TheoryConst(bv, 0)
    one  = solver.TheoryConst(bv, 1)
    expr = None

    for node in cgra.routing_nodes:
        s_expr = None
        for value in design.values:
            if s_expr is None:
                s_expr = vars[node, value]
            else:
                s_expr = solver.BVOr(s_expr, vars[node, value])
        if expr is None:
            expr = solver.Ite(s_expr == 0, zero, one)
        else:
            expr = expr + solver.Ite(s_expr == 0, zero, one)

    if expr is not None:
        return expr <= n
    else:
        assert 0
        return True

