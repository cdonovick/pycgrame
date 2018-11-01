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
#    './designs/linalg/vv3x3.dot',
#    './designs/linalg/vcv3x3.dot',
#    './designs/linalg/vv4x4.dot',
#    './designs/linalg/vcv4x4.dot',
#    './designs/linalg/vm2x2.dot',
#    './designs/linalg/vcm2x2.dot',
#    './designs/linalg/vm3x3.dot',
#    './designs/linalg/vcm3x3.dot',
#    './designs/linalg/mm2x2.dot',
#    './designs/linalg/mcm2x2.dot',

    './designs/cgrame/add_16.dot',
    './designs/cgrame/cos_4.dot',
    './designs/cgrame/cosh_4.dot',
    './designs/cgrame/exponential_4.dot',
    './designs/cgrame/exponential_6.dot',
    './designs/cgrame/multiply_16.dot',
    './designs/cgrame/sinh_4.dot',
    './designs/cgrame/taylor_series_4.dot',
    './designs/cgrame/test_operation_extreme_block.dot',
    './designs/cgrame/weighted_sum.dot', #vv8x8
]
# Excluded
#    './designs/cgrame/add_10.dot',
#    './designs/cgrame/add_14.dot',
#    './designs/cgrame/corner_case_2x2_fail.dot',
#    './designs/cgrame/corner_case_2x2_pass.dot',
#    './designs/cgrame/exponential_5.dot',
#    './designs/cgrame/multiply_10.dot',
#    './designs/cgrame/multiply_14.dot',

CONTEXTS_OPTIMIZERS = [
    (1, 'BIT_HACK_MUX'),
    (2, 'BIT_HACK_M/R'),
]

OPTIMIZERS = {

    'BIT_HACK_MUX' : optimization.Optimizer(optimization.mux_filter,
                        optimization.init_popcount_bithack,
                        optimization.smart_count,
                        optimization.lower_bound_popcount,
                        optimization.limit_popcount_total),

    'BIT_HACK_M/R' : optimization.Optimizer(optimization.mux_reg_filter,
                        optimization.init_popcount_bithack,
                        optimization.smart_count,
                        optimization.lower_bound_popcount,
                        optimization.limit_popcount_total),
}

CONFIG_MATS = [
    {
        'incremental' : [False, True],
        'duplicate' : [None, 'duplicate_const',], #'duplicate_all',], duplicate all seems to break things not sure why
        'cutoff' : [None],
        'optimize_final' : [False, True],
    },
    {
        'incremental' : [True],
        'duplicate' : [None],
        'cutoff' : [0.0],
        'optimize_final' : [False],
    },
    {
        'incremental' : [True],
        'duplicate' : [None],
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
        for contexts,optimizer_name in CONTEXTS_OPTIMIZERS:
            for design_file in DESIGNS:
                for config_mat in CONFIG_MATS:
                    for incremental in config_mat['incremental']:
                        for cutoff in config_mat['cutoff']:
                            for optimize_final in config_mat['optimize_final']:
                                for dupe in config_mat['duplicate']:
                                    s = f'PYTHONHASHSEED=0 python3 -W ignore run_test.py {fabric_file} {contexts} {design_file} {optimizer_name}'
                                    if cutoff is not None:
                                        s += f' --cutoff {cutoff}'
                                    if optimize_final:
                                        s += ' --optimize_final'
                                    if incremental:
                                        s += ' --incremental'
                                    if dupe is not None:
                                        s += f' --{dupe}'

                                    print(s)

