import typing as tp
import mrrg
import design
import functools as ft
from mrrg import MRRG
from design import Design
from modeler import Modeler
from smt_switch_types import Solver, Term, Sort
import sys

ConstraintGeneratorType = tp.Callable[[MRRG, Design, Modeler, Solver], Term]

def init_placement_vars(cgra : MRRG, design : Design, vars : Modeler, solver : Solver) -> Term:
    bv1 = solver.BitVec(1)
    for pe in cgra.functional_units:
        for op in design.operations:
            vars.init_var((pe, op), bv1)
    return solver.TheoryConst(solver.Bool(), True)

def init_routing_vars(cgra : MRRG, design : Design, vars : Modeler, solver : Solver) -> Term:
    bv1 = solver.BitVec(1)
    for node in cgra.all_nodes:
        for value in design.values:
            vars.init_var((node, value), bv1)
            for dst in value.dsts:
                vars.init_var((node, value, dst), bv1)
    return solver.TheoryConst(solver.Bool(), True)

def _is_one_hot_or_0(var : Term, solver : Solver):
    return (var & (var - 1)) == solver.TheoryConst(var.sort, 0)

def _is_one_hot(var : Term, solver : Solver) -> Term:
    return solver.And(_is_one_hot_or_0(var, solver), var != solver.TheoryConst(var.sort, 0))

def op_placement(cgra : MRRG, design : Design, vars : Modeler, solver : Solver) -> Term:
    ''' Assert all ops are placed exactly one time
    unless they can be duplicated in which case assert they are placed '''
    bv = solver.BitVec(len(cgra.functional_units))
    c = []
    for op in design.operations:
        if op.duplicate:
            c.append(ft.reduce(solver.BVOr, (vars[pe, op] for pe in cgra.functional_units)) == 1)
        else:
            op_vars = vars.anonymous_var(bv)
            for idx,pe in enumerate(cgra.functional_units):
                c.append(op_vars[idx] == vars[pe, op])
            c.append(_is_one_hot(op_vars, solver))

    return solver.And(c)

def pe_exclusivity(cgra : MRRG, design : Design, vars : Modeler, solver : Solver) -> Term:
    ''' Assert all PEs are used at most one time '''
    bv = solver.BitVec(len(design.operations))
    c = []
    for pe in cgra.functional_units:
        pe_vars = vars.anonymous_var(bv)
        for idx, op in enumerate(design.operations):
            c.append(pe_vars[idx] == vars[pe, op])
        c.append(_is_one_hot_or_0(pe_vars, solver))

    return solver.And(c)

def pe_legality(cgra : MRRG, design : Design, vars : Modeler, solver : Solver) -> Term:
    ''' Assert ops are not placed on PE's that do not support them '''
    c = []
    print() # debugging format print
    for pe in cgra.functional_units:
        for op in design.operations:
            if op.opcode not in pe.ops:
                c.append(vars[pe, op] == 0)
                # debugging
                # solver.Assert(c[-1])
                # print('.', end='')
                # sys.stdout.flush()
                # if not solver.CheckSat():
                #     print("bad pair restriction was on {}".format((pe, op)))
                # end debugging
    return solver.And(c)

def route_exclusivity(cgra : MRRG, design : Design, vars : Modeler, solver : Solver) -> Term:
    '''
        each routing node is used for at most one value

        for all node in nodes:
            popcount(vars[node, value] for value in values) <= 1
    '''
    bv = solver.BitVec(len(design.values))
    c = []
    for node in cgra.all_nodes:
        node_vars = vars.anonymous_var(bv)
        for idx, value in enumerate(design.values):
            c.append(node_vars[idx] == vars[node, value])
        c.append(_is_one_hot_or_0(node_vars, solver))

    return solver.And(c)

def routing_resource_usage(cgra : MRRG, design : Design, vars : Modeler, solver : Solver) -> Term:
    '''
        if a routing node is used to route a value to a dst then then it is used to
        route the value
    '''
    c = []
    for node in cgra.all_nodes:
        for value in design.values:
            v = vars[node, value]
            v_ = ft.reduce(solver.BVOr, (vars[node, value, dst] for dst in value.dsts))
            c.append(v == v_)

    return solver.And(c)

