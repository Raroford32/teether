import logging
from collections import defaultdict
from queue import PriorityQueue

from teether.util.frontierset import FrontierSet


class BackwardExplorerState(object):
    """
    Represents the state of the backward exploration process.
    """

    def __init__(self, bb, gas, must_visit, cost, data):
        """
        Initialize the BackwardExplorerState object.

        :param bb: Basic block (BB) representing the current state.
        :param gas: Remaining gas for exploration.
        :param must_visit: FrontierSet of nodes that must be visited.
        :param cost: Cost of the current state.
        :param data: Additional data associated with the state.
        """
        self.bb = bb
        self.gas = gas
        self.must_visit = must_visit.copy()
        self.data = data
        self.cost = cost

    def estimate(self):
        """
        Return an estimate of how quickly we can reach the root of the tree.
        This estimate is the sum of the number of branches taken so far (self.cost) and the
        estimate given by the next BB to visit (self.bb.estimate).

        :return: Estimated distance to root.
        """
        if self.bb.estimate_constraints is None:
            return self.cost
        else:
            return self.cost + self.bb.estimate_constraints

    def rank(self):
        """
        Compute a rank for this state. Order by estimated root-distance first, solve ties by favoring less restricted states
        for caching efficiency.

        :return: Rank of the state.
        """
        return self.estimate(), len(self.must_visit)

    def __lt__(self, other):
        return self.rank() < other.rank()

    def __hash__(self):
        return sum(a * b for a, b in zip((23, 29, 31), (hash(self.bb), hash(self.must_visit), hash(self.data))))

    def __eq__(self, other):
        return self.bb == other.bb and self.must_visit == other.must_visit and self.data == other.data

    def __str__(self):
        return 'At: %x, Gas: %s, Must-Visit: %s, Data: %s, Hash: %x' % (
            self.bb.start, self.gas, self.must_visit, self.data, hash(self))


def generate_sucessors(state: BackwardExplorerState, new_data, update_data, predicate=lambda st, pred: True):
    """
    Generate successor states for the given state.

    :param state: Current state.
    :param new_data: New data to be used for generating successors.
    :param update_data: Function to update the data for the new state.
    :param predicate: Predicate function to filter successor states.
    :return: List of successor states.
    """
    new_todo = []
    if state.gas is None or state.gas > 0:
        new_gas = state.gas
        if state.gas and len(state.bb.pred) > 1:
            new_gas = state.gas - 1

        for p in state.bb.pred:
            if not predicate(state.data, p):
                continue

            new_must_visits = []
            for path in state.bb.pred_paths[p]:
                new_must_visit = state.must_visit.copy()
                for a, b in zip(path[:-1], path[1:]):
                    new_must_visit.add(b, a)
                if p.start in new_must_visit.frontier:
                    new_must_visit.remove(p.start)
                if not new_must_visit.all.issubset(p.ancestors):
                    continue
                new_must_visits.append(new_must_visit)

            new_cost = state.cost + (1 if p.branch else 0)

            for new_must_visit in minimize(new_must_visits):
                new_todo.append(BackwardExplorerState(p, new_gas, new_must_visit, new_cost, update_data(new_data, p)))
    return new_todo


def traverse_back(start_ins, initial_gas, initial_data, advance_data, update_data, finish_path, must_visits=[],
                  predicate=lambda st, p: True):
    """
    Traverse the control flow graph backward from the given starting instructions.

    :param start_ins: Starting instructions.
    :param initial_gas: Initial gas for exploration.
    :param initial_data: Initial data for exploration.
    :param advance_data: Function to advance the data.
    :param update_data: Function to update the data.
    :param finish_path: Function to check if the path is finished.
    :param must_visits: FrontierSet describing the next nodes that must be visited.
    :param predicate: Predicate function to filter successor states.
    :return: Yields paths as they are explored one-by-one.
    """
    todo = PriorityQueue()

    for ins in start_ins:
        data = initial_data(ins)
        bb = ins.bb
        gas = initial_gas
        if not must_visits:
            must_visits = [FrontierSet()]
        for must_visit in minimize(FrontierSet(mv) if mv is not FrontierSet else mv for mv in must_visits):
            ts = BackwardExplorerState(bb, gas, must_visit, 0, data)
            todo.put(ts)

    cache = set()
    ended_prematurely = defaultdict(int)
    while not todo.empty():
        state = todo.get()
        if len(state.bb.succ) > 1:
            if state in cache:
                continue
            cache.add(state)
        new_data = advance_data(state.data)
        if finish_path(new_data):
            yield new_data
        else:
            if state.gas is not None and state.bb.estimate_back_branches is not None and (state.gas == 0 or state.gas < state.bb.estimate_back_branches):
                ended_prematurely[state.bb.start] += 1
            else:
                new_todo = generate_sucessors(state, new_data, update_data, predicate=predicate)
                for nt in new_todo:
                    todo.put(nt)
    total_ended = sum(ended_prematurely.values())
    if total_ended:
        logging.info("%d paths that ended prematurely due to branches: %s", total_ended,
                     ', '.join('%x: %d' % (k, v) for k, v in ended_prematurely.items()))
    else:
        logging.info("Finished all paths")


def minimize(must_visits):
    """
    Minimize the list of must-visit sets by removing subsets.

    :param must_visits: List of must-visit sets.
    :return: Generator yielding minimized must-visit sets.
    """
    todo = sorted(must_visits, key=len)
    while todo:
        must_visit = todo[0]
        yield must_visit
        todo = [mv for mv in todo[1:] if not must_visit.issubset(mv)]
