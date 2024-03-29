#!/usr/bin/env python3
import argparse
import dotparse
from design import Design
from adlparse import adlparse
from mrrg import MRRG
from pnr import PNR
import constraints
import optimization
import modeler
from util import Timer
import json
import tester
import time


parser = argparse.ArgumentParser('run test')
parser.add_argument('fabric', metavar='<FABRIC_FILE>', help='XML Fabric file')
parser.add_argument('contexts', help='Number of contexts', type=int)
parser.add_argument('design', metavar='<DESIGN_FILE>', help='dot file')
parser.add_argument('optimizer_name')
parser.add_argument('--cutoff', type=float, default=None)
parser.add_argument('--optimize_final', action='store_true', default=False)
parser.add_argument('--incremental', action='store_true', default=False)
parser.add_argument('--duplicate_const', action='store_true', default=False)
parser.add_argument('--duplicate_all', action='store_true', default=False)
parser.add_argument('--no-tie-nodes', action='store_true', default=False, dest='ntiesnodes')

args = parser.parse_args()

solve_timer = Timer(time.perf_counter)
build_timer = Timer(time.perf_counter)
full_timer = Timer(time.perf_counter)

design_file = args.design
contexts = args.contexts
fabric_file = args.fabric
optimizer_name = args.optimizer_name

cutoff = args.cutoff
optimize_final = args.optimize_final
incremental = args.incremental
duplicate_const = args.duplicate_const
duplicate_all = args.duplicate_all

optimizer = tester.OPTIMIZERS[optimizer_name]
solver = tester.SOLVER


mods, ties = dotparse.dot2graph(design_file)
design = Design(mods, ties)
cgra = adlparse(fabric_file)
mrrg = MRRG(cgra, contexts=contexts, add_tie_nodes=not args.ntiesnodes)

pnr = PNR(mrrg, design, solver, incremental=incremental, duplicate_const=duplicate_const, duplicate_all=duplicate_all)

full_timer.start()
result = pnr.optimize_design(
        optimizer,
        tester.init,
        tester.funcs,
        verbose=False,
        cutoff=cutoff,
        build_timer=build_timer,
        solve_timer=solve_timer,
        return_bounds=True,
        optimize_final=optimize_final,
#        attest_func=modeler.model_checker,
        )

full_timer.stop()

print(json.dumps({
    'benchmark' : {
        'fabric' : fabric_file,
        'contexts' : contexts,
        'design' : design_file,
    },
    'params' : {
        'incremental' : incremental,
        'cutoff' : cutoff,
        'optimize_final' : optimize_final,
        'optimizer' : optimizer_name,
        'duplicate_const' : duplicate_const,
        'duplicate_all' : duplicate_all,
        'solver' : solver,
    },
    'results' : {
        'sat' : result[0],
        'lower' : result[1],
        'upper' : result[2],
        'total_time' : full_timer.total,
        'build_time_total' : build_timer.total,
        'solve_time_total' : solve_timer.total,
        'build_times' : tuple(build_timer.times),
        'solve_times' : tuple(solve_timer.times),
    },
}))

