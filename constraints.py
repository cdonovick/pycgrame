import mrrg
from util import BiDict, BiMultiDict
import functools as ft
import itertools as it
import math

_var_counter = it.count()
def _gen_name():
    return f'V_{next(_var_counter)}'

def init_placement_vars(cgra, design, map_vars, solver):
    bv1 = solver.BitVec(1)
    for pe in cgra.functional_units:
        for op in design.operations:
            map_vars[pe, op] = v = solver.DeclareConst(_gen_name(), bv1)
    return True

def init_routing_vars(cgra, design, map_vars, solver):
    bv1 = solver.BitVec(1)
    for node in cgra.all_nodes:
        for value in design.values:
            map_vars[node, value] = v = solver.DeclareConst(_gen_name(), bv1)
            for dst in value.dsts:
                map_vars[node, value, dst] = v = solver.DeclareConst(_gen_name(), bv1)

    return True


def _is_one_hot(var, solver):
    c = []
    bv = var.sort
    if solver.solver_name == 'CVC4':
        for i in range(var.sort.width):
            c.append(var == solver.TheoryConst(bv, 1) << i)
    else:
        for i in range(var.sort.width):
            c.append(var == solver.TheoryConst(bv, 1 << i))


    return solver.Or(c)

def op_placement(cgra, design, map_vars, solver):
    ''' Assert all ops are placed exactly one time '''
    bv = solver.BitVec(len(cgra.functional_units))
    c = []
    for op in design.operations:
        op_vars = solver.DeclareConst(_gen_name(), bv)
        for idx,pe in enumerate(cgra.functional_units):
            c.append(op_vars[idx] == map_vars[pe, op])
        c.append(_is_one_hot(op_vars, solver))

    return solver.And(c)

def pe_exclusivity(cgra, design, map_vars, solver):
    ''' Assert all PEs are used at most one time '''
    bv = solver.BitVec(len(design.operations))
    c = []
    for pe in cgra.functional_units:
        pe_vars = solver.DeclareConst(_gen_name(), bv)
        for idx, op in enumerate(design.operations):
            c.append(pe_vars[idx] == map_vars[pe, op])
        c.append(solver.Or(_is_one_hot(pe_vars, solver), pe_vars == 0))

    return solver.And(c)

def pe_legality(cgra, design, map_vars, solver):
    ''' Assert ops are not placed on PE's that do not support them '''
    c = []
    for pe in cgra.functional_units:
        for op in design.operations:
            if op.opcode not in pe.ops:
                c.append(map_vars[pe, op] == 0)
    return solver.And(c)

def route_exclusivity(cgra, design, map_vars, solver):
    '''
        each routing node is used for at most one value

        for all node in nodes:
            popcount(vars[node, value] for value in values) <= 1
    '''
    bv = solver.BitVec(len(design.values))
    c = []
    for node in cgra.all_nodes:
        node_vars = solver.DeclareConst(_gen_name(), bv)
        for idx, value in enumerate(design.values):
            c.append(node_vars[idx] == map_vars[node, value])
        c.append(solver.Or(_is_one_hot(node_vars, solver), node_vars == 0))

    return solver.And(c)

def routing_resource_usage(cgra, design, map_vars, solver):
    c = []
    for node in cgra.all_nodes:
        for value in design.values:
            for dst in value.dsts:
                #node,value,dst => node,value
                c.append(solver.Or(map_vars[node, value, dst] == 0, map_vars[node, value] == 1))
    return solver.And(c)

def init_value(cgra, design, map_vars, solver):
    c = []
    for pe in cgra.functional_units:
        for op in design.operations:
            value = op.output
            if value is not None:
                v = map_vars[pe, op]
                for dst in value.dsts:
                    v_ = map_vars[pe, value, dst]
                    c.append(v == v_)

    return solver.And(c)

def port_placement(cgra, design, map_vars, solver):
    c = []
    for pe in cgra.functional_units:
        for op in design.operations:
            if op.opcode not in pe.ops:
                continue
            v = map_vars[pe, op]
            for operand, value in op.inputs.items():
                node = pe.operands[operand]
                dst = (op, operand)
                assert dst in value.dsts, (dst, value.dsts)
                v_ = map_vars[node, value, dst]
                c.append(v == v_)

    return solver.And(c)

