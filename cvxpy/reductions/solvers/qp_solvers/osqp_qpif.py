import cvxpy.settings as s
from cvxpy.reductions.solvers import utilities
import cvxpy.interface as intf
from cvxpy.reductions import Solution
from cvxpy.reductions.solvers.qp_solvers.qp_solver import QpSolver
import numpy as np
import scipy.sparse as sp


class OSQP(QpSolver):
    """QP interface for the OSQP solver"""

    # Map of OSQP status to CVXPY status.
    STATUS_MAP = {1: s.OPTIMAL,
                  -2: s.SOLVER_ERROR,     # Maxiter reached
                  -3: s.INFEASIBLE,
                  -4: s.UNBOUNDED,
                  -5: s.SOLVER_ERROR,     # Interrupted by user
                  -10: s.SOLVER_ERROR}    # Unsolved

    def name(self):
        return s.OSQP

    def import_solver(self):
        import osqp
        osqp

    def invert(self, solution, inverse_data):
        attr = {s.SOLVE_TIME: solution.info.run_time}

        # Map OSQP statuses back to CVXPY statuses
        status = self.STATUS_MAP.get(solution.info.status_val, s.SOLVER_ERROR)

        if status in s.SOLUTION_PRESENT:
            opt_val = solution.info.obj_val
            primal_vars = {
                inverse_data.id_map.keys()[0]:
                intf.DEFAULT_INTF.const_to_matrix(np.array(solution.x))
            }
            dual_vars = utilities.get_dual_values(
                intf.DEFAULT_INTF.const_to_matrix(solution.y),
                utilities.extract_dual_value,
                inverse_data.sorted_constraints)
            attr[s.NUM_ITERS] = solution.info.iter
        else:
            primal_vars = None
            dual_vars = None
            opt_val = np.inf
            if status == s.UNBOUNDED:
                opt_val = -np.inf
        return Solution(status, opt_val, primal_vars, dual_vars, attr)

    def solve_via_data(self, data, warm_start, verbose, solver_opts,
                       solver_cache=None):
        import osqp
        P = data[s.P]
        q = data[s.Q]
        A = sp.vstack([data[s.A], data[s.F]]).tocsc()
        u = np.concatenate((data[s.B], data[s.G]))
        l = np.concatenate([data[s.B], -np.inf*np.ones(data[s.G].shape)])

        if solver_cache[self.name]:
            # Use cached data.
            solver, old_data, results = solver_cache[self.name]
            same_pattern = (P.shape == old_data[s.P].shape and
                            all(P.indptr == old_data[s.P].row)) and \
                           (A.shape == old_data[s.A].shape and
                            all(A.indptr == old_data[s.A].row))
        else:
            same_pattern = False


        # If sparsity pattern differs need to do setup.
        if warm_start and solver_cache[self.name] and same_pattern:
            new_args = {'q': q, 'u': u, 'l': l}
            if any(P.indices != old_data[s.P].indices):
                new_args['Px_idx']
            if any(P.data != old_data[s.P].data):
                new_args['Px']
            if any(A.indices != old_data[s.A].indices):
                new_args['Ax_idx']
            if any(A.data != old_data[s.A].data):
                new_args['Ax']
            solver.update(**new_args)
            solver.update_settings(verbose=verbose, **solver_opts)
            # Map OSQP statuses back to CVXPY statuses
            status = self.STATUS_MAP.get(results.info.status_val, s.SOLVER_ERROR)
            if status == OPTIMAL:
                solver.warm_start(results.x, results.y)
            results = solver.solve()
        else:
            # Initialize and solve problem
            solver = osqp.OSQP()
            solver.setup(P, q, A, l, u, verbose=verbose, **solver_opts)
            results = solver.solve()

        solver_cache[self.name] = (solver, data, results)
        return results