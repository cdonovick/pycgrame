
import typing as tp
import mrrg
import design
import functools as ft
import operator
from mrrg import MRRG, TieNode
from design import Design
from modeler import Model

def _is_one_hot_or_0(var : int) -> bool:
    return var & (var - 1) == 0

def _is_one_hot(var : int) -> bool:
    return _is_one_hot_or_0(var) and var != 0

def op_placement(cgra : MRRG, design : Design, model : Model) -> None:
    ''' Assert all ops are placed exactly one time
    unless they can be duplicated in which case assert they are placed '''
    for op in design.operations:
        if op.duplicate:
            assert ft.reduce(operator.or_, (model[pe, op] for pe in cgra.functional_units)) == 1
        else:
            op_vars = 0
            for idx,pe in enumerate(cgra.functional_units):
                op_vars += model[pe, op] << idx
            assert _is_one_hot(op_vars)

    

def pe_exclusivity(cgra : MRRG, design : Design, model : Model) -> None:
    ''' Assert all PEs are used at most one time '''
    for pe in cgra.functional_units:
        pe_vars = 0
        for idx, op in enumerate(design.operations):
            pe_vars += model[pe, op] << idx
        assert _is_one_hot_or_0(pe_vars)


def pe_legality(cgra : MRRG, design : Design, model : Model) -> None:
    ''' Assert ops are not placed on PE's that do not support them '''
    for pe in cgra.functional_units:
        for op in design.operations:
            if op.opcode not in pe.ops:
                assert model[pe, op] == 0

def route_exclusivity(cgra : MRRG, design : Design, model : Model) -> None:
    '''
        each routing node is used for at most one value

        for all node in nodes:
            popcount(model[node, value] for value in values) <= 1
    '''
    for node in cgra.all_nodes:
        node_vars = 0
        for idx, value in enumerate(design.values):
            node_vars += model[node, value] << idx
        assert _is_one_hot_or_0(node_vars)


def routing_resource_usage(cgra : MRRG, design : Design, model : Model) -> None:
    '''
        if a routing node is used to route a value to a dst then then it is used to
        route the value
    '''
    for node in cgra.all_nodes:
        for value in design.values:
            v = model[node, value]
            v_ = ft.reduce(operator.or_, (model[node, value, dst] for dst in value.dsts))
            assert v == v_


def init_value(cgra : MRRG, design : Design, model : Model) -> None:
    '''
        values are routed from the pe which holds their source op
    '''
    for pe in cgra.functional_units:
        for value in design.values:
            src = value.src
            v = model[pe, src]
            if src.duplicate:
                v_ = model[pe, value]
                assert v == v_
            else:
                for dst in value.dsts:
                    v_ = model[pe, value, dst]
                    assert v == v_

def port_placement(cgra : MRRG, design : Design, model : Model) -> None:
    '''
        values terminate at the input port of their op
    '''
    for pe in cgra.functional_units:
        for value in design.values:
            for dst in value.dsts:
                op, operand = dst
                if op.opcode not in pe.ops:
                    for port in pe.operands.values():
                        v_ = model[port, value, dst]
                        assert v_ == 0
                else:
                    port = pe.operands[operand]
                    v = model[pe, op]
                    v_ = model[port, value, dst]
                    assert v == v_

def input_connectivity(cgra : MRRG, design : Design, model : Model) -> None:
    '''
        if node used to route a value then exactly one of its inputs also
        routes that value
    '''
    for node in cgra.routing_nodes:
        for value in design.values:
            for dst in value.dsts:
                v = model[node, value, dst]
                i_vars = 0
                for idx, n in enumerate(node.inputs.values()):
                    if isinstance(n, TieNode):
                        n = n.input
                    i_vars += model[n, value, dst] << idx
                
                if not (v == 0 or _is_one_hot(i_vars)):
                    print(f'node: {node}')
                    print(f'v: {v}')
                    print(f'i_vars: {i_vars}')
                    print(f'value: {value}')
                    print(f'dst: {dst}')
                    print(f'inputs:')
                    for n in node.inputs.values():
                        if isinstance(n, TieNode):
                            n = n.input
                        print(f'\t{n}')
                    print(f'enabled inputs:')
                    for n in node.inputs.values():
                        if isinstance(n, TieNode):
                            n = n.input
                        if model[n, value, dst] == 1:
                            print(f'\t{n}')
                    assert 0



def output_connectivity(cgra : MRRG, design : Design, model : Model) -> None:
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
                v = model[node, value, dst]
                for idx, n in enumerate(node.inputs.values()):
                    if isinstance(n, TieNode):
                        n = n.output
                    i_vars += model[n, value, dst] << idx
                assert v == 0 or _is_one_hot(i_vars)