def input_connectivity(cgra, design, map_vars, solver):
    '''
    if node used to route a value then exactly one of its inputs is also used
    to route that value or is the origin of the value
    '''

    c = []
    for node in cgra.routing_nodes:
        l = len(node.inputs.values())
        bv = solver.BitVec(l)
        for value in design.values:
            for dst in value.dsts:
                v = map_vars[node, value, dst]
                i_vars = solver.DeclareConst(_gen_name(), bv)
                for idx, n in enumerate(node.inputs.values()):
                    c.append(i_vars[idx] == map_vars[n, value, dst])

                c.append(solver.Or(v == 0, _is_one_hot(i_vars, solver)))

    return solver.And(c)

def output_connectivity(cgra, design, map_vars, solver):
    '''
    if node used to route a value then at least one of  its outputs is also
    used to route that value or is the origin of the value
    '''
    c = []
    for node in cgra.all_nodes:
        bv = solver.BitVec(len(node.outputs.values()))
        for value in design.values:
            if isinstance(node, mrrg.FU_Port):
                continue
            for dst in value.dsts:
                v = map_vars[node, value, dst]
                i_vars = solver.DeclareConst(_gen_name(), bv)
                for idx, n in enumerate(node.outputs.values()):
                    c.append(i_vars[idx] == map_vars[n, value, dst])


                c.append(solver.Or(v == 0, _is_one_hot(i_vars, solver)))

    return solver.And(c)


def _get_path(solver, map_vars, node, value, dst, dst_node):
    yield node
    if node != dst_node:
        next = None
        for n in node.outputs.values():
            if solver.GetValue(map_vars[n, value, dst]).as_int() == 1:
                assert next is None
                next = n
        assert next is not None
        yield from _get_path(solver, map_vars, next, value, dst, dst_node)

class optimizer:
    def __init__(self, calc, gen):
        self.lower = 0
        self.upper = None
        self.last = None
        self.calc = calc
        self.gen = gen

    def __call__(self, cgra, design, map_vars, solver, sat):
        if sat:
            self.upper = self.calc(cgra, design, map_vars, solver)
        else:
            assert self.last is not None
            self.lower = self.last

        print(f'range is: [{self.lower}, {self.upper})', flush=True)
        next = math.ceil((self.lower + self.upper)/2)
        if next == self.last or next < self.lower or next > self.upper:
            return None
        else:
            self.last = next
            return self.gen(next)

def count_mux(cgra, design, map_vars, solver):
    F_map = BiDict()
    for pe in cgra.functional_units:
        for op in design.operations:
            if solver.GetValue(map_vars[pe, op]).as_int() == 1:
                F_map[op] = pe
    used = set()
    for op in design.operations:
        value = op.output
        if value is not None:
            pe = F_map[op]
            dsts = {(F_map[dst].operands[port]) for dst, port in value.dsts}
            for dst in value.dsts:
                assert dst[0] in F_map
                dst_node = F_map[dst[0]].operands[dst[1]]
                for node in _get_path(solver, map_vars, pe, value, dst, dst_node):
                    if isinstance(node, mrrg.Mux):
                        used.add(node)
    return len(used)


def limit_muxes(n):
    p = ft.partial(_limit_muxes, n)
    p.__name__ = f'{limit_muxes.__name__}({n})'
    p.__qualname__ = f'{limit_muxes.__qualname__}({n})'
    return p

def _limit_muxes(n, cgra, design, map_vars, solver):
    bv = solver.BitVec(max(len(cgra.muxes).bit_length(), n.bit_length()) +  1)
    zero = solver.TheoryConst(bv, 0)
    one  = solver.TheoryConst(bv, 1)
    expr = None

    for mux in cgra.muxes:
        s_expr = None
        for value in design.values:
            if s_expr is None:
                s_expr = map_vars[mux, value]
            else:
                s_expr = solver.BVOr(s_expr, map_vars[mux, value])
        if expr is None:
            expr = solver.Ite(s_expr == 0, zero, one)
        else:
            expr = expr + solver.Ite(s_expr == 0, zero, one)

    if expr is not None:
        return expr < n
    else:
        return True

