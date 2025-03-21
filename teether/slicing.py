from teether.cfg.instruction import Instruction
from teether.cfg.opcodes import potentially_user_controlled
from teether.explorer.backward import traverse_back
from teether.util.intrange import Range
from typing import List, Set, Tuple, Union, Optional


def slice_to_program(s: List[Instruction]) -> dict:
    """
    Convert a slice of instructions to a program.

    :param s: List of instructions in the slice.
    :return: Dictionary representing the program.
    """
    pc = 0
    program = {}
    for ins in s:
        program[pc] = ins
        pc += ins.next_addr - ins.addr
    return program


def adjust_stack(backward_slice: List[Instruction], stack_delta: int) -> None:
    """
    Adjust the stack by adding or removing instructions.

    :param backward_slice: List of instructions in the backward slice.
    :param stack_delta: Stack delta to adjust.
    """
    if stack_delta > 0:
        backward_slice.extend(Instruction(0x0, 0x63, b'\xde\xad\xc0\xde') for _ in range(abs(stack_delta)))
    elif stack_delta < 0:
        backward_slice.extend(Instruction(0x0, 0x50) for _ in range(abs(stack_delta)))


class SlicingState:
    """
    Represents the state of the slicing process.
    """

    def __init__(self, stacksize: int, stack_underflow: int, stack_delta: int, taintmap: Set[int], memory_taint: Range,
                 backward_slice: List[Instruction], instructions: List[Instruction]):
        """
        Initialize the SlicingState object.

        :param stacksize: Current stack size.
        :param stack_underflow: Stack underflow value.
        :param stack_delta: Stack delta value.
        :param taintmap: Set of tainted stack indices.
        :param memory_taint: Range of tainted memory.
        :param backward_slice: List of instructions in the backward slice.
        :param instructions: List of instructions to be processed.
        """
        self.stacksize = stacksize
        self.stack_underflow = stack_underflow
        self.stack_delta = stack_delta
        self.taintmap = frozenset(taintmap)
        self.memory_taint = memory_taint
       
