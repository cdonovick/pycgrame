import itertools as it
import functools as ft
import typing as tp
from collections import Counter
from smt_switch import smt
from modeler import Modeler
from design import Design
from mrrg import MRRG
import smt_switch_types
from constraints import ConstraintGeneratorType
from optimization import EvalType, OptGeneratorType
from modeler import Model, ModelReader

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
            incremental : bool = False):

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
        self._attest()
        self._model = None

    def _attest(self) -> None:
        op_hist = Counter()
        pe_hist = Counter()
        for op in self.design.operations:
            op_hist[op.opcode] += 1

        for pe in self.cgra.functional_units:
            for op in pe.ops:
                pe_hist[op] += 1
        for op, n in op_hist.items():
            assert pe_hist[op] >= n, (op, pe_hist)

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

    def optimize_design(self,
            init_func : ConstraintGeneratorType,
            eval_func : EvalType,
            constraint_func : OptGeneratorType,
            init_funcs : ConstraintGeneratorList,
            funcs : ConstraintGeneratorList,
            verbose : bool = False,
            attest_func : tp.Optional[ModelReader] = None) -> bool:
        solver = self._solver
        vars = self._vars
        cgra = self.cgra
        design = self.design
        args = cgra, design, vars, solver
        incremental = self._incremental

        if attest_func is None:
            attest_func : ModelReader = lambda *args : True

        if not verbose:
            log = lambda *args, **kwargs :  None
        else:
            log = ft.partial(print, sep='', flush=True)

        if incremental:
            sat_cb = solver.Push
            unsat_cb = solver.Pop
        else:
            sat_cb = self._reset
            unsat_cb = self._reset

        def apply(*funcs : ConstraintGeneratorType) -> tp.List[smt_switch_types.Term]:
            x = []
            log('Building constraints:')
            for f in funcs:
                log('  ', f.__qualname__, end='... ')
                solver.Assert(f(*args))
                log('done')
            log('---\n')


        apply(*init_funcs, init_func, *funcs)

        if incremental:
            funcs = ()
        else:
            funcs = *init_funcs, init_func, *funcs


        if solver.CheckSat():
            lower = 0
            best = vars.save_model()
            upper = eval_func(cgra, design, best)
            next = int((upper+lower)/2)
            attest_func(cgra, design, best)
            sat_cb()

            while lower < upper:
                assert lower <= next <= upper
                log(f'bounds: [{lower}, {upper}])')
                log(f'next: {next}\n')

                f = constraint_func(next)
                apply(*funcs, f)

                if solver.CheckSat():
                    best = vars.save_model()
                    upper = eval_func(cgra, design, best)
                    attest_func(cgra, design, best)
                    sat_cb()
                else:
                    lower = next+1
                    unsat_cb()
                next = int((upper+lower)/2)

            self._model = best
            assert lower == upper
            log(f'optimal found: {upper}')
            return True
        else:
            return False

    def solve(self, *, verbose : bool = False):
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

