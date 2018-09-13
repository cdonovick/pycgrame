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

class PNR:
    _cgra : MRRG
    _design : Design
    _vars : Modeler
    _solver : smt_switch_types.Solver
    _model : tp.Optional[Model]
    _solver_opts : tp.List[tp.Tuple[str, str]]

    def __init__(self,
            cgra : MRRG,
            design : Design,
            solver_str : str,
            seed : int = 0):

        self._cgra = cgra
        self._design  = design

        self._solver = solver = smt(solver_str)
        self._solver_opts = solver_opts = [('random-seed', seed)]
        if solver_str == 'CVC4':
            solver_opts.append(('bitblast', 'eager'))
            solver_opts.append(('bv-sat-solver', 'cryptominisat'))

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

        solver.SetOption('produce-models', 'true')
        solver.SetLogic('QF_BV')
        for opts in self._solver_opts:
            solver.SetOption(*opts)

    def pin_module(self, module, placement):
        raise NotImplementedError()

    def pin_tie(self, tie, placement):
        raise NotImplementedError()

    def map_design(self, *funcs : ConstraintGeneratorType, verbose : bool = False) -> None:
        solver = self._solver
        args = self.cgra, self.design, self._vars, solver

        if verbose:
            for f in funcs:
                print(f.__qualname__, end='... ', flush=True)
                c = f(*args)
                print('done', flush=True)
                solver.Assert(c)
        else:
            for f in funcs:
                solver.Assert(f(*args))

    def optimize_design(self,
            eval_func : EvalType,
            constraint_func : OptGeneratorType,
            *funcs : ConstraintGeneratorType,
            verbose : bool = True,
            attest_func : tp.Optional[ModelReader] = None) -> bool:
        solver = self._solver
        vars = self._vars
        cgra = self.cgra
        design = self.design
        args = cgra, design, vars, solver

        if attest_func is None:
            attest_func : ModelReader = lambda *args : True

        if not verbose:
            lprint = lambda *args, **kwargs :  None
        else:
            lprint = ft.partial(print, sep='', flush=True)

        def apply(*funcs : ConstraintGeneratorType):
            lprint('Building constraints:')
            for f in funcs:
                lprint('  ', f.__qualname__, end='... ')
                c = f(*args)
                solver.Assert(c)
                lprint('done')
            lprint('---\n')

        apply(*funcs)
        if solver.CheckSat():
            lower = 0
            best = vars.save_model()
            upper = eval_func(cgra, design, best)
            next = int((upper+lower)/2)
            attest_func(cgra, design, best)

            while lower < upper:
                assert lower <= next <= upper
                lprint(f'bounds: [{lower}, {upper}])')
                lprint(f'next: {next}\n')
                self._reset()

                f = constraint_func(next)
                apply(*funcs, f)
                if solver.CheckSat():
                    best = vars.save_model()
                    upper = eval_func(cgra, design, best)
                    attest_func(cgra, design, best)
                else:
                    lower = next+1
                next = int((upper+lower)/2)

            self._model = best
            assert lower == upper
            lprint(f'optimal found: {upper}')
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

