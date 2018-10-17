#!/usr/bin/env python3
import constraints
import optimization

SOLVER = 'Boolector'

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


if __name__ == '__main__':
    for fabric_file in FABRICS:
        for contexts in CONTEXTS:
            for design_file in DESIGNS:
                for config_mat in CONFIG_MATS:
                    for incremental in config_mat['incremental']:
                        for cutoff in config_mat['cutoff']:
                            for optimize_final in config_mat['optimize_final']:
                                for optimizer_name in OPTIMIZERS:
                                    s = f'python3 -W ignore run_test.py {fabric_file} {contexts} {design_file} {optimizer_name}'
                                    if cutoff is not None:
                                        s += f' --cutoff {cutoff}'
                                    if optimize_final:
                                        s += ' --optimize_final'
                                    if incremental:
                                        s += ' --incremental'

                                    print(s)

