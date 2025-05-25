import numpy as np
from scipy.linalg import solve as lin_solve

class StructuralSolver:
    """Finite‑element solver for 2D truss / beam systems.
    * Truss nodes: UX, UY (translations)
    * Beam/Frame nodes: UX, UY, THETA (rotation)
    The code always builds 3‑DOF/node global matrices; truss
    elements simply leave rotational entries zero. This keeps
    the implementation compact while supporting mixed models.
    """
    def __init__(self):
        self.nodes: dict[int, np.ndarray] = {}
        self.elements: dict[int, dict] = {}
        self.materials: dict[int, dict] = {}
        self.sections: dict[int, dict] = {}
        self.loads: dict[int, dict] = {}
        self.boundary_conditions: dict[int, dict] = {}
        self.results = {}

    # ---------- helpers ---------------------------------------------------
    @staticmethod
    def _truss_k_local(E, A, L):
        return (E*A/L) * np.array([[ 1,  0, -1,  0],
                                   [ 0,  0,  0,  0],
                                   [-1,  0,  1,  0],
                                   [ 0,  0,  0,  0]], dtype=float)

    @staticmethod
    def _beam_k_local(E, A, I, L):
        k = np.zeros((6,6))
        EA_L = E*A / L
        EI_L3 = E*I / L**3
        EI_L2 = E*I / L**2
        EI_L1 = E*I / L
        # axial
        k[0,0] = k[3,3] = EA_L
        k[0,3] = k[3,0] = -EA_L
        # bending
        k[1,1] = k[4,4] = 12*EI_L3
        k[1,4] = k[4,1] = -12*EI_L3
        k[1,2] = k[2,1] = k[1,5] = k[5,1] = 6*EI_L2
        k[4,2] = k[2,4] = k[4,5] = k[5,4] = -6*EI_L2
        k[2,2] = k[5,5] = 4*EI_L1
        k[2,5] = k[5,2] = 2*EI_L1
        return k

    @staticmethod
    def _transformation_matrix(c, s):
        T = np.zeros((6,6))
        # ux
        T[0,0] =  c; T[0,1] =  s
        T[3,3] =  c; T[3,4] =  s
        # uy
        T[1,0] = -s; T[1,1] =  c
        T[4,3] = -s; T[4,4] =  c
        # theta  (out‑of‑plane, unchanged)
        T[2,2] = T[5,5] = 1.0
        return T

    # ---------- model definition ------------------------------------------
    def add_node(self, nid: int, x: float, y: float):
        if nid in self.nodes:
            raise ValueError(f"Node {nid} already exists")
        self.nodes[nid] = np.array([x, y], float)

    def add_material(self, mid: int, E: float, nu: float = 0.3, rho: float = 0):
        self.materials[mid] = {'E':E, 'nu':nu, 'rho':rho}

    def add_section(self, sid: int, A: float, I: float = 0):
        self.sections[sid] = {'A':A, 'I':I}

    def add_element(self, eid: int, n1: int, n2: int, etype: str = 'truss',
                    mat: int | None = None, sec: int | None = None):
        if etype not in ('truss','beam'):
            raise ValueError('etype must be truss or beam')
        if mat is None:
            mat = next(iter(self.materials))  # first material
        if sec is None:
            sec = next(iter(self.sections))   # first section
        self.elements[eid] = {'nodes':[n1,n2], 'type':etype,
                              'mat':mat, 'sec':sec}

    def add_load(self, nid: int, fx=0, fy=0, m=0):
        # replace existing load values instead of accumulating
        self.loads[nid] = {'fx': fx, 'fy': fy, 'm': m}

    def add_boundary_condition(self, nid: int, ux=None, uy=None, th=None):
        bc = self.boundary_conditions.setdefault(nid, {'ux':None,'uy':None,'th':None})
        if ux is not None: bc['ux']=ux
        if uy is not None: bc['uy']=uy
        if th is not None: bc['th']=th

    # ---------- assembly ---------------------------------------------------
    def _element_dof_indices(self, n1, n2):
        idx = lambda n: [3*(n-1)+i for i in range(3)]
        return idx(n1)+idx(n2)

    def _element_stiffness_global(self, eid: int):
        el = self.elements[eid]
        n1,n2 = el['nodes']
        x1,y1 = self.nodes[n1]
        x2,y2 = self.nodes[n2]
        dx = x2-x1; dy=y2-y1
        L = np.hypot(dx,dy)
        c = dx/L; s = dy/L
        mat = self.materials[el['mat']]
        sec = self.sections[el['sec']]
        E = mat['E']; A = sec['A']; I = sec['I']
        
        # determine effective element type based on global analysis mode
        # effective_type = el['type'] # original line
        # if self.current_analysis_mode == 'truss': # removed block
        #     effective_type = 'truss'

        # now, element type from el['type'] is directly used.
        # if el['type'] is 'truss', truss formulation is used.
        # if el['type'] is 'beam', beam formulation is used.
        # the gui now only creates 'beam' type elements, but if a file were loaded
        # with 'truss' elements, this logic would respect it.
        # for typical gui usage, el['type'] will be 'beam'.
        if el['type'] =='truss':
            k4 = self._truss_k_local(E,A,L)
            # embed into 6x6 (rot dofs zero)
            k6 = np.zeros((6,6))
            map4=[0,1,3,4]  # positions ux,uy,ux,uy inside 6×6
            for i,r in enumerate(map4):
                for j,c2 in enumerate(map4):
                    k6[r,c2]=k4[i,j]
            T = self._transformation_matrix(c,s)
        else:  # beam
            k6_local = self._beam_k_local(E,A,I,L)
            T = self._transformation_matrix(c,s)
            k6 = T.T @ k6_local @ T
        return k6

    def assemble_global_K(self):
        ndof = 3*len(self.nodes)
        K = np.zeros((ndof,ndof))
        for eid in self.elements:
            k = self._element_stiffness_global(eid)
            n1,n2 = self.elements[eid]['nodes']
            dofs = self._element_dof_indices(n1,n2)
            for i,gi in enumerate(dofs):
                for j,gj in enumerate(dofs):
                    K[gi,gj]+=k[i,j]
        return K

    def assemble_F(self):
        ndof = 3*len(self.nodes)
        F = np.zeros(ndof)
        
        # ensure all nodes have load entries (with zeros for those not explicitly defined)
        for nid in self.nodes:
            if nid not in self.loads:
                # add zero loads for this node
                self.loads[nid] = {'fx': 0, 'fy': 0, 'm': 0}
        
        # apply all loads to the force vector
        for nid, ld in self.loads.items():
            di = 3*(nid-1)
            F[di] = ld['fx']
            F[di+1] = ld['fy']
            F[di+2] = ld['m']
            
        return F

    # ---------- BC application & solving ----------------------------------
    def _bc_fixed_indices(self):
        fixed=[]
        for nid,bc in self.boundary_conditions.items():
            di=3*(nid-1)
            if bc.get('ux') is not None: fixed.append(di)
            if bc.get('uy') is not None: fixed.append(di+1)
            # in truss mode, rotational dofs are effectively free unless explicitly fixed
            # (though they won't carry moment). for frame mode, they can be fixed.
            if bc.get('th') is not None: # simplified: always check 'th' for frame-like behavior
                fixed.append(di+2)
        return sorted(set(fixed))

    def solve(self, analysis_mode=None):
        # self.current_analysis_mode = analysis_mode # store it - removed
        if not self.nodes or not self.elements:
            raise RuntimeError('Add nodes and elements before solving.')
        
        # check if we have boundary conditions
        if not self.boundary_conditions:
            raise RuntimeError('No boundary conditions defined. The structure must be constrained.')
            
        K = self.assemble_global_K()
        F = self.assemble_F()
        fixed = self._bc_fixed_indices()
        
        # check if we have enough constraints
        if not fixed:
            raise RuntimeError('No constrained degrees of freedom. Add at least one boundary condition.')
            
        all_idx = np.arange(K.shape[0])
        free = np.setdiff1d(all_idx, fixed)
        Kff = K[np.ix_(free,free)]
        Ff = F[free]
        
        # check if the stiffness matrix is likely to be singular
        try:
            # check the condition number to identify potential singularity
            cond_num = np.linalg.cond(Kff)
            if cond_num > 1e15:  # very high condition number indicates near-singularity
                rigid_body_message = self._check_rigid_body_modes()
                raise RuntimeError(f"Structure is likely under-constrained (condition number: {cond_num:.1e}).\n{rigid_body_message}")
                
            # try to solve the system
            Uf = lin_solve(Kff, Ff)
            
        except np.linalg.LinAlgError:
            # if linear algebra error occurs, try to give helpful feedback
            rigid_body_message = self._check_rigid_body_modes()
            raise RuntimeError(f"Stiffness matrix is singular. The structure is under-constrained.\n{rigid_body_message}")
            
        # if we get here, the solve was successful
        U = np.zeros_like(F)
        U[free] = Uf
        
        # store results
        self.results['displacements'] = U
        self.results['forces'] = {} # will store local forces
        for eid in self.elements:
            el = self.elements[eid]
            n1, n2 = el['nodes']
            x1,y1 = self.nodes[n1]
            x2,y2 = self.nodes[n2]
            dx = x2-x1; dy=y2-y1
            L = np.hypot(dx,dy)
            c = dx/L; s = dy/L
            
            T = self._transformation_matrix(c,s) # transformation matrix
            
            dofs = self._element_dof_indices(n1,n2)
            ue_global = U[dofs] # global displacements for this element
            ue_local = T @ ue_global # transform global displacements to local

            mat = self.materials[el['mat']]
            sec = self.sections[el['sec']]
            E = mat['E']; A = sec['A']; I = sec['I']

            k_local_actual = np.zeros((6,6))
            if el['type'] == 'truss' or I < 1e-9: # consider negligible i as truss for local k
                k4_local = self._truss_k_local(E,A,L)
                # embed 4x4 truss k_local into 6x6 k_local_actual
                # dofs for 4x4 are [u1, v1, u2, v2]
                # dofs for 6x6 are [u1, v1, th1, u2, v2, th2]
                # mapping local 4-dof indices to local 6-dof indices for truss:
                # u1 -> 0, v1 -> 1, u2 -> 3, v2 -> 4
                idx_map_4_to_6 = [0, 1, 3, 4]
                for i_4x4, i_6x6 in enumerate(idx_map_4_to_6):
                    for j_4x4, j_6x6 in enumerate(idx_map_4_to_6):
                        k_local_actual[i_6x6, j_6x6] = k4_local[i_4x4, j_4x4]
            else: # beam element
                k_local_actual = self._beam_k_local(E,A,I,L)
            
            fe_local = k_local_actual @ ue_local # calculate local forces
            self.results['forces'][eid] = fe_local
            
        # reactions (optional) - reactions are k_global @ u_global - f_global, so this part is fine
        R = K @ U - F
        self.results['reactions'] = {}
        for nid in self.boundary_conditions:
            di = 3*(nid-1)
            # report all 3 dofs for reactions, even if one is conceptually zero for truss analysis
            self.results['reactions'][nid] = R[di:di+3]
            
        return U
        
    def _check_rigid_body_modes(self):
        """Check for common issues with rigid body modes and provide feedback"""
        messages = []
        
        # check for rigid body translation
        constrained_x = any(bc.get('ux') == 0 for bc in self.boundary_conditions.values())
        constrained_y = any(bc.get('uy') == 0 for bc in self.boundary_conditions.values())
        
        if not constrained_x:
            messages.append("- Structure can translate freely in X direction")
        if not constrained_y:
            messages.append("- Structure can translate freely in Y direction")
            
        # check for rigid body rotation (only relevant for frame analysis)
        # if self.current_analysis_mode == 'frame': # this check is always relevant now
        # for rotation constraint, we need either:
        # 1. at least one rotational dof constrained, or
        # 2. at least two translational constraints at different locations
        rotation_constrained = any(bc.get('th') == 0 for bc in self.boundary_conditions.values())
        
        if not rotation_constrained:
            # check if we have at least two points constrained in any direction
            constrained_nodes = [nid for nid, bc in self.boundary_conditions.items()
                                if bc.get('ux') == 0 or bc.get('uy') == 0]
            
            if len(constrained_nodes) < 2:
                messages.append("- Structure can rotate freely (need either a rotation constraint or two separated translation constraints)")
        
        # check if any elements are using beam elements in truss mode - this check is less relevant now as gui makes beams
        # but if a file loaded elements with type 'truss' and i=0, they'd behave as trusses.
        # if self.current_analysis_mode == 'truss':
        #     beam_elements = [eid for eid, el in self.elements.items() if el['type'] == 'beam']
        #     if beam_elements:
        #         messages.append(f"- {len(beam_elements)} beam elements found in truss analysis mode (they will be treated as truss elements)")
        
        # create helpful message
        if messages:
            return "Possible issues detected:\n" + "\n".join(messages) + "\n\nAdd appropriate boundary conditions to fully constrain the structure."
        else:
            return "No obvious rigid body modes detected, but the structure may still be unstable."

    def get_element_axial_force(self, eid: int) -> float | None:
        """Returns the axial force for a given element ID from the results.
           Assumes N1 = -N2, so returns N1. Positive for tension, negative for compression.
           Returns None if results are not available or element not found.
        """
        if 'forces' not in self.results or eid not in self.results['forces']:
            return None
        
        # fe = [n1, v1, m1, n2, v2, m2] in local coordinates
        local_forces = self.results['forces'][eid]
        axial_force_n1 = local_forces[0]
        # axial_force_n2 = local_forces[3] # should be -n1
        return -axial_force_n1 # return negative n1 to align with compression(+) / tension(-)

    def get_element_shear_moment(self, eid: int, num_points: int = 11) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
        """Calculates shear force and bending moment along an element.
        
        Args:
            eid: Element ID.
            num_points: Number of points along the element to calculate values.
            
        Returns:
            A tuple (x_coords, shear_forces, bending_moments) or None if not applicable.
            x_coords: Relative coordinates along the element (0 to L).
            shear_forces: Shear forces at these points.
            bending_moments: Bending moments at these points.
        """
        if 'forces' not in self.results or eid not in self.results['forces']:
            return None
        
        el = self.elements.get(eid)
        if not el:
            return None
        
        # for a simple truss element (or beam with i=0 acting as truss), shear/moment are zero.
        # for a beam element, these need to be calculated based on end forces and distributed loads (if any).
        # this is a placeholder for full beam sfd/bmd calculation.
        # for now, if it's a beam-like element, we can return zero shear/moment as a basic default
        # or derive from end shears/moments if no distributed loads are considered.

        n1, n2 = el['nodes']
        x1, y1 = self.nodes[n1]
        x2, y2 = self.nodes[n2]
        L = np.hypot(x2-x1, y2-y1)
        
        x_coords = np.linspace(0, L, num_points)
        
        # placeholder: returning zero shear and moment for now
        # a full implementation would use the local end forces [n1, v1, m1, n2, v2, m2]
        # and any distributed loads on the element to calculate shear and moment along its length.
        local_forces = self.results['forces'][eid]
        V1 = local_forces[1]
        M1 = local_forces[2]
        V2 = local_forces[4] # note: v2_local = -v1_local if no distributed load
        M2 = local_forces[5]

        # basic linear interpolation for shear and moment if no distributed loads
        # (this is a simplification; actual diagrams depend on loading)
        # v(x) = v1 - (v1+v2)/l * x  -- this is incorrect for typical sign conventions if v2 is end reaction
        # correct for v(x) = v1 (constant if no transverse load)
        # m(x) = m1 + v1*x (if v1 is shear at start, m1 moment at start)
        
        shear_forces = np.full_like(x_coords, 0.0) # placeholder
        bending_moments = np.full_like(x_coords, 0.0) # placeholder

        # example of simple shear/moment if only end loads (no distributed)
        # this is still a simplification. for bmd/sfd, you often need to consider equilibrium of segments.
        # for now, returning zeros as a safe placeholder that indicates not fully implemented.
        # to properly implement sfd/bmd, we need to consider element loads along its length.
        # for now, we assume that beam elements only have end loads and thus shear is constant and moment is linear.
        # this will be incorrect if there are distributed loads on the element.

        # if you want to show *something* based on end shears and moments:
        shear_forces = np.full_like(x_coords, V1)
        bending_moments = M1 + V1 * x_coords # m(x) = m(start) + integral(v(x)dx)

        # if the element is more like a truss (i is very small), shear/moment should be near zero.
        sec = self.sections[el['sec']]
        if sec['I'] < 1e-9: # threshold for being truss-like
            shear_forces.fill(0.0)
            bending_moments.fill(0.0)
            
        return x_coords, shear_forces, bending_moments