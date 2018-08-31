import itertools as it
from collections import Counter
from smt_switch import smt


class PNR:
    def __init__(self, cgra, design, solver_str, seed=1):
        self._cgra = cgra
        self._design = design

        self._map_state =dict()
        self._map_vars = dict()
        

        self._solver = smt(solver_str)
        self._solver_opts = solver_opts = [('random-seed', seed)]
        if solver_str == 'CVC4':
            solver_opts.append(('bitblast', 'eager'))
            solver_opts.append(('bv-sat-solver', 'cryptominisat'))

        self._init_solver()
        self._attest()

    def _attest(self):
        op_hist = Counter()
        pe_hist = Counter()
        for op in self.design.operations:
            op_hist[op.opcode] += 1

        for pe in self.cgra.functional_units:
            for op in pe.ops:
                pe_hist[op] += 1
        for op, n in op_hist.items():
            assert pe_hist[op] >= n, (op, pe_hist)

    def _init_solver(self):
        solver = self._solver

        solver.SetOption('produce-models', 'true')
        solver.SetLogic('QF_BV')
        for opts in self._solver_opts:
            solver.SetOption(*opts)

    def pin_module(self, module, placement):
        raise NotImplementedError()

    def pin_tie(self, tie, placement):
        raise NotImplementedError()

    def map_design(self, *funcs, verbose=False):
        solver = self._solver
        args = self.cgra, self.design, self._map_state, self._map_vars, solver

        constraints = []
        if verbose:
            for f in funcs:
                print(f.__qualname__, end='... ', flush=True)
                c = f(*args)
                print('done', flush=True)
                solver.Assert(c)
        else:
            for f in funcs:
                solver.Assert(f(*args))

    def solve(self, *, verbose=False):
        solver = self._solver
        if verbose:
            print('Solving ...', flush=True)

        if not solver.CheckSat():
            solver.Reset()
            self._init_solver()
            return False

        return True

    def attest_design(self, *funcs, verbose=False):
        solver = self._solver
        args = self.cgra, self.design, self._map_state, self._map_vars, solver

        if verbose:
            for f in funcs:
                print(f.__qualname__, end='... ', flush=True)
                f(*args)
                print('done', flush=True)
        else:
            for f in funcs:
                f(*args)



    def write_design(self, model_writer):
        model_writer(self._place_state, self._route_state)

    @property
    def cgra(self):
        return self._cgra

    @property
    def design(self):
        return self._design

