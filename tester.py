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
import json

RESULTS_FILE = 'results.json'

SOLVER = 'Boolector'
TIME_OUT = 2*60*60

FABRICS = [
    './benchmark_fabrics/small_ortho.xml',
    './benchmark_fabrics/small_ortho_hetero.xml',
    './benchmark_fabrics/small_diag.xml',
    './benchmark_fabrics/small_diag_hetero.xml',
    './benchmark_fabrics/mid_ortho.xml',
    './benchmark_fabrics/mid_ortho_hetero.xml',
    './benchmark_fabrics/mid_diag.xml',
    './benchmark_fabrics/mid_diag_hetero.xml',
]

DESIGNS = [
    './designs/other/point_const.dot',
    './designs/linalg/vv3x3.dot',
    './designs/linalg/vcv3x3.dot',
    './designs/linalg/vv4x4.dot',
    './designs/linalg/vcv4x4.dot',
    './designs/linalg/vm2x2.dot',
    './designs/linalg/vcm2x2.dot',
    './designs/linalg/vm3x3.dot',
    './designs/linalg/vcm3x3.dot',
    './designs/linalg/mm2x2.dot',
    './designs/linalg/mcm2x2.dot',
]

CONTEXTS = [
    1,
    2,
]

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

DUPLICATE = [
    False,
    True,
]

CONFIG_MATS = [
    {
        'incremental' : [False],
        'cutoff' : [None],
        'optimize_final' : [False, True],
    },
    {
        'incremental' : [True],
        'cutoff' : [None],
        'optimize_final' : [True],
    },
    {
        'incremental' : [True],
        'cutoff' : [0.0],
        'optimize_final' : [False],
    },
    {
        'incremental' : [True],
        'cutoff' : [0.2, 0.5],
        'optimize_final' : [False, True],
    },
]


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


results = []

date = datetime.datetime.now().isoformat(timespec='seconds')
for fabric_file in FABRICS:
    for contexts in CONTEXTS:
        for design_file in DESIGNS:
            for config_mat in CONFIG_MATS:
                for incremental in config_mat['incremental']:
                    for cutoff in config_mat['cutoff']:
                        for optimize_final in config_mat['optimize_final']:
                            for optimizer_name, optimizer in OPTIMIZERS.items():
                                solve_timer.reset()
                                build_timer.reset()
                                full_timer.reset()
                                mods, ties = dotparse.dot2graph(design_file)
                                design = Design(mods, ties)
                                cgra = adlparse(fabric_file)
                                mrrg = MRRG(cgra, contexts=contexts)
                                pnr = PNR(mrrg, design, SOLVER, incremental=incremental)
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
                                        optimize_final=optimize_final,
                                        time_out=TIME_OUT,
                                        )
                                full_timer.stop()
                                results.append(
                                    {
                                        'params' : {
                                            'fabric' : repr(fabric_file),
                                            'contexts' : repr(contexts),
                                            'design' : repr(design_file),
                                            'incremental' : repr(incremental),
                                            'cutoff' : repr(cutoff),
                                            'optimize_final' : repr(optimize_final),
                                            'optimizer' : repr(optimizer_name),
                                        },
                                        'results' : {
                                            'sat' : repr(result[0]),
                                            'lower' : repr(result[1]),
                                            'upper' : repr(result[2]),
                                            'total_time' : repr(full_timer.total),
                                            'solve_time_total' : repr(solve_timer.total),
                                            'build_time_total' : repr(build_timer.total),
                                            'solve_times' : repr(tuple(solve_timer.times)),
                                            'build_times' : repr(tuple(build_timer.times)),
                                        },
                                    }
                                )

with open(RESULTS_FILE, 'w') as f:
    json.dump(results, f)

