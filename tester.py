#!/usr/bin/env python3
import time
import datetime
import dotparse
from design import Design
from adlparse import adlparse
from mrrg import MRRG
from pnr import PNR
import constraints
import optimization
import modeler
from util import Timer

RESULTS_FILE = 'results.csv'

FABRICS = [
    './fabrics/small_pattern.xml',
    './fabrics/small_pattern_const.xml',
    './fabrics/small_pattern_hetero.xml',
    './fabrics/small_pattern_const_hetero.xml',
#    './fabrics/mid_pattern.xml',
#    './fabrics/mid_pattern_const.xml',
#    './fabrics/mid_pattern_hetero.xml',
#    './fabrics/mid_pattern_const_hetero.xml',
]

DESIGNS = [
    './designs/linalg/vm2x2.dot',
    './designs/linalg/vcm2x2.dot',
    './designs/linalg/vm3x3.dot',
    './designs/linalg/vcm3x3.dot',
    './designs/linalg/mm2x2.dot',
    './designs/linalg/mcm2x2.dot',
    './designs/linalg/vv3x3.dot',
    './designs/linalg/vcv3x3.dot',
    './designs/linalg/vv4x4.dot',
    './designs/linalg/vcv4x4.dot',
]

CONTEXTS = [1]

OPTIMIZERS = {

    'BIT_HACK_MUX' : optimization.Optimizer(optimization.mux_filter,
                        optimization.init_popcount_bithack,
                        optimization.smart_count,
                        optimization.limit_popcount_total),

    'BIT_HACK_M/R' : optimization.Optimizer(optimization.mux_reg_filter,
                        optimization.init_popcount_bithack,
                        optimization.smart_count,
                        optimization.limit_popcount_total),
}

INCREMENTAL = [True, False]

SOLVERS = [
    'Boolector',
]

CUTOFFS = [
    0.0, 0.2, 2.0,
]

fabric_cache = dict()
solve_timer = Timer(time.perf_counter)
build_timer = Timer(time.perf_counter)
full_timer = Timer(time.perf_counter)
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

with open(RESULTS_FILE, 'a') as outfile:
    date = datetime.datetime.now().isoformat(timespec='seconds')
    outfile.write('\n\nrun_date, design, fabric, contexts, solver, incremental, cutoff, optimizer, total_time, total_build_time, total_solve_time, iterations, result, lower_bound, upper_bound;\n')
    for design_file in DESIGNS:
        for fabric_file in FABRICS:
            for contexts in CONTEXTS:
                for solver_str in SOLVERS:
                    for incremental in INCREMENTAL:
                        for cutoff in CUTOFFS:
                            for optimizer_name, optimizer in OPTIMIZERS.items():
                                solve_timer.reset()
                                build_timer.reset()
                                full_timer.reset()
                                mods, ties = dotparse.dot2graph(design_file)
                                design = Design(mods, ties)
                                cgra = adlparse(fabric_file)
                                mrrg = fabric_cache[fabric_file, contexts] = MRRG(cgra, contexts=contexts)
                                pnr = PNR(mrrg, design, solver_str, incremental=incremental)
                                full_timer.start()
                                result = pnr.optimize_design(
                                        optimizer,
                                        init,
                                        funcs,
                                        verbose=False,
                                        cutoff=cutoff,
                                        build_timer=build_timer,
                                        solve_timer=solve_timer,
                                        return_bounds=True,
                                        )
                                full_timer.stop()
                                if len(build_timer.times) != len(solve_timer.times):
                                    print('something wierd happened')
                                outfile.write(
                                    f'{date}, {design_file}, {fabric_file}, {contexts}, {solver_str}, {incremental}, {cutoff}, {optimizer_name}, {full_timer.total}, {build_timer.total}, {solve_timer.total}, {len(solve_timer.times)}, {result[0]}, {result[1]}, {result[2]};\n')
                                outfile.flush()
