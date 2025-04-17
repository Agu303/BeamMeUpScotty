import numpy as np
from typing import Optional, List, Union, Tuple
from load import *

class BEAM:
    fix_fix = 1
    fix_pin = 2
    pin_fix = 3
    pin_pin = 4


    def __init( 
            self,
            lengths: Optional[List[float]] = None,
            flex_list: Optional[Union[float, List[float]]] = None,
            constraints:   Optional[List[int]] = None,
            loadsList:  Optional[LoadMatrix] = None,
            element_types:  Optional[List[int]] = None
    )
        self.lengths = []
        self.flex_list = []
        self.element_types = []
        self.constraints = [] 
        self.loadsList = []
        self.nodeCoords = [0.0]

    #def addLength();
        
