#!/usr/bin/env python3


import sys
import argparse
import time

parser = argparse.ArgumentParser(description='Run place and route')
parser.add_argument('design', metavar='<DESIGN_FILE>', help='dot file')
parser.add_argument('fabric', metavar='<FABRIC_FILE>', help='XML Fabric file')
parser.add_argument('--contexts', help='Number of contexts', type=int, default=1)
parser.add_argument('--verbose', '-v', help='print debug information', action='store_true', default=False)
parser.add_argument('--seed', help='Seed the randomness in solvers', type=int, default=0)
parser.add_argument('--solver', help='choose the smt solver to use for placement', default='Boolector')
parser.add_argument('--time', '-t', action='store_true', help='Print timing information.', default=False)
parser.add_argument('--parse-only', action='store_true', default=False, dest='parse_only')
parser.add_argument('--rewrite-fabric', default=None, dest='rewrite_name')
parser.add_argument('--optimize', '-o', action='store_true', default=False)
parser.add_argument('--incremental', '-i', action='store_true', default=False)
parser.add_argument('--cutoff', type=float, default=None)


args = parser.parse_args()

design_file = args.design
fabric_file = args.fabric

import dotparse
from design import Design
from adlparse import adlparse
from mrrg import MRRG
from pnr import PNR
import constraints
import optimization
import modeler
from util import Timer

mods, ties = dotparse.dot2graph(design_file)
design = Design(mods, ties)
cgra = adlparse(fabric_file, rewrite_name=args.rewrite_name)
mrrg = MRRG(cgra, contexts=args.contexts)
pnr = PNR(mrrg, design, args.solver, args.seed, args.incremental)

if args.parse_only:
    print('success')
    sys.exit(0)
verbose = args.verbose

init  = (
        constraints.init_placement_vars,
        constraints.init_routing_vars,
    )

funcs = (
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

if args.optimize:
    #filter_func = optimization.route_filter
    #filter_func = optimization.mux_filter
    filter_func = optimization.mux_reg_filter
    #filter_func = optimization.no_filter
    solve_timer = Timer(time.perf_counter)
    build_timer = Timer(time.perf_counter)
    opt_start = time.perf_counter()
    optimizer = optimization.Optimizer(filter_func,
            optimization.init_popcount_bithack,
#            optimization.init_popcount_concat,
            optimization.smart_count,
            optimization.lower_bound_popcount,
            optimization.limit_popcount_total)
    sat = pnr.optimize_design(
#    sat = pnr.optimize_enum(
            optimizer,
            init,
            funcs,
            verbose=verbose,
            attest_func=modeler.model_checker,
            solve_timer=solve_timer,
            build_timer=build_timer,
            cutoff = args.cutoff,
            #next_func=lambda u,l: u-1,
            )
    opt_end = time.perf_counter()
    if sat:
        pnr.attest_design(modeler.model_checker, verbose=verbose)
        print('SAT')
        if verbose:
            pnr.attest_design(modeler.model_info, verbose=verbose)
            pnr.attest_design(modeler.routing_stats, verbose=verbose)
    else:
        print('UNSAT')

    if args.time or verbose:
        def time_formater(time):
            formatter = '{:.4}'.format
            try:
                return ', '.join(map(formatter, time))
            except:
                return formatter(time)
        print(f'Optimization took {time_formater(opt_end - opt_start)} seconds', flush=True)
        print(f'Constraint building:\n\ttimes: {time_formater(build_timer.times)}\n\ttotal: {time_formater(build_timer.total)}')
        print(f'Solving:\n\ttimes: {time_formater(solve_timer.times)}\n\ttotal: {time_formater(solve_timer.total)}')
else:
    constraint_start = time.perf_counter()
    pnr.map_design(init, funcs, verbose=verbose)
    constraint_end = time.perf_counter()
    if args.time and verbose:
        print(f'Constraint building took {constraint_end - constraint_start} seconds', flush=True)

    solver_start = time.perf_counter()
    sat = pnr.solve(verbose=verbose)
    solver_end = time.perf_counter()

    if args.time and verbose:
        print(f'Solving took {solver_end - solver_start} seconds', flush=True)

    if sat:
        pnr.attest_design(modeler.model_checker, verbose=verbose)
        print('SAT')
        if verbose:
            pnr.attest_design(modeler.model_info, verbose=verbose)
            pnr.attest_design(modeler.routing_stats, verbose=verbose)
    else:
        print('UNSAT')

    if args.time and not verbose:
        print(f'Constraint building took {constraint_end - constraint_start} seconds')
        print(f'Solving took {solver_end - solver_start} seconds')

