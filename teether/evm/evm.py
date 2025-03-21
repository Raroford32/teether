import datetime
import logging
from collections import defaultdict
from typing import List, Dict, Union, Optional

from z3 import z3

import teether.util.utils
from teether.evm.exceptions import ExternalData, SymbolicError, IntractablePath, VMException
from teether.evm.results import SymbolicResult, gen_exec_id
from teether.evm.state import SymRead, EVMState, SymbolicEVMState
from teether.util.z3_extra_util import concrete, is_true


class Context(object):
    def __init__(self):
        self.address = 0
        self.balance = dict()
        self.origin = 0
        self.caller = 0
        self.callvalue = 0
        self.calldata = []
        self.gasprice = 0
        self.coinbase = 0
        self.timestamp = 0
        self.number = 0
        self.difficulty = 0
        self.gaslimit = 0
        self.storage = defaultdict(int)


def run(program
