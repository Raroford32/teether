import logging
from collections import defaultdict, deque

from teether.util.utils import unique


class BB(object):
    """
    Basic Block (BB) class representing a sequence of instructions with no branches.
    """

    def __init__(self, ins: list) -> None:
        """
        Initialize the BB object.

        :param ins: List of instructions in the basic block.
        """
        self.ins = ins
        self.streads = set()  # indices of stack-items that will be read by this BB (0 is the topmost item on stack)
        self.stwrites = set()  # indices of stack-items that will be written by this BB (0 is the topmost item on stack)
        self.stdelta = 0
        for i in ins:
            i.bb = self
            if 0x80 <= i.op <= 0x8f:  # Special handling for DUP
                ridx = i.op - 0x80 - self.stdelta
                widx = -1 - self.stdelta
                if ridx not in self.stwrites:
                    self.streads.add(ridx)
                self.stwrites.add(widx)
            elif 0x90 <= i.op <= 0x9f:  # Special handling for SWAP
                idx1 = i.op - 0x8f - self.stdelta
                idx2 = - self.stdelta
                if idx1 not in self.stwrites:
                    self.streads.add(idx1)
                if idx2 not in self.stwrites:
                    self.streads.add(idx2)
                self.stwrites.add(idx1)
                self.stwrites.add(idx2)
            else:  # assume entire stack is affected otherwise
                for j in range(i.ins):
                    idx = j - self.stdelta
                    if idx not in self.stwrites:
                        self.streads.add(idx)
                for j in range(i.outs):
                    idx = i.ins - 1 - j - self.stdelta
                    self.stwrites.add(idx)
            self.stdelta += i.delta
        self.streads = {x for x in self.streads if x >= 0}
        self.stwrites = {x for x in self.stwrites if x >= 0}
        self.start = self.ins[0].addr
        self.pred = set()
        self.succ = set()
        self.succ_addrs = set()
        self.pred_paths = defaultdict(set)
        self.branch = self.ins[-1].op == 0x57
        self.indirect_jump = self.ins[-1].op in (0x56, 0x57)
        self.ancestors = set()
        self.descendants = set()
        # maintain a set of 'must_visit' constraints to limit
        # backward-slices to only new slices after new edges are added
        # initially, no constraint is given (= empty set)
        self.must_visit = [set()]
        # also maintain an estimate of how fast we can get from here
        # to the root of the cfg
        # how fast meaning, how many JUMPI-branches we have to take
        self.estimate_constraints = (1 if self.branch else 0) if self.start == 0 else None
        # and another estimate fo many backwards branches
        # we will encounter to the root
        self.estimate_back_branches = 0 if self.start == 0 else None

    @property
    def jump_resolved(self) -> bool:
        """
        Check if the jump target is resolved.

        :return: True if the jump target is resolved, False otherwise.
        """
        return not self.indirect_jump or len(self.must_visit) == 0

    def update_ancestors(self, new_ancestors: set) -> None:
        """
        Update the ancestors of the basic block.

        :param new_ancestors: Set of new ancestors to be added.
        """
        new_ancestors = new_ancestors - self.ancestors
        if new_ancestors:
            self.ancestors.update(new_ancestors)
            for s in self.succ:
                s.update_ancestors(new_ancestors)

    def update_descendants(self, new_descendants: set) -> None:
        """
        Update the descendants of the basic block.

        :param new_descendants: Set of new descendants to be added.
        """
        new_descendants = new_descendants - self.descendants
        if new_descendants:
            self.descendants.update(new_descendants)
            for p in self.pred:
                p.update_descendants(new_descendants)

    def update_estimate_constraints(self) -> None:
        """
        Update the estimate constraints of the basic block.
        """
        if all(p.estimate_constraints is None for p in self.pred):
            return
        best_estimate = min(p.estimate_constraints for p in self.pred if p.estimate_constraints is not None)
        if self.estimate_constraints is None or best_estimate + (1 if self.branch else 0) < self.estimate_constraints:
            self.estimate_constraints = best_estimate + (1 if self.branch else 0)
            for s in self.succ:
                s.update_estimate_constraints()

    def update_estimate_back_branches(self) -> None:
        """
        Update the estimate back branches of the basic block.
        """
        if all(p.estimate_back_branches is None for p in self.pred):
            return
        best_estimate = min(p.estimate_back_branches for p in self.pred if p.estimate_back_branches is not None)
        if self.estimate_back_branches is None or best_estimate + (1 if self.branch else 0) < self.estimate_back_branches:
            self.estimate_back_branches = best_estimate + (1 if self.branch else 0)
            for s in self.succ:
                s.update_estimate_back_branches()

    def add_succ(self, succ: 'BB', path: set) -> None:
        """
        Add a successor to the basic block.

        :param succ: Successor basic block.
        :param path: Set of addresses representing the path to the successor.
        """
        if succ not in self.succ:
            self.succ.add(succ)
            succ.pred.add(self)
            self.succ_addrs.add(succ.start)
            self.pred_paths[succ].add(frozenset(path))
            self.update_descendants({succ})
            succ.update_ancestors({self})
            self.update_estimate_constraints()
            self.update_estimate_back_branches()
        else:
            self.pred_paths[succ].add(frozenset(path))

    def get_succ_addrs(self, valid_jump_targets: set) -> set:
        """
        Get the addresses of the successor basic blocks.

        :param valid_jump_targets: Set of valid jump targets.
        :return: Set of addresses of the successor basic blocks.
        """
        if self.ins[-1].op == 0x56:  # JUMP
            return {self.ins[-1].arg} if self.ins[-1].arg in valid_jump_targets else set()
        elif self.ins[-1].op == 0x57:  # JUMPI
            return {self.ins[-1].arg} if self.ins[-1].arg in valid_jump_targets else set()
        else:
            return {self.ins[-1].addr + self.ins[-1].size}

    def __str__(self) -> str:
        """
        Get the string representation of the basic block.

        :return: String representation of the basic block.
        """
        return '\n'.join(str(i) for i in self.ins)
