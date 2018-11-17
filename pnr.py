import itertools as it
import functools as ft
import typing as tp
from collections import Counter
from smt_switch import smt
from modeler import Modeler
from design import Design
from mrrg import MRRG
import mrrg
import checker
import smt_switch_types
from constraints import ConstraintGeneratorType
from modeler import Model, ModelReader
import optimization
from util import Timer, NullTimer

ConstraintGeneratorList = tp.Sequence[ConstraintGeneratorType]


class PNR:
    _cgra : MRRG
    _design : Design
    _vars : Modeler
    _solver : smt_switch_types.Solver
    _model : tp.Optional[Model]
    _solver_opts : tp.List[tp.Tuple[str, str]]
    _incremental : bool

    def __init__(self,
            cgra : MRRG,
            design : Design,
            solver_str : str,
            seed : int = 0,
            incremental : bool = False,
            duplicate_const : bool = False,
            duplicate_all : bool = False,):



        if duplicate_all:
            for op in design.operations:
                op.allow_duplicate()
        elif duplicate_const:
            for op in design.operations:
                if op.opcode == 'const':
                    op.allow_duplicate()

        self._cgra = cgra
        self._design  = design
        self._incremental = incremental

        self._solver = solver = smt(solver_str)
        self._solver_opts = solver_opts = [('random-seed', seed), ('produce-models', 'true')]
        if incremental:
            solver_opts.append(('incremental', 'true'))

        if solver_str == 'CVC4':
            if incremental:
                solver_opts.append(('bv-sat-solver', 'cryptominisat'))
            else:
                solver_opts.append(('bv-sat-solver', 'cadical'))
                #solver_opts.append(('bitblast', 'eager'))

        self._init_solver()
        self._vars  = Modeler(solver)
        self._model = None

    def _check_pigeons(self) -> bool:
        op_hist = Counter()
        pe_hist = Counter()
        for op in self.design.operations:
            op_hist[op.opcode] += 1

        for pe in self.cgra.functional_units:
            for op in pe.ops:
                pe_hist[op] += 1
        for op, n in op_hist.items():
            if pe_hist[op] < n:
                return False
        else:
            return True

    def _reset(self) -> None:
        self._vars.reset()
        self._solver.Reset()
        self._init_solver()
        self._model = None

    def _init_solver(self) -> None:
        solver = self._solver

        solver.SetLogic('QF_BV')
        for opts in self._solver_opts:
            solver.SetOption(*opts)

        if self._solver.solver_name == 'Boolector':
            if self._incremental:
                self._solver._solver._btor.Set_sat_solver("Lingeling")
            else:
                self._solver._solver._btor.Set_sat_solver("CaDiCaL")

    def pin_module(self, module, placement):
        raise NotImplementedError()

    def pin_tie(self, tie, placement):
        raise NotImplementedError()

    def map_design(self,
            init_funcs : ConstraintGeneratorList,
            funcs : ConstraintGeneratorList,
            verbose : bool = False) -> None:
        solver = self._solver
        args = self.cgra, self.design, self._vars, solver

        if verbose:
            for f in it.chain(init_funcs, funcs):
                print(f.__qualname__, end='... ', flush=True)
                c = f(*args)
                print('done', flush=True)
                solver.Assert(c)
        else:
            for f in it.chain(init_funcs, funcs):
                solver.Assert(f(*args))

    def satisfy_design(self,
            init_funcs : ConstraintGeneratorList,
            funcs : ConstraintGeneratorList,
            verbose : bool = False,
            attest_func : tp.Optional[ModelReader] = None,
            first_cut : tp.Optional[tp.Callable[[int, int], int]] = None,
            build_timer : tp.Optional[Timer] = None,
            solve_timer : tp.Optional[Timer] = None,
            ) -> bool:
        pass

    def optimize_enum(self,
            optimizer : optimization.Optimizer,
            init_funcs : ConstraintGeneratorList,
            funcs : ConstraintGeneratorList,
            verbose : bool = False,
            attest_func : tp.Optional[ModelReader] = None,
            build_timer : tp.Optional[Timer] = None,
            solve_timer : tp.Optional[Timer] = None,
            cutoff : tp.Optional[float] = None,
            return_bounds : bool = False,
            max_sol : int = 5000,
            ) -> bool:
        if not verbose:
            log = lambda *args, **kwargs :  None
        else:
            log = ft.partial(print, sep='', flush=True)

        if not self._check_pigeons():
            log('Infeasible: too many pigeons')
            if return_bounds:
                return (False, None, None)
            else:
                return False

        solver = self._solver
        vars = self._vars
        cgra = self.cgra
        design = self.design
        args = cgra, design, vars, solver
        incremental = self._incremental


        if attest_func is None:
            attest_func : ModelReader = lambda *args : True

        if build_timer is None:
            build_timer = NullTimer()

        if solve_timer is None:
            solve_timer = NullTimer()

        if cutoff is None:
            def check_cutoff(lower, upper):
                return False
        elif cutoff == 0:
            def check_cutoff(lower, upper):
                return lower < upper
        else:
            def check_cutoff(lower, upper):
                return (upper - lower)/upper > cutoff


        if incremental:
            sat_cb = lambda : None
        else:
            sat_cb = self._reset

        def apply(*funcs : ConstraintGeneratorType):
            if not funcs:
                return
            log('Building constraints:')
            build_timer.start()
            for f in funcs:
                log('  ', f.__qualname__, end='... ')
                solver.Assert(f(*args))
                log('done')

            build_timer.stop()
            log('---\n')

        def do_checksat():
            solve_timer.start()
            s = solver.CheckSat()
            solve_timer.stop()
            return s

        def not_this(model : Model, vars : Modeler) -> int:
            build_timer.start()
            solver = vars._solver
            kx = []
            tx = []
            for k,v in model.items():
                n = k[0]
                if v == 1 and len(k) == 2 and optimizer.node_filter(n):
                    kx.append(k)
            assert kx
            c = []
            t = ft.reduce(solver.BVAnd, (vars[k] for k in kx))
            solver.Assert(t==0)
            build_timer.stop()

        eval_func = optimizer.eval_func
        lower_func = optimizer.lower_func

        if cutoff is None:
            funcs = *init_funcs, *funcs
        else:
            funcs = *init_funcs, *funcs


        apply(*funcs)

        if incremental:
            funcs = ()

        if do_checksat():
            init_time = solve_timer.total + build_timer.total
            print(init_time)
            lower = 0
            sol = 1
            best = m = vars.save_model()
            upper = eval_func(cgra, design, best)
            if check_cutoff(lower, upper):
                lower = lower_func(cgra, design)

            attest_func(cgra, design, best)

            log(f'bounds: [{lower}, {upper}])')

            while check_cutoff(lower, upper) \
                and solve_timer.times[-1] + build_timer.times[-1] <= init_time \
                and solve_timer.total + build_timer.total < init_time * 100:
                apply(*funcs)
                not_this(m, vars)

                if do_checksat():
                    m = vars.save_model()
                    e = eval_func(cgra, design, m)
                    if upper > e:
                        log(f'\nnew model eval: {e}')
                        upper = e
                        best = m
                    elif upper == e:
                        log('=', end='')
                    else:
                        log('+', end='')

                    sol += 1
                else:
                    log('solutions exhausted')
                    break


            self._model = best
            log(f'optimal found: {upper}')
            if return_bounds:
                return (True, lower, upper)
            else:
                return True
        else:
            if return_bounds:
                return (False, None, None)
            else:
                return False

    def optimize_design(self,
            optimizer : optimization.Optimizer,
            init_funcs : ConstraintGeneratorList,
            funcs : ConstraintGeneratorList,
            verbose : bool = False,
            attest_func : tp.Optional[ModelReader] = None,
            first_cut : tp.Optional[tp.Callable[[int, int], int]] = None,
            build_timer : tp.Optional[Timer] = None,
            solve_timer : tp.Optional[Timer] = None,
            cutoff : tp.Optional[float] = None,
            return_bounds : bool = False,
            optimize_final : bool = False,
            ) -> bool:

        if not verbose:
            log = lambda *args, **kwargs :  None
        else:
            log = ft.partial(print, sep='', flush=True)

        if not self._check_pigeons():
            log('Infeasible: too many pigeons')
            if return_bounds:
                return (False, None, None)
            else:
                return False

        solver = self._solver
        vars = self._vars
        cgra = self.cgra
        design = self.design
        args = cgra, design, vars, solver
        incremental = self._incremental


        if attest_func is None:
            attest_func : ModelReader = lambda *args : True
        else:
            _attest_func = attest_func
            def attest_func(cgra, design, model):
                _attest_func(cgra, design, model)
                for f in (
                    checker.op_placement,
                    checker.pe_exclusivity,
                    checker.pe_legality,
                    checker.route_exclusivity,
                    checker.init_value,
                    checker.port_placement,
                    checker.input_connectivity,
                    checker.output_connectivity,
                    checker.routing_resource_usage,
                    ):
                    f(cgra, design, model)


        if first_cut is None:
            first_cut = lambda l, u : int(max(u - 1, (u+l)/2))

        if build_timer is None:
            build_timer = NullTimer()

        if solve_timer is None:
            solve_timer = NullTimer()

        if cutoff is None:
            def check_cutoff(lower, upper):
                return False
        elif cutoff == 0:
            def check_cutoff(lower, upper):
                return lower < upper
        else:
            def check_cutoff(lower, upper):
                return (upper - lower)/upper > cutoff


        if incremental:
            sat_cb = solver.Push
            def unsat_cb():
                solver.Pop()
                solver.Push()
        else:
            sat_cb = self._reset
            unsat_cb = self._reset

        def apply(*funcs : ConstraintGeneratorType) -> tp.List[smt_switch_types.Term]:
            log('Building constraints:')
            build_timer.start()
            for f in funcs:
                log('  ', f.__qualname__, end='... ')
                solver.Assert(f(*args))
                log('done')
            build_timer.stop()
            log('---\n')

        def do_checksat():
            solve_timer.start()
            s = solver.CheckSat()
            solve_timer.stop()
            if s:
                log('sat')
            else:
                log('unsat')
            return s

        eval_func = optimizer.eval_func
        limit_func = optimizer.limit_func
        lower_func = optimizer.lower_func

        if cutoff is None and not optimize_final:
            funcs = *init_funcs, *funcs
        else:
            funcs = *init_funcs, optimizer.init_func, *funcs


        apply(*funcs)

        if incremental:
            funcs = ()

        if do_checksat():
            lower = 0
            best = vars.save_model()
            upper = eval_func(cgra, design, best)
            if check_cutoff(lower, upper) or optimize_final:
                lower = lower_func(cgra, design)
            next = first_cut(lower, upper)
            attest_func(cgra, design, best)
            sat_cb()

            next_f = None

            if not check_cutoff(lower, upper) and optimize_final:
                optimize_final = False
                def check_cutoff(lower, upper):
                    return lower < upper

                log('freazing placement')
                if incremental:
                    next_f = optimization.freaze_fus(best)
                else:
                    funcs = *funcs, optimization.freaze_fus(best)

            while check_cutoff(lower, upper):
                assert lower <= next <= upper
                log(f'bounds: [{lower}, {upper}])')
                log(f'next: {next}\n')

                f = limit_func(lower, next)
                if next_f is None:
                    apply(*funcs, f)
                else:
                    apply(*funcs, next_f, f)

                if do_checksat():
                    best = vars.save_model()
                    upper = eval_func(cgra, design, best)
                    attest_func(cgra, design, best)
                    sat_cb()
                else:
                    lower = next+1
                    unsat_cb()
                next = int((upper+lower)/2)

                next_f = None
                if not check_cutoff(lower, upper) and optimize_final:
                    optimize_final = False
                    def check_cutoff(lower, upper):
                        return lower < upper

                    log('freazing placement')
                    if incremental:
                        next_f = optimization.freaze_fus(best)
                    else:
                        funcs = *funcs, optimization.freaze_fus(best)


            self._model = best
            log(f'optimal found: {upper}')
            if return_bounds:
                return (True, lower, upper)
            else:
                return True
        else:
            if return_bounds:
                return (False, None, None)
            else:
                return False

    def solve(self, *, verbose : bool = False):
        if not self._check_pigeons():
            if verbose:
                print('Infeasible: too many pigeons', flush=True)
            return False
        solver = self._solver
        if verbose:
            print('Solving ...', flush=True)

        if not solver.CheckSat():
            solver.Reset()
            self._init_solver()
            return False

        self._model = self._vars.save_model()
        return True

    def attest_design(self, *funcs : ModelReader, verbose : bool = False):
        model = self._model
        assert model is not None
        args = self.cgra, self.design, model

        if verbose:
            for f in funcs:
                print(f.__qualname__, flush=True)
                f(*args)
        else:
            for f in funcs:
                f(*args)


    @property
    def cgra(self) -> MRRG:
        return self._cgra

    @property
    def design(self) -> Design:
        return self._design