def count_route(cgra, design, map_vars, solver):
    F_map = BiDict()
    for pe in cgra.functional_units:
        for op in design.operations:
            if solver.GetValue(map_vars[pe, op]).as_int() == 1:
                F_map[op] = pe
    used = set()
    for op in design.operations:
        value = op.output
        if value is not None:
            pe = F_map[op]
            dsts = {(F_map[dst].operands[port]) for dst, port in value.dsts}
            for dst in value.dsts:
                assert dst[0] in F_map
                dst_node = F_map[dst[0]].operands[dst[1]]
                for node in _get_path(solver, map_vars, pe, value, dst, dst_node):
                    used.add(node)
    return len(used)


def limit_route(n):
    p = ft.partial(_limit_route, n)
    p.__name__ = f'{limit_route.__name__}({n})'
    p.__qualname__ = f'{limit_route.__qualname__}({n})'
    return p

def _limit_route(n, cgra, design, map_vars, solver):
    bv = solver.BitVec(max(len(cgra.routing_nodes).bit_length(), n.bit_length()) +  1)
    zero = solver.TheoryConst(bv, 0)
    one  = solver.TheoryConst(bv, 1)
    expr = None

    for node in cgra.routing_nodes:
        s_expr = None
        for value in design.values:
            if s_expr is None:
                s_expr = map_vars[node, value]
            else:
                s_expr = solver.BVOr(s_expr, map_vars[node, value])
        if expr is None:
            expr = solver.Ite(s_expr == 0, zero, one)
        else:
            expr = expr + solver.Ite(s_expr == 0, zero, one)

    if expr is not None:
        return expr < n
    else:
        return True

def model_checker(cgra, design, map_vars, solver):
    F = dict()
    R = dict()
    S = dict()
    F_map = BiDict()
    R_map = BiMultiDict()
    S_map = BiMultiDict()

    for pe in cgra.functional_units:
        for op in design.operations:
            if solver.GetValue(map_vars[pe, op]).as_int() == 1:
                F[pe, op] = True
                assert op not in F_map
                assert pe not in F_map.I
                F_map[op] = pe
            else:
                F[pe, op] = False

    for node in cgra.all_nodes:
        for value in design.values:
            if solver.GetValue(map_vars[node, value]).as_int() == 1:
                R[node, value] = True
                assert node not in R_map.I
                R_map[value] = node
            else:
                R[node, value] = False

    for node in cgra.all_nodes:
        for value in design.values:
            for dst in value.dsts:
                if solver.GetValue(map_vars[node, value, dst]).as_int() == 1:
                    assert R[node, value]
                    S[node, value, dst] = True
                    S_map[value, dst] = node
                else:
                    S[node, value, dst] = False

    for op in design.operations:
        assert op in F_map

    def _flood(node, value, dst, dst_node):
        if node == dst_node:
            return
        assert S[node, value, dst]
        next = None
        for n in node.outputs.values():
            if S[n, value, dst]:
                assert next is None, (node, next, n)
                next = n
        assert next is not None, '\n%s\n%s\n%s\n%s\n' % (node, node.outputs, dst, dst_node)
        return _flood(next, value, dst, dst_node)

    for op in design.operations:
        pe = F_map[op]
        value = op.output
        if value is not None:
            dsts = {(F_map[dst].operands[port]) for dst, port in value.dsts}
            assert R[pe, value]
            for dst in value.dsts:
                assert dst[0] in F_map
                dst_node = F_map[dst[0]].operands[dst[1]]
                node = pe
                assert S[pe, value, dst]
                _flood(pe, value, dst, dst_node)

def model_info(cgra, design, map_vars, solver):
    F_map = BiDict()

    for pe in cgra.functional_units:
        for op in design.operations:
            if solver.GetValue(map_vars[pe, op]).as_int() == 1:
                F_map[op] = pe
                print(f'{op.name}({op.opcode}): {pe.name}')

    used = set()
    for op in design.operations:
        value = op.output
        if value is not None:
            pe = F_map[op]
            dsts = {(F_map[dst].operands[port]) for dst, port in value.dsts}
            for dst in value.dsts:
                assert dst[0] in F_map
                dst_node = F_map[dst[0]].operands[dst[1]]
                print(f'{op.name}->{dst[0].name}:{dst[1]}')
                for node in _get_path(solver, map_vars, pe, value, dst, dst_node):
                    print(f'\t{node.name}')
                    if isinstance(node, mrrg.Mux):
                        used.add(node)

    print(f'Total muxes used: {len(used)}')