def init_value(cgra : MRRG, design : Design, vars : Modeler, solver : Solver) -> Term:
    '''
        values are routed from the pe which holds their source op
    '''
    c = []
    for pe in cgra.functional_units:
        for value in design.values:
            src = value.src
            v = vars[pe, src]
            if src.duplicate:
                v_ = vars[pe, value]
                c.append(v == v_)
            else:
                for dst in value.dsts:
                    v_ = vars[pe, value, dst]
                    c.append(v == v_)

    return solver.And(c)

def port_placement(cgra : MRRG, design : Design, vars : Modeler, solver : Solver) -> Term:
    '''
        values terminate at the input port of their op
    '''
    c = []
    for pe in cgra.functional_units:
        for value in design.values:
            for dst in value.dsts:
                op, operand = dst
                if op.opcode not in pe.ops:
                    continue
                port = pe.operands[operand]
                v = vars[pe, op]
                v_ = vars[port, value, dst]
                c.append(v == v_)

    return solver.And(c)

def input_connectivity(cgra : MRRG, design : Design, vars : Modeler, solver : Solver) -> Term:
    '''
        if node used to route a value then exactly one of its inputs also
        routes that value
    '''

    c = []
    for node in cgra.routing_nodes:
        l = len(node.inputs.values())
        bv = solver.BitVec(l)
        for value in design.values:
            for dst in value.dsts:
                v = vars[node, value, dst]
                i_vars = vars.anonymous_var(bv)
                for idx, n in enumerate(node.inputs.values()):
                    c.append(i_vars[idx] == vars[n, value, dst])

                c.append(solver.Or(v == 0, _is_one_hot(i_vars, solver)))

    return solver.And(c)

def output_connectivity(cgra : MRRG, design : Design, vars : Modeler, solver : Solver) -> Term:
    '''
        if node used to route a value then exactly one of its outputs also
        routes that value
    '''
    c = []
    for node in cgra.all_nodes:
        bv = solver.BitVec(len(node.outputs.values()))
        for value in design.values:
            if isinstance(node, mrrg.FU_Port):
                continue
            for dst in value.dsts:
                v = vars[node, value, dst]
                i_vars = vars.anonymous_var(bv)
                for idx, n in enumerate(node.outputs.values()):
                    c.append(i_vars[idx] == vars[n, value, dst])
                c.append(solver.Or(v == 0, _is_one_hot(i_vars, solver)))

    return solver.And(c)

def fix_placement(cgra : MRRG, design : Design, vars : Modeler, solver : Solver) -> Term:
    '''
    Hack to fix a placement, hardcoding desired placement because just debugging
    '''
    desired_placement = {'x': (5, 2),
                         'add0': (2, 2),
                         'add1': (1, 2),
                         'add2': (1, 3),
                         'mul0': (4, 3),
                         'mul1': (2, 1),
                         'mul2': (3, 3),
                         'mul3': (1, 1),
                         'mul4': (2, 3),
                         'output0': (0, 3)}
    keys = set(desired_placement.keys())
    vals = set(desired_placement.values())
    # Not fixing constants, so this should hold
    assert len(keys) == len(vals), "Expecting all different placements"
    grid = {}
    for pe in cgra.functional_units:
        if 'Const' not in pe.name:
            row, col = map(int, pe.name.split('_')[-2:])
            grid[(row, col)] = pe

    c = []
    print()
    for op in design.operations:
        if op.name in desired_placement:
            c.append(vars[grid[desired_placement[op.name]], op] == solver.TheoryConst(solver.BitVec(1), 1))
            # debugging
            # print('.', end='')
            # sys.stdout.flush()
            # solver.Assert(c[-1])
            # if not solver.CheckSat():
            #     print("Placing {} at {} [{}] failed".format(op.name, desired_placement[op.name], grid[desired_placement[op.name]]))
            #     assert False
            # end debugging

    return solver.And(c)
