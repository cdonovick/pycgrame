#!/usr/bin/env python3


import sys
import argparse
import time 

parser = argparse.ArgumentParser(description='Run place and route')
parser.add_argument('design', metavar='<DESIGN_FILE>', help='Mapped coreir file')
parser.add_argument('fabric', metavar='<FABRIC_FILE>', help='XML Fabric file')
parser.add_argument('--contexts', help='Number of contexts', type=int, default=1)
parser.add_argument('--verbose', '-v', help='print debug information', action='store_true', default=False)
parser.add_argument('--seed', help='Seed the randomness in solvers', type=int, default=0)
parser.add_argument('--solver', help='choose the smt solver to use for placement', default='Boolector')
parser.add_argument('--time', '-t', action='store_true', help='Print timing information.', default=False)


args = parser.parse_args()

design_file = args.design
fabric_file = args.fabric

import dotparse
from design import Design
from adlparse import adlparse
from mrrg import MRRG
from pnr import PNR
import constraints

mods, ties = dotparse.dot2graph(design_file)
design = Design(mods, ties)
cgra = adlparse(fabric_file)
mrrg = MRRG(cgra, contexts=args.contexts)
pnr = PNR(mrrg, design, args.solver, args.seed)
verbose = args.verbose

funcs = (
        constraints.init_placement_vars,
        constraints.init_routing_vars,
        constraints.op_placement,
        constraints.pe_exclusivity,
        constraints.pe_legality,
        constraints.route_exclusivity,
        constraints.init_value,
        constraints.port_placement,
        constraints.input_connectivity,
        constraints.output_connectivity,
        constraints.routing_resource_usage,
    )
constraint_start = time.perf_counter()
pnr.map_design(*funcs, verbose=verbose)
constraint_end = time.perf_counter()
if args.time and verbose:
    print(f'Constraint building took {constraint_end - constraint_start} seconds', flush=True)

solver_start = time.perf_counter()
sat = pnr.solve(verbose=verbose)
solver_end = time.perf_counter()

if args.time and verbose:
    print(f'Solving took {solver_end - solver_start} seconds', flush=True)

if sat:
    pnr.attest_design(constraints.model_checker)
    print('SAT')
else:
    print('UNSAT')

if args.time and not verbose:
    print(f'Constraint building took {constraint_end - constraint_start} seconds')
    print(f'Solving took {solver_end - solver_start} seconds')

