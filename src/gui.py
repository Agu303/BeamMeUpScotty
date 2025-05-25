import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.scrolledtext as scrolledtext
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.patches as patches
from matplotlib.path import Path
from solver import StructuralSolver
from visualizer import StructureVisualizer
import numpy as np
import copy
import json
from matplotlib.backends.backend_pdf import PdfPages # for pdf export

class StructuralGUI(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        master.title('BeamMeUpScotty v2')
        self.pack(fill='both', expand=True)
        self.solver = StructuralSolver()
        self.current_mode = 'node'  # 'node', 'element', or 'delete'
        self.temp_node = None  # for element placement
        self.temp_line = None  # for temporary line visualization
        self.plot_limits = {'xmin': -10, 'xmax': 10, 'ymin': -10, 'ymax': 10}  # initial plot limits
        self.pan_start = None  # for panning functionality
        
        # undo/redo history
        self.history = []
        self.history_index = -1
        self.max_history = 50  # max history states
        
        # units
        self.force_unit = tk.StringVar(value='N')  # 'n' or 'lbf'
        self.distance_unit = tk.StringVar(value='m')  # 'm' or 'ft'
        
        # trace callbacks for unit changes
        self.force_unit.trace_add("write", self._on_force_unit_change)
        self.distance_unit.trace_add("write", self._on_distance_unit_change)
        
        self._initialize_materials()  # initialize common materials
        self._initialize_sections()   # initialize common sections
        self._build_ui()

    def _initialize_materials(self):
        # initialize common materials database
        # format: {id: {'name': name, 'E': young's modulus (gpa), 'density': kg/m³}}
        self.material_database = {
            1: {'name': 'Steel (A36)', 'E': 200, 'density': 7850},
            2: {'name': 'Aluminum 6061', 'E': 69, 'density': 2700},
            3: {'name': 'Balsa Wood', 'E': 3.5, 'density': 160},
            4: {'name': 'G10 Fiberglass', 'E': 17.2, 'density': 1800},
            5: {'name': 'Carbon Fiber', 'E': 230, 'density': 1600},
            6: {'name': 'Titanium', 'E': 116, 'density': 4500},
            7: {'name': 'Copper', 'E': 110, 'density': 8960},
            8: {'name': 'Brass', 'E': 102, 'density': 8500},
            9: {'name': 'PVC', 'E': 3.0, 'density': 1380},
            10: {'name': 'Pine Wood', 'E': 8.5, 'density': 500}
        }
        
        # add materials to solver
        for mid, props in self.material_database.items():
            self.solver.add_material(mid, props['E'] * 1e9)  # convert gpa to pa

    def _initialize_sections(self):
        # initialize common section database
        # format: {id: {'name': name, 'type': type, 'dimensions': {...}}}
        self.section_database = {
            1: {'name': 'Rectangle', 'type': 'rectangle', 'dimensions': {'width': 20, 'height': 10}},
            2: {'name': 'Round', 'type': 'round', 'dimensions': {'diameter': 10}},
            3: {'name': 'I-Beam', 'type': 'ibeam', 'dimensions': {'height': 100, 'width': 50, 'web_thickness': 5, 'flange_thickness': 8}},
            4: {'name': 'Channel', 'type': 'channel', 'dimensions': {'height': 50, 'width': 25, 'web_thickness': 5, 'flange_thickness': 8}},
            5: {'name': 'T-Beam', 'type': 'tbeam', 'dimensions': {'height': 50, 'width': 50, 'web_thickness': 5, 'flange_thickness': 8}}
        }
        
        # add sections to solver
        for sid, props in self.section_database.items():
            A, I = self._calculate_section_properties(props['type'], props['dimensions'])
            self.solver.add_section(sid, A * 1e-6, I * 1e-12)  # convert mm² to m² and mm⁴ to m⁴

    def _calculate_section_properties(self, section_type, dimensions):
        # calculate area and moment of inertia for different section types
        if section_type == 'rectangle':
            w = dimensions['width']
            h = dimensions['height']
            A = w * h
            I = w * h**3 / 12
        elif section_type == 'round':
            d = dimensions['diameter']
            A = np.pi * d**2 / 4
            I = np.pi * d**4 / 64
        elif section_type == 'ibeam':
            h = dimensions['height']
            w = dimensions['width']
            tw = dimensions['web_thickness']
            tf = dimensions['flange_thickness']
            A = w * tf * 2 + (h - 2 * tf) * tw
            I = (w * h**3 - (w - tw) * (h - 2 * tf)**3) / 12
        elif section_type == 'channel':
            h = dimensions['height']
            w = dimensions['width']
            tw = dimensions['web_thickness']
            tf = dimensions['flange_thickness']
            A = h * tw + 2 * w * tf
            I = (tw * h**3 + 2 * w * tf**3) / 12 + 2 * w * tf * (h/2 - tf/2)**2
        elif section_type == 'tbeam':
            h = dimensions['height']
            w = dimensions['width']
            tw = dimensions['web_thickness']
            tf = dimensions['flange_thickness']
            A = w * tf + (h - tf) * tw
            # calculate centroid
            y_bar = (w * tf * tf/2 + (h - tf) * tw * (tf + (h - tf)/2)) / A
            I = (w * tf**3)/12 + w * tf * (y_bar - tf/2)**2 + \
                (tw * (h - tf)**3)/12 + tw * (h - tf) * (tf + (h - tf)/2 - y_bar)**2
        else:
            raise ValueError(f"Unknown section type: {section_type}")
            
        return A, I

    # ---------------- gui layout ----------------------
    def _build_ui(self):
        # create main container frame
        main_frame = ttk.Frame(self)
        main_frame.pack(fill='both', expand=True)
        
        # create left control panel with scrollbar
        control_frame_container = ttk.Frame(main_frame)
        control_frame_container.pack(side='left', fill='y', padx=5, pady=5)
        
        # canvas for scrolling
        control_canvas = tk.Canvas(control_frame_container, width=300)
        control_canvas.pack(side='left', fill='both', expand=True)
        
        # scrollbar for canvas
        control_scrollbar = ttk.Scrollbar(control_frame_container, orient='vertical', command=control_canvas.yview)
        control_scrollbar.pack(side='right', fill='y')
        control_canvas.configure(yscrollcommand=control_scrollbar.set)
        
        # frame for controls inside the canvas
        control_frame = ttk.Frame(control_canvas)
        control_frame_id = control_canvas.create_window((0, 0), window=control_frame, anchor='nw', width=280)
        
        # update scrollregion after control frame changes
        def update_scrollregion(event):
            control_canvas.configure(scrollregion=control_canvas.bbox('all'))
        
        # bind update function to control_frame size changes
        control_frame.bind('<Configure>', update_scrollregion)
        
        # undo/redo buttons
        history_frame = ttk.Frame(control_frame)
        history_frame.pack(fill='x', pady=5)
        
        # frame for undo/redo buttons for equal width
        undo_redo_frame = ttk.Frame(history_frame)
        undo_redo_frame.pack(fill='x')
        
        # configure grid for equal button width
        undo_redo_frame.columnconfigure(0, weight=1)
        undo_redo_frame.columnconfigure(1, weight=1)
        
        # undo button
        self.undo_button = ttk.Button(undo_redo_frame, text="Undo", command=self._undo, state='disabled')
        self.undo_button.grid(row=0, column=0, sticky='ew', padx=2)
        
        # redo button
        self.redo_button = ttk.Button(undo_redo_frame, text="Redo", command=self._redo, state='disabled')
        self.redo_button.grid(row=0, column=1, sticky='ew', padx=2)
        
        # units selection
        units_frame = ttk.LabelFrame(control_frame, text="Units")
        units_frame.pack(fill='x', pady=5)
        
        # force units
        force_frame = ttk.Frame(units_frame)
        force_frame.pack(fill='x', pady=2)
        ttk.Label(force_frame, text="Force:").pack(side='left')
        ttk.Radiobutton(force_frame, text="Newtons (N)", variable=self.force_unit, 
                       value='N').pack(side='left', padx=5)
        ttk.Radiobutton(force_frame, text="Pounds (lbf)", variable=self.force_unit, 
                       value='lbf').pack(side='left', padx=5)
        
        # distance units
        dist_frame = ttk.Frame(units_frame)
        dist_frame.pack(fill='x', pady=2)
        ttk.Label(dist_frame, text="Distance:").pack(side='left')
        ttk.Radiobutton(dist_frame, text="Meters (m)", variable=self.distance_unit, 
                       value='m').pack(side='left', padx=5)
        ttk.Radiobutton(dist_frame, text="Feet (ft)", variable=self.distance_unit, 
                       value='ft').pack(side='left', padx=5)
        
        # mode selection
        mode_frame = ttk.LabelFrame(control_frame, text="Mode")
        mode_frame.pack(fill='x', pady=5)
        
        self.mode_var = tk.StringVar(value='node')
        ttk.Radiobutton(mode_frame, text="Add Node", variable=self.mode_var, 
                       value='node', command=self._update_mode).pack(fill='x', pady=1)
        self.element_radio = ttk.Radiobutton(mode_frame, text="Add Element", variable=self.mode_var,
                       value='element', command=self._update_mode)
        self.delete_node_radio = ttk.Radiobutton(mode_frame, text="Delete Node", 
                       variable=self.mode_var, value='delete', command=self._update_mode)
        
        # remove edit element mode
        # self.edit_element_radio = ttk.Radiobutton(mode_frame, text="Edit Element", variable=self.mode_var,
        #               value='edit_element', command=self._update_mode)
        
        self.element_type_var = tk.StringVar(value='beam') # default to beam
        
        # fine-tune node controls
        finetune_frame = ttk.LabelFrame(control_frame, text="Fine-tune Node")
        finetune_frame.pack(fill='x', pady=5)
        
        # node selection frame
        node_select_frame = ttk.Frame(finetune_frame)
        node_select_frame.pack(fill='x', pady=2)
        ttk.Label(node_select_frame, text="Select Node:").pack(side='left')
        self.finetune_node_var = tk.StringVar()
        self.finetune_node_combobox = ttk.Combobox(node_select_frame, textvariable=self.finetune_node_var)
        self.finetune_node_combobox.pack(side='right', fill='x', expand=True)
        
        # fine-tune button
        ttk.Button(finetune_frame, text="Edit Coordinates", 
                  command=self._show_finetune_dialog).pack(fill='x', pady=2)
        
        # zoom controls
        zoom_frame = ttk.LabelFrame(control_frame, text="View Controls")
        zoom_frame.pack(fill='x', pady=5)
        ttk.Button(zoom_frame, text="Zoom In", command=self._zoom_in).pack(fill='x', pady=1)
        ttk.Button(zoom_frame, text="Zoom Out", command=self._zoom_out).pack(fill='x', pady=1)
        ttk.Button(zoom_frame, text="Reset View", command=self._reset_view).pack(fill='x', pady=1)
        
        # load and bc controls
        load_frame = ttk.LabelFrame(control_frame, text="Loads & BCs")
        load_frame.pack(fill='x', pady=5)
        
        # node load section
        node_load_frame = ttk.LabelFrame(load_frame, text="Node Load")
        node_load_frame.pack(fill='x', pady=2)
        
        self._add_labeled_entry(node_load_frame, 'Load Node', 'ln')
        self._add_labeled_entry(node_load_frame, 'Fx', 'Fx')
        self._add_labeled_entry(node_load_frame, 'Fy', 'Fy')
        self._add_labeled_entry(node_load_frame, 'Moment', 'M')
        ttk.Button(node_load_frame, text='Add/Update Load', command=self._gui_add_load).pack(fill='x', pady=2)
        
        # boundary condition section
        bc_frame = ttk.LabelFrame(load_frame, text="Boundary Conditions")
        bc_frame.pack(fill='x', pady=2)
        
        # node selection and dropdown for bc type
        bc_node_frame = ttk.Frame(bc_frame)
        bc_node_frame.pack(fill='x', pady=2)
        ttk.Label(bc_node_frame, text="BC Node:").pack(side='left')
        self._entry_bn = ttk.Entry(bc_node_frame, width=10)
        self._entry_bn.pack(side='left', padx=5)
        
        # bc type dropdown
        bc_type_frame = ttk.Frame(bc_frame)
        bc_type_frame.pack(fill='x', pady=2)
        ttk.Label(bc_type_frame, text="BC Type:").pack(side='left')
        self.bc_type_var = tk.StringVar(value="fixed")
        self.bc_type_dropdown = ttk.Combobox(bc_type_frame, textvariable=self.bc_type_var, state='readonly')
        self.bc_type_dropdown['values'] = ["Fixed", "Pinned", "Roller-X", "Roller-Y", "Custom"]
        self.bc_type_dropdown.pack(side='right', fill='x', expand=True)
        self.bc_type_dropdown.bind('<<ComboboxSelected>>', self._on_bc_type_selected)
        
        # custom bc options frame (initially hidden)
        self.custom_bc_frame = ttk.Frame(bc_frame)
        # will be packed/unpacked based on selection
        
        # custom bc checkboxes
        self.bc_ux_var = tk.BooleanVar(value=True)
        self.bc_uy_var = tk.BooleanVar(value=True)
        self.bc_theta_var = tk.BooleanVar(value=True)
        
        ttk.Checkbutton(self.custom_bc_frame, text="Constrain X", variable=self.bc_ux_var).pack(fill='x')
        ttk.Checkbutton(self.custom_bc_frame, text="Constrain Y", variable=self.bc_uy_var).pack(fill='x')
        ttk.Checkbutton(self.custom_bc_frame, text="Constrain Rotation", variable=self.bc_theta_var).pack(fill='x')
        
        # add bc button
        ttk.Button(bc_frame, text='Apply Boundary Condition', command=self._gui_apply_bc).pack(fill='x', pady=2)
        
        # add delete bc button
        ttk.Button(bc_frame, text='Delete Boundary Condition', command=self._gui_delete_bc).pack(fill='x', pady=2)
        
        # material and cross-section controls
        mat_frame = ttk.LabelFrame(control_frame, text="Material & Cross-Section")
        mat_frame.pack(fill='x', pady=5)  # always visible now
        
        # element selection
        self.element_select_frame = ttk.Frame(mat_frame)
        self.element_select_frame.pack(fill='x', pady=2)
        ttk.Label(self.element_select_frame, text="Select Element:").pack(side='left')
        self.element_var = tk.StringVar()
        self.element_dropdown = ttk.Combobox(self.element_select_frame, textvariable=self.element_var, state='readonly')
        self.element_dropdown.pack(side='right', fill='x', expand=True)
        self.element_dropdown.bind('<<ComboboxSelected>>', self._on_element_selected)
        
        # material selection
        mat_select_frame = ttk.Frame(mat_frame)
        mat_select_frame.pack(fill='x', pady=2)
        ttk.Label(mat_select_frame, text="Current Material:").pack(side='left')
        self.material_var = tk.StringVar()
        self.material_dropdown = ttk.Combobox(mat_select_frame, textvariable=self.material_var, state='readonly')
        self.material_dropdown.pack(side='right', fill='x', expand=True)
        self.material_dropdown.bind('<<ComboboxSelected>>', self._on_material_selected)
        
        # material properties
        self._add_labeled_entry(mat_frame, 'E (GPa)', 'E')
        
        # cross-section selection
        sec_select_frame = ttk.Frame(mat_frame)
        sec_select_frame.pack(fill='x', pady=2)
        ttk.Label(sec_select_frame, text="Current Cross-Section:").pack(side='left')
        self.section_var = tk.StringVar()
        self.section_dropdown = ttk.Combobox(sec_select_frame, textvariable=self.section_var, state='readonly')
        self.section_dropdown.pack(side='right', fill='x', expand=True)
        self.section_dropdown.bind('<<ComboboxSelected>>', self._on_section_selected)
        
        # buttons for applying properties
        ttk.Button(mat_frame, text='Add New Properties', command=self._gui_add_properties).pack(fill='x', pady=2)
        ttk.Button(mat_frame, text='Apply to Selected Element', command=self._gui_update_element).pack(fill='x', pady=2)
        ttk.Button(mat_frame, text='Apply to All Elements', command=self._gui_update_all_elements).pack(fill='x', pady=2)
        
        # results section
        results_frame = ttk.LabelFrame(control_frame, text="Results")
        results_frame.pack(fill='x', pady=5)
        
        ttk.Button(results_frame, text='Solve', command=self._gui_solve).pack(fill='x', pady=2)
        ttk.Button(results_frame, text='Plot Deformed', command=self._gui_plot_def).pack(fill='x', pady=2)
        ttk.Button(results_frame, text='Identify Zero-Force Members', command=self._gui_identify_zero_force_members).pack(fill='x', pady=2)
        ttk.Button(results_frame, text='Export PDF', command=lambda: self._gui_export('pdf')).pack(fill='x', pady=2)
        
        # delete all button - moved to bottom as danger zone
        danger_frame = ttk.LabelFrame(control_frame, text="Danger Zone")
        danger_frame.pack(fill='x', pady=5)
        
        delete_all_button = ttk.Button(danger_frame, text='Delete All', command=self._delete_all)
        delete_all_button.pack(fill='x', pady=2)
        # apply red styling if possible with ttk (might be limited by theme)
        try:
            delete_all_button.configure(style='Danger.TButton')
        except:
            pass  # fallback to default style if custom style not supported
        
        # add mouse wheel scrolling to the canvas - platform-independent approach
        def _on_mousewheel(event):
            # cross-platform scrolling support
            if event.num == 4 or event.delta > 0:
                control_canvas.yview_scroll(-1, "units")
            elif event.num == 5 or event.delta < 0:
                control_canvas.yview_scroll(1, "units")
            
        # bind different mouse wheel events based on platform
        control_frame.bind_all("<MouseWheel>", _on_mousewheel)  # windows and macos
        control_frame.bind_all("<Button-4>", _on_mousewheel)    # linux - scroll up
        control_frame.bind_all("<Button-5>", _on_mousewheel)    # linux - scroll down
        
        # enter/leave events to prevent scrolling when mouse is not over the control panel
        def _bind_mousewheel(event):
            control_canvas.bind_all("<MouseWheel>", _on_mousewheel)
            control_canvas.bind_all("<Button-4>", _on_mousewheel)
            control_canvas.bind_all("<Button-5>", _on_mousewheel)
            
        def _unbind_mousewheel(event):
            control_canvas.unbind_all("<MouseWheel>")
            control_canvas.unbind_all("<Button-4>")
            control_canvas.unbind_all("<Button-5>")
            
        control_frame.bind("<Enter>", _bind_mousewheel)
        control_frame.bind("<Leave>", _unbind_mousewheel)
        
        # matplotlib area
        self.fig, self.ax = plt.subplots(figsize=(8, 6))
        self.canvas = FigureCanvasTkAgg(self.fig, master=main_frame)
        self.canvas.get_tk_widget().pack(side='right', fill='both', expand=True, padx=5, pady=5)
        
        # connect click event
        self.canvas.mpl_connect('button_press_event', self._on_click)
        self.canvas.mpl_connect('button_release_event', self._on_release)
        self.canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        
        # initialize plot with grid and labels
        self._update_plot()
        self._update_material_section_lists()
        self.zero_force_members = set() # to store ids of zero-force members
        
        # update element dropdown
        self._update_element_list()
        
        # save initial empty state
        self._save_state("Initial State")

    def _update_material_section_lists(self):
        # update the material and section dropdown lists
        # store current selections
        current_material = self.material_var.get()
        current_section = self.section_var.get()
        
        # update material dropdown with just the names
        materials = [props['name'] for props in self.material_database.values()]
        self.material_dropdown['values'] = materials
        
        # update section dropdown with just the names
        sections = [props['name'] for props in self.section_database.values()]
        self.section_dropdown['values'] = sections
        
        # restore selections if they still exist in the new lists
        if current_material in materials:
            self.material_var.set(current_material)
        elif materials:
            self.material_var.set(materials[0])
            
        if current_section in sections:
            self.section_var.set(current_section)
        elif sections:
            self.section_var.set(sections[0])

    def _add_labeled_entry(self, parent, label, key):
        """Add a labeled entry field to the parent widget"""
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=1)
        ttk.Label(frame, text=label).pack(side='left')
        e = ttk.Entry(frame, width=10)
        e.pack(side='right', padx=5)
        setattr(self, f'_entry_{key}', e)

    def _on_material_selected(self, event):
        """Handle material selection from dropdown"""
        selection = self.material_var.get()
        if not selection:
            return
            
        # Find material ID by name and autofill E value
        for mid, props in self.material_database.items():
            if props['name'] == selection:
                # Auto-fill E value
                self._entry_E.delete(0, tk.END)
                self._entry_E.insert(0, str(props['E']))
                break

    def _on_section_selected(self, event):
        """Handle section selection from dropdown"""
        selection = self.section_var.get()
        if not selection:
            return
            
        # Find section ID by name
        for sid, props in self.section_database.items():
            if props['name'] == selection:
                break

    def _gui_add_properties(self):
        """Add both material and cross-section properties"""
        # First add material
        E = self._safe_float(self._entry_E)
        
        if E <= 0:
            messagebox.showerror('Error', 'Please enter a positive Young\'s modulus')
            return
        
        # Next, get cross-section type
        section_type = self._show_section_type_dialog()
        if not section_type:
            return
            
        # Get dimension input
        dimensions = self._show_section_dimensions_dialog(section_type)
        if not dimensions:
            return
            
        try:
            # Add material
            mid = max(self.solver.materials.keys()) + 1 if self.solver.materials else 1
            material_name = f"Material {len(self.material_database) + 1}"
            
            # Add to material database
            self.material_database[mid] = {
                'name': material_name,
                'E': E,
                'density': 0  # Default density
            }
            
            # Add material to solver
            self.solver.add_material(mid, E * 1e9)  # Convert GPa to Pa
            
            # Add section
            sid = max(self.solver.sections.keys()) + 1 if self.solver.sections else 1
            section_name = f"Section {len(self.section_database) + 1}"
            
            # Calculate properties
            A, I = self._calculate_section_properties(section_type, dimensions)
            
            # Add to section database
            self.section_database[sid] = {
                'name': section_name,
                'type': section_type,
                'dimensions': dimensions
            }
            
            # Add section to solver
            self.solver.add_section(sid, A * 1e-6, I * 1e-12)  # Convert mm² to m² and mm⁴ to m⁴
            
            # Update dropdowns
            self._update_material_section_lists()
            
            # Select the newly added material and section
            self.material_var.set(material_name)
            self.section_var.set(section_name)
            
            messagebox.showinfo('Success', f'Added {material_name} and {section_name}')
            
            # Clear input fields
            self._entry_E.delete(0, tk.END)
            
        except Exception as e:
            messagebox.showerror('Error', str(e))

    def _update_mode(self):
        self.current_mode = self.mode_var.get()
        
        # Update element mode visibility based on node count
        if len(self.solver.nodes) >= 2:
            self.element_radio.pack(fill='x', pady=1)
            self.delete_node_radio.pack(fill='x', pady=1)
        else:
            self.element_radio.pack_forget()
            self.delete_node_radio.pack_forget()
            if self.current_mode in ['element', 'delete']:
                self.mode_var.set('node')
                self.current_mode = 'node'
                messagebox.showinfo('Info', 'At least two nodes are required to create elements.')
            
        self.temp_node = None
        if self.temp_line:
            self.temp_line.remove()
            self.temp_line = None
            # Add this line to redraw the canvas after removing the temp_line
            self.canvas.draw() 
            
        self._update_delete_node_visibility()
        self._update_plot()
        
        # Always update the element list and node list
        self._update_element_list()
        self._update_node_list()
        
    def _update_node_list(self):
        """Update the node selection dropdown in the fine-tune panel"""
        if not self.solver.nodes:
            self.finetune_node_combobox['values'] = []
            self.finetune_node_var.set('')
            return
            
        # Create list of node entries
        nodes = []
        for nid, (x, y) in self.solver.nodes.items():
            unit = self.distance_unit.get()
            nodes.append(f"Node {nid}: ({x:.2f}, {y:.2f}) {unit}")
            
        self.finetune_node_combobox['values'] = nodes
        
        # Select the first node or keep current selection if valid
        current_selection = self.finetune_node_var.get()
        if current_selection and current_selection in nodes:
            pass  # Keep current selection
        elif nodes:
            self.finetune_node_var.set(nodes[0])
            
    def _show_finetune_dialog(self):
        """Open the coordinate fine-tuning dialog for the selected node"""
        if not self.solver.nodes:
            messagebox.showinfo('Info', 'No nodes to edit.')
            return
            
        selection = self.finetune_node_var.get()
        if not selection:
            messagebox.showinfo('Info', 'Please select a node to edit.')
            return
            
        # Extract node ID from selection string (e.g., "Node 1: (0.00, 0.00) m")
        try:
            node_id = int(selection.split(':')[0].replace('Node', '').strip())
        except (ValueError, IndexError):
            messagebox.showerror('Error', 'Invalid node selection.')
            return
            
        if node_id not in self.solver.nodes:
            messagebox.showerror('Error', f'Node {node_id} not found.')
            return
            
        # Get current coordinates
        original_x, original_y = self.solver.nodes[node_id]
        initial_coords = (original_x, original_y)
        
        # Show dialog
        final_coords = self._show_coordinate_dialog(initial_coords, node_id)
        
        if final_coords:  # User didn't cancel
            new_x, new_y = final_coords
            
            # Check if the node is part of any element
            connected_elements = []
            for eid, el in self.solver.elements.items():
                if node_id in el['nodes']:
                    connected_elements.append(eid)
            
            # If the node is connected to elements, check for intersections
            if connected_elements:
                # Store original position
                original_position = self.solver.nodes[node_id].copy()
                
                # Temporarily update node position to check intersections
                self.solver.nodes[node_id] = np.array([new_x, new_y], dtype=float)
                
                # Find all possible intersections with this node's movement
                intersections_found = False
                
                # Check each element connected to this node
                for eid in connected_elements:
                    element_nodes = self.solver.elements[eid]['nodes']
                    # Get the other node in this element
                    other_node_id = element_nodes[0] if element_nodes[1] == node_id else element_nodes[1]
                    other_x, other_y = self.solver.nodes[other_node_id]
                    
                    # Check for intersections with all other elements
                    for other_eid, other_el in self.solver.elements.items():
                        # Skip if it's the same element or another connected element
                        if other_eid in connected_elements:
                            continue
                            
                        n1, n2 = other_el['nodes']
                        x1, y1 = self.solver.nodes[n1]
                        x2, y2 = self.solver.nodes[n2]
                        
                        # Check for intersection
                        intersection = self._check_line_intersection(
                            new_x, new_y, other_x, other_y,
                            x1, y1, x2, y2
                        )
                        
                        if intersection:
                            intersections_found = True
                            ix, iy = intersection
                            
                            # Check if a node already exists at this intersection
                            existing_node = None
                            for nid, (nx, ny) in self.solver.nodes.items():
                                if ((nx - ix) ** 2 + (ny - iy) ** 2) ** 0.5 < 0.1:  # 0.1 unit threshold
                                    existing_node = nid
                                    break
                            
                            if existing_node is None:
                                # Create a new node at intersection
                                new_node_id = len(self.solver.nodes) + 1
                                self.solver.add_node(new_node_id, ix, iy)
                                
                                # Split the intersected element
                                self._split_element_at_node(other_eid, new_node_id)
                
                # Reset node position temporarily
                self.solver.nodes[node_id] = original_position
                
                # If intersections were found, ask user if they want to proceed
                if intersections_found:
                    proceed = messagebox.askyesno('Warning', 
                        'Moving this node will create intersections with existing elements. New nodes will be created at these intersections. Proceed?')
                    if not proceed:
                        return
            
            # Save the current state before making changes
            self._save_state(f"Before Edit Node {node_id}")
            
            # Update node coordinates
            self.solver.nodes[node_id] = np.array([new_x, new_y], dtype=float)
            
            # Explicitly verify element connections
            # This ensures both node references and element data structures remain consistent
            for eid, el in list(self.solver.elements.items()):
                nodes = el['nodes']
                # Verify that both nodes in this element exist
                if nodes[0] not in self.solver.nodes or nodes[1] not in self.solver.nodes:
                    # This should never happen but handle it just in case
                    print(f"Warning: Element {eid} references missing node(s). Auto-fixing.")
                    # Remove the broken element
                    del self.solver.elements[eid]
                elif node_id in nodes:
                    # Verify this element is correctly connected to the edited node
                    # No action needed as elements store node IDs, not coordinates
                    pass
            
            # Re-perform intersection checks and create the necessary nodes/elements
            if connected_elements:
                for eid in connected_elements:
                    element_nodes = self.solver.elements[eid]['nodes']
                    # Get the other node in this element
                    other_node_id = element_nodes[0] if element_nodes[1] == node_id else element_nodes[1]
                    other_x, other_y = self.solver.nodes[other_node_id]
                    
                    # Check for intersections with all other elements
                    for other_eid, other_el in self.solver.elements.items():
                        # Skip if it's the same element or another connected element
                        if other_eid in connected_elements:
                            continue
                            
                        n1, n2 = other_el['nodes']
                        x1, y1 = self.solver.nodes[n1]
                        x2, y2 = self.solver.nodes[n2]
                        
                        # Check for intersection
                        intersection = self._check_line_intersection(
                            new_x, new_y, other_x, other_y,
                            x1, y1, x2, y2
                        )
                        
                        if intersection:
                            ix, iy = intersection
                            
                            # Check if a node already exists at this intersection
                            existing_node = None
                            for nid, (nx, ny) in self.solver.nodes.items():
                                if ((nx - ix) ** 2 + (ny - iy) ** 2) ** 0.5 < 0.1:  # 0.1 unit threshold
                                    existing_node = nid
                                    break
                            
                            if existing_node is None:
                                # Create a new node at intersection
                                new_node_id = len(self.solver.nodes) + 1
                                self.solver.add_node(new_node_id, ix, iy)
                                
                                # Split the intersected element
                                self._split_element_at_node(other_eid, new_node_id)
            
            # Update UI
            self._update_plot()
            self._update_node_list()
            self._update_element_list()
            self._update_mode()  # Ensure all modes are properly accessible
            
            # Save the new state
            self._save_state(f"Edit Node {node_id}")

    def _update_element_list(self):
        """Update the element dropdown list"""
        if not self.solver.elements:
            self.element_dropdown['values'] = []
            return
            
        # Create list of element descriptions
        elements = []
        for eid, el in self.solver.elements.items():
            n1, n2 = el['nodes']
            mat_name = self.material_database[el['mat']]['name']
            sec_name = self.section_database[el['sec']]['name']
            elements.append(f"Element {eid}: {n1}-{n2} ({mat_name}, {sec_name})")
            
        self.element_dropdown['values'] = elements
        if elements:
            self.element_dropdown.set(elements[0])
            # No need to call _on_element_selected here as it might trigger unwanted dialogs

    def _on_element_selected(self, event):
        """Handle element selection from dropdown"""
        selection = self.element_var.get()
        if not selection:
            return
            
        eid = int(selection.split(':')[0].split()[1])
        
        # Load the element's current properties into the UI
        self._load_element_properties_to_ui(eid)
        
        # Update plot to highlight selected element
        self._update_plot()

    def _load_element_properties_to_ui(self, eid, new_section_id_override=None):
        """Helper to load element's properties into the UI controls."""
        el_props = self.solver.elements[eid]
        
        # Material
        mat_id = el_props['mat']
        mat_name = self.material_database[mat_id]['name']
        mat_E = self.material_database[mat_id]['E']
        self.material_var.set(mat_name)
        self._entry_E.delete(0, tk.END)
        self._entry_E.insert(0, str(mat_E))
        
        # Section
        sec_id_to_load = new_section_id_override if new_section_id_override is not None else el_props['sec']
        # Ensure the sec_id_to_load is valid before accessing section_database
        if sec_id_to_load in self.section_database:
            sec_name = self.section_database[sec_id_to_load]['name']
            self.section_var.set(sec_name)
        else: # Fallback or error handling if section ID is somehow invalid
            self.section_var.set("") # Clear or set to a default
            print(f"Warning: Section ID {sec_id_to_load} not found in database for element {eid}")

    def _update_delete_node_visibility(self):
        """Update visibility of delete node option based on node existence"""
        if self.solver.nodes:
            self.delete_node_radio.pack(fill='x', pady=1)
        else:
            self.delete_node_radio.pack_forget()
            # Force switch to node mode if no nodes exist
            self.mode_var.set('node')
            self.current_mode = 'node'

    def _renumber_nodes(self):
        """Renumber nodes sequentially starting from 1"""
        if not self.solver.nodes:
            self._update_node_list() # Ensure UI is cleared if no nodes
            return

        # Current nodes are those remaining after any deletion.
        # Their IDs might be sparse. We want to make them sequential 1...N.
        
        # Create a mapping from old (current) node IDs to new sequential node IDs.
        # Sorting by old ID ensures some determinism.
        remaining_old_node_ids = sorted(self.solver.nodes.keys())
        
        old_to_new_id_map = {old_id: new_id for new_id, old_id in enumerate(remaining_old_node_ids, 1)}
        
        # Create the new nodes dictionary with new sequential IDs.
        new_nodes_dict_seq_id = {}
        for old_id, new_id in old_to_new_id_map.items():
            new_nodes_dict_seq_id[new_id] = self.solver.nodes[old_id] # Get coords from old dict
            
        # Update element node references using the map.
        # Elements in self.solver.elements are the ones remaining.
        for eid, el_props in list(self.solver.elements.items()): # Iterate over a copy in case of modification
            old_n1, old_n2 = el_props['nodes']
            
            valid_element = True
            if old_n1 in old_to_new_id_map:
                el_props['nodes'][0] = old_to_new_id_map[old_n1]
            else:
                # This implies an inconsistency: a remaining element refers to a non-remaining node.
                # This should ideally not happen if connected elements to a deleted node were properly removed.
                print(f"Warning: Element {eid} node {old_n1} not found in map during renumbering. Removing element.")
                # Potentially remove the element if it's now invalid
                # del self.solver.elements[eid] # Be cautious with modifying during iteration or handle separately
                valid_element = False


            if old_n2 in old_to_new_id_map:
                el_props['nodes'][1] = old_to_new_id_map[old_n2]
            else:
                print(f"Warning: Element {eid} node {old_n2} not found in map during renumbering. Removing element.")
                valid_element = False

            if not valid_element and eid in self.solver.elements:
                 # If an element became invalid because its nodes are gone (should have been caught earlier)
                 # This is a safeguard.
                 del self.solver.elements[eid]


        # Update loads using the map
        new_loads_dict_seq_id = {}
        for old_nid, load_props in self.solver.loads.items():
            if old_nid in old_to_new_id_map:
                new_loads_dict_seq_id[old_to_new_id_map[old_nid]] = load_props
        self.solver.loads = new_loads_dict_seq_id

        # Update boundary conditions using the map
        new_bcs_dict_seq_id = {}
        for old_nid, bc_props in self.solver.boundary_conditions.items():
            if old_nid in old_to_new_id_map:
                new_bcs_dict_seq_id[old_to_new_id_map[old_nid]] = bc_props
        self.solver.boundary_conditions = new_bcs_dict_seq_id

        # Replace old nodes dictionary with the new one
        self.solver.nodes = new_nodes_dict_seq_id
        
        # Update the UI node list to reflect renumbering
        self._update_node_list()

    def _renumber_elements(self):
        """Renumber elements sequentially starting from 1"""
        if not self.solver.elements:
            return

        # Create new elements dictionary with sequential numbering
        new_elements = {}
        for i, (old_eid, el_props) in enumerate(sorted(self.solver.elements.items()), 1):
            # Copy all properties to maintain material, section, type, etc.
            new_elements[i] = el_props.copy()

        # Update result forces if they exist
        if 'forces' in self.solver.results:
            new_forces = {}
            for i, (old_eid, _) in enumerate(sorted(self.solver.elements.items()), 1):
                if old_eid in self.solver.results['forces']:
                    new_forces[i] = self.solver.results['forces'][old_eid]
            self.solver.results['forces'] = new_forces

        # Replace old elements with new ones
        self.solver.elements = new_elements
        
        # Update element list in the UI
        self._update_element_list()

    def _screen_to_data_coords(self, x, y):
        """Convert screen coordinates to data coordinates"""
        return self.ax.transData.inverted().transform((x, y))

    def _data_to_screen_coords(self, x, y):
        """Convert data coordinates to screen coordinates"""
        return self.ax.transData.transform((x, y))

    def _check_line_intersection(self, x1, y1, x2, y2, x3, y3, x4, y4):
        """Check if two line segments intersect and return intersection point if they do"""
        def ccw(A, B, C):
            return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])
            
        def intersect(A, B, C, D):
            return ccw(A,C,D) != ccw(B,C,D) and ccw(A,B,C) != ccw(A,B,D)
            
        A = (x1, y1)
        B = (x2, y2)
        C = (x3, y3)
        D = (x4, y4)
        
        if not intersect(A, B, C, D):
            return None
            
        # Calculate intersection point
        denominator = ((x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4))
        if abs(denominator) < 1e-10:  # Lines are parallel or coincident
            return None
            
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denominator
        if 0 <= t <= 1:  # Intersection is within first line segment
            u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denominator
            if 0 <= u <= 1:  # Intersection is within second line segment
                x = x1 + t * (x2 - x1)
                y = y1 + t * (y2 - y1)
                return (x, y)
        return None

    def _find_intersections(self, new_element_nodes):
        """Find intersections between the new element and existing elements"""
        intersections = []
        n1, n2 = new_element_nodes
        x1, y1 = self.solver.nodes[n1]
        x2, y2 = self.solver.nodes[n2]
        
        for eid, el in self.solver.elements.items():
            n3, n4 = el['nodes']
            x3, y3 = self.solver.nodes[n3]
            x4, y4 = self.solver.nodes[n4]
            
            # Skip if elements share a node
            if n1 in (n3, n4) or n2 in (n3, n4):
                continue
                
            intersection = self._check_line_intersection(x1, y1, x2, y2, x3, y3, x4, y4)
            if intersection:
                intersections.append(intersection)
                
        return intersections

    def _create_node_at_intersection(self, x, y):
        """Create a new node at the intersection point"""
        # Check if a node already exists very close to this point
        for nid, (nx, ny) in self.solver.nodes.items():
            if ((nx - x) ** 2 + (ny - y) ** 2) ** 0.5 < 0.1:  # 0.1 unit threshold
                return nid
                
        # Create new node
        nid = len(self.solver.nodes) + 1
        self.solver.add_node(nid, x, y)
        return nid

    def _split_element_at_node(self, eid, node_id):
        """Split an element into two elements at the given node"""
        if eid not in self.solver.elements:
            return  # Element may have been deleted already
            
        el = self.solver.elements[eid]
        n1, n2 = el['nodes']
        
        # Skip if the node is already one of the element's endpoints
        if node_id in (n1, n2):
            return
            
        # Create two new elements
        eid1 = max(self.solver.elements.keys()) + 1 if self.solver.elements else 1
        eid2 = eid1 + 1
        
        # Add new elements with the same properties as the original
        self.solver.add_element(eid1, n1, node_id, el['type'], el['mat'], el['sec'])
        self.solver.add_element(eid2, node_id, n2, el['type'], el['mat'], el['sec'])
        
        # Copy the 'edited' flag if present
        if 'edited' in el:
            self.solver.elements[eid1]['edited'] = el['edited']
            self.solver.elements[eid2]['edited'] = el['edited']
        
        # Remove original element
        del self.solver.elements[eid]
        
        # Renumber elements to ensure chronological order
        self._renumber_elements()

    def _on_click(self, event):
        if event.inaxes != self.ax:
            return
            
        x, y = event.xdata, event.ydata
        
        # Check if click is within plot limits
        if not (self.plot_limits['xmin'] <= x <= self.plot_limits['xmax'] and 
                self.plot_limits['ymin'] <= y <= self.plot_limits['ymax']):
            return
        
        # If no nodes exist, force node mode
        if not self.solver.nodes and self.current_mode != 'node':
            self.mode_var.set('node')
            self.current_mode = 'node'
            self._update_mode()
        
        # Handle right click for panning
        if event.button == 3:  # Right click
            self.pan_start = (event.x, event.y)  # Store screen coordinates
            return
            
        # Handle middle click for escape
        if event.button == 2:  # Middle click
            if self.current_mode == 'element' and self.temp_node is not None:
                self.temp_node = None
                if self.temp_line:
                    self.temp_line.remove()
                    self.temp_line = None
                self.canvas.draw()
            return
            
        # Only process left click for other operations
        if event.button != 1:  # Not left click
            return
        
        # Get click coordinates
        click_x, click_y = event.xdata, event.ydata

        # If mode switched while drawing an element, cancel drawing.
        if self.current_mode != 'element' and self.temp_node is not None:
            self.temp_node = None
            if self.temp_line:
                self.temp_line.remove()
                self.temp_line = None
            self.canvas.draw()
            # It's important to return here to prevent the click from being processed by the new mode
            # if this click was the one that *completed* the element in the user's mind.
            messagebox.showinfo("Info", "Element creation cancelled due to mode switch.")
            return

        if self.current_mode == 'node':
            # Add new node
            try:
                new_node_id = len(self.solver.nodes) + 1 # Simpler node ID generation
                
                # --- Snapping Logic for Add Node ---
                # Determine a reasonable snap threshold (e.g., 5% of the smaller view dimension, converted to data units)
                # This is a heuristic. A fixed data unit threshold might be better.
                # For now, let's use a fixed data unit threshold, similar to _find_closest_node
                snap_threshold = 0.1 # Same as _find_closest_node threshold
                
                snapped_element_id, snapped_coords = self._find_closest_element_and_snap_point(
                    click_x, click_y, snap_threshold
                )
                
                node_x_to_add, node_y_to_add = click_x, click_y
                action_description_prefix = f"Add Node {new_node_id}"

                if snapped_element_id is not None:
                    node_x_to_add, node_y_to_add = snapped_coords
                    # Check if the snapped point is very close to an existing endpoint of the snapped element
                    el_props_snap = self.solver.elements[snapped_element_id]
                    n1_snap, n2_snap = el_props_snap['nodes']
                    x1_snap, y1_snap = self.solver.nodes[n1_snap]
                    x2_snap, y2_snap = self.solver.nodes[n2_snap]
                    
                    dist_to_n1_snap_sq = (node_x_to_add - x1_snap)**2 + (node_y_to_add - y1_snap)**2
                    dist_to_n2_snap_sq = (node_x_to_add - x2_snap)**2 + (node_y_to_add - y2_snap)**2
                    
                    epsilon_sq = (1e-5)**2 # Tolerance for being "at" an endpoint

                    is_at_endpoint = False
                    if dist_to_n1_snap_sq < epsilon_sq:
                        # Snapped very close to n1 of the element, treat as clicking n1
                        # No new node needed if we just select n1
                        # For "Add Node" mode, this means we don't create a duplicate.
                        # We could instead highlight node n1 or disallow adding node here.
                        # For now, let's proceed to add, but it might merge if coordinates are identical.
                        # Or, better, if snapping to an existing node's location, don't add.
                        existing_node_at_snap = self._find_closest_node(node_x_to_add, node_y_to_add, threshold=1e-4)
                        if existing_node_at_snap:
                             messagebox.showinfo("Info", f"A node ({existing_node_at_snap}) already exists at this location.")
                             return
                        is_at_endpoint = True
                    elif dist_to_n2_snap_sq < epsilon_sq:
                        existing_node_at_snap = self._find_closest_node(node_x_to_add, node_y_to_add, threshold=1e-4)
                        if existing_node_at_snap:
                             messagebox.showinfo("Info", f"A node ({existing_node_at_snap}) already exists at this location.")
                             return
                        is_at_endpoint = True
                    
                    if not is_at_endpoint:
                         action_description_prefix = f"Add Node {new_node_id} (snapped to E{snapped_element_id})"
                    else: # Snapped to an endpoint, don't split, just add if space is free
                        snapped_element_id = None # Clear this so it doesn't try to split

                # Check again if a node already exists at the final (possibly snapped) coordinates
                # This handles cases where snapping moves the click to an existing node location.
                existing_node_at_final_pos = self._find_closest_node(node_x_to_add, node_y_to_add, threshold=1e-4)
                if existing_node_at_final_pos is not None:
                    messagebox.showinfo("Info", f"Node {existing_node_at_final_pos} already exists at or very near this location.")
                    return

                self.solver.add_node(new_node_id, node_x_to_add, node_y_to_add)
                
                # Element splitting logic (either due to snapping or direct placement on line)
                element_to_split_after_add = None
                if snapped_element_id: # Node was snapped to this element and isn't an endpoint
                    element_to_split_after_add = snapped_element_id
                else: # Node was not snapped, check if it was manually placed on an element
                    for eid_check, el_props_check in list(self.solver.elements.items()):
                        n1_chk, n2_chk = el_props_check['nodes']
                        if n1_chk not in self.solver.nodes or n2_chk not in self.solver.nodes: continue
                        x1_c, y1_c = self.solver.nodes[n1_chk]
                        x2_c, y2_c = self.solver.nodes[n2_chk]
                        
                        # Use a slightly more tolerant epsilon for _is_point_on_line_segment
                        if self._is_point_on_line_segment(node_x_to_add, node_y_to_add, x1_c, y1_c, x2_c, y2_c, epsilon=1e-5) and \
                           new_node_id not in [n1_chk, n2_chk]:
                            # Ensure it's not effectively at an endpoint of this segment either
                            dist_to_n1_chk_sq = (node_x_to_add - x1_c)**2 + (node_y_to_add - y1_c)**2
                            dist_to_n2_chk_sq = (node_x_to_add - x2_c)**2 + (node_y_to_add - y2_c)**2
                            if dist_to_n1_chk_sq > epsilon_sq and dist_to_n2_chk_sq > epsilon_sq:
                                element_to_split_after_add = eid_check
                                break
                
                action_description = action_description_prefix
                if element_to_split_after_add is not None:
                    self._split_element_at_node(element_to_split_after_add, new_node_id)
                    action_description += f" and Split Element {element_to_split_after_add}"
                
                self._update_mode()
                self._update_plot()
                self._update_node_list()
                self._update_element_list()
                self._save_state(action_description)
            except Exception as e:
                messagebox.showerror('Error', str(e))
                import traceback
                traceback.print_exc() # For debugging
                
        elif self.current_mode == 'element':
            if self.temp_node is None: # First click for element
                closest_node_start = self._find_closest_node(click_x, click_y)
                if closest_node_start is None: 
                    messagebox.showinfo('Info', 'Elements must start from an existing node. Please click near a node to start an element.')
                    return 
                else:
                    self.temp_node = closest_node_start
                
                x1_coord, y1_coord = self.solver.nodes[self.temp_node]
                self.temp_line, = self.ax.plot([x1_coord, x1_coord], [y1_coord, y1_coord], 'r--', lw=2)
                self.canvas.draw()
            else: # Second click for element
                node_for_end_of_element = None
                element_to_split_for_end_node = None 
                created_node_for_end = None # ID of a new node if one is made for the endpoint

                # Priority 1: Is the click near an existing node?
                closest_existing_node = self._find_closest_node(click_x, click_y)
                if closest_existing_node is not None:
                    node_for_end_of_element = closest_existing_node
                else:
                    # Priority 2: Is the click on an existing element (to split it)?
                    # Use a snap threshold for determining "on element"
                    snap_threshold_element = 0.05 # Adjust as needed, data units
                    snapped_eid, snapped_coords_on_el = self._find_closest_element_and_snap_point(
                        click_x, click_y, snap_threshold_element
                    )

                    if snapped_eid is not None:
                        # Ensure snapped point is not too close to endpoints of the snapped_eid
                        el_props_snap = self.solver.elements[snapped_eid]
                        n1_s, n2_s = el_props_snap['nodes']
                        x1_s, y1_s = self.solver.nodes[n1_s]
                        x2_s, y2_s = self.solver.nodes[n2_s]
                        
                        # Using a small epsilon for checking if "at" an endpoint
                        epsilon_endpoint_sq = (1e-5)**2 
                        dist_to_n1_s_sq = (snapped_coords_on_el[0] - x1_s)**2 + (snapped_coords_on_el[1] - y1_s)**2
                        dist_to_n2_s_sq = (snapped_coords_on_el[0] - x2_s)**2 + (snapped_coords_on_el[1] - y2_s)**2

                        if dist_to_n1_s_sq > epsilon_endpoint_sq and dist_to_n2_s_sq > epsilon_endpoint_sq:
                            # Create a new node at the snapped coordinates on the element
                            new_nid_on_element = len(self.solver.nodes) + 1
                            self.solver.add_node(new_nid_on_element, snapped_coords_on_el[0], snapped_coords_on_el[1])
                            self._save_state(f"Add Node {new_nid_on_element} on E{snapped_eid}") # Save intermediate
                            
                            self._split_element_at_node(snapped_eid, new_nid_on_element) # This will renumber elements
                            self._save_state(f"Split E{snapped_eid} for new element end") # Save intermediate

                            node_for_end_of_element = new_nid_on_element
                            element_to_split_for_end_node = snapped_eid # Store original ID for context if needed
                            created_node_for_end = new_nid_on_element
                            self._update_node_list()
                        else: # Snapped too close to an existing endpoint of an element
                              # Try to find that endpoint node directly
                            node_for_end_of_element = self._find_closest_node(snapped_coords_on_el[0], snapped_coords_on_el[1])
                            if node_for_end_of_element is None: # Should not happen if logic is correct
                                # Fallback: create new node in empty space - REMOVED THIS FALLBACK
                                messagebox.showinfo("Info", "Element end point must be on an existing node or element. Click cancelled.")
                                self.temp_node = None
                                if self.temp_line: self.temp_line.remove(); self.temp_line = None
                                self.canvas.draw()
                                return

                    else:
                        # Priority 3: Click in empty space - NOW DISALLOWED
                        # new_nid_empty = len(self.solver.nodes) + 1
                        # self.solver.add_node(new_nid_empty, click_x, click_y)
                        # self._save_state(f"Add Node {new_nid_empty} (for element end)")
                        # node_for_end_of_element = new_nid_empty
                        # created_node_for_end = new_nid_empty
                        # self._update_node_list()
                        messagebox.showinfo("Info", "Element end point must be on an existing node or element. Click cancelled.")
                        self.temp_node = None
                        if self.temp_line: self.temp_line.remove(); self.temp_line = None
                        self.canvas.draw()
                        return

                if self.temp_node == node_for_end_of_element: # Clicked same node twice
                    messagebox.showwarning('Warning', 'Cannot create an element with zero length (clicked the same node).')
                    if created_node_for_end and created_node_for_end not in self.solver.elements: # Clean up node if it was just made and not used
                        # This check is tricky because the node might be part of a split element now.
                        # A safer approach might be to rely on undo or manual delete.
                        # For now, let's assume such nodes might be wanted or will be handled by undo.
                        pass
                    self.temp_node = None 
                    if self.temp_line: self.temp_line.remove(); self.temp_line = None
                    self.canvas.draw()
                    return
                
                element_exists = any(set(el['nodes']) == {self.temp_node, node_for_end_of_element} for el in self.solver.elements.values())
                if element_exists:
                    messagebox.showwarning('Warning', 'An element already exists between these nodes.')
                    self.temp_node = None 
                    if self.temp_line: self.temp_line.remove(); self.temp_line = None
                    self.canvas.draw()
                    return

                mat_name = self.material_var.get()
                sec_name = self.section_var.get()
                if not mat_name or not sec_name:
                    messagebox.showwarning('Warning', 'Please select/add material and section from the \'Material & Cross-Section\' panel before creating elements.')
                    self.temp_node = None 
                    if self.temp_line: self.temp_line.remove(); self.temp_line = None
                    self.canvas.draw()
                    return

                mat_id = next((mid for mid, props in self.material_database.items() if props['name'] == mat_name), None)
                sec_id = next((sid for sid, props in self.section_database.items() if props['name'] == sec_name), None)

                if mat_id is None or sec_id is None:
                    messagebox.showwarning('Warning', 'Selected material or section not found. Please ensure they are added to the database via \'Add Properties\'.')
                    self.temp_node = None 
                    if self.temp_line: self.temp_line.remove(); self.temp_line = None
                    self.canvas.draw()
                    return
                
                effective_etype = 'beam' 
                
                if effective_etype == 'beam': 
                    sec_props = self.solver.sections[sec_id]
                    if sec_props['A'] == 0 : # Check Area instead of I for basic validity
                        messagebox.showwarning('Warning', 'Elements require non-zero Area (A). Please select/define a section with A > 0.')
                        self.temp_node = None 
                        if self.temp_line: self.temp_line.remove(); self.temp_line = None
                        self.canvas.draw()
                        return
                    # For trusses, user should set I=0. For beams, I>0.
                    # If I=0 for a beam element, it acts like a truss link.
                    # This is now user's responsibility via section definition.

                try:
                    # --- Intersection logic for the new element segment ---
                    # The primary segment is from self.temp_node to node_for_end_of_element
                    
                    intersections_on_new_segment = [] # Stores (node_id, x, y) of intersections
                    elements_to_split_due_to_new_segment = {} # eid_to_split -> new_intersection_node_id
                    
                    x1_current_el, y1_current_el = self.solver.nodes[self.temp_node]
                    x2_current_el, y2_current_el = self.solver.nodes[node_for_end_of_element]

                    for eid_other, el_other_props in list(self.solver.elements.items()):
                        # Skip if this 'other' element was the one just split to create node_for_end_of_element
                        if element_to_split_for_end_node == eid_other and created_node_for_end is not None:
                            # More accurately, skip if node_for_end_of_element is one of its nodes
                            if node_for_end_of_element in el_other_props['nodes']:
                                continue

                        # Skip if the 'other' element shares an endpoint with the current element being drawn
                        if self.temp_node in el_other_props['nodes'] or node_for_end_of_element in el_other_props['nodes']:
                            continue
                        
                        n1_other, n2_other = el_other_props['nodes']
                        if n1_other not in self.solver.nodes or n2_other not in self.solver.nodes: continue
                        x1_o, y1_o = self.solver.nodes[n1_other]
                        x2_o, y2_o = self.solver.nodes[n2_other]
                        
                        intersection_pt = self._check_line_intersection(
                            x1_current_el, y1_current_el, x2_current_el, y2_current_el,
                            x1_o, y1_o, x2_o, y2_o
                        )
                        
                        if intersection_pt:
                            ix, iy = intersection_pt
                            # Ensure intersection is not at an endpoint of the *other* element
                            # (to avoid re-splitting at an existing node if lines meet at a vertex)
                            # And ensure it's not at an endpoint of the *current* segment
                            dist_to_n1_other_sq = (ix - x1_o)**2 + (iy - y1_o)**2
                            dist_to_n2_other_sq = (ix - x2_o)**2 + (iy - y2_o)**2
                            dist_to_temp_node_sq = (ix - x1_current_el)**2 + (iy - y1_current_el)**2
                            dist_to_end_node_sq = (ix - x2_current_el)**2 + (iy - y2_current_el)**2
                            epsilon_sq = (1e-5)**2

                            if (dist_to_n1_other_sq > epsilon_sq and dist_to_n2_other_sq > epsilon_sq and
                                dist_to_temp_node_sq > epsilon_sq and dist_to_end_node_sq > epsilon_sq):
                                
                                # Create a new node at this intermediate intersection
                                new_intermediate_nid = self._create_node_at_intersection(ix, iy)
                                if new_intermediate_nid not in [item[0] for item in intersections_on_new_segment]: # Avoid duplicates
                                     intersections_on_new_segment.append((new_intermediate_nid, ix, iy))
                                elements_to_split_due_to_new_segment[eid_other] = new_intermediate_nid
                    
                    # Split the necessary *other* elements
                    for eid_to_split, at_node_id in elements_to_split_due_to_new_segment.items():
                        if eid_to_split in self.solver.elements: # Check if still exists (might have been renumbered)
                             self._split_element_at_node(eid_to_split, at_node_id)
                    
                    if intersections_on_new_segment:
                        self._update_node_list() # Nodes might have been added
                        # Re-fetch coordinates for sorting as node IDs might have changed
                        # or new nodes might have slightly different coords if _create_node_at_intersection merged.
                        # We need to sort these intersection_nodes by their distance from self.temp_node
                        
                        # Refresh intersection coordinates from solver if nodes were merged by _create_node_at_intersection
                        refreshed_intersections = []
                        for nid_int, _, _ in intersections_on_new_segment:
                            if nid_int in self.solver.nodes:
                                refreshed_intersections.append((nid_int, self.solver.nodes[nid_int][0], self.solver.nodes[nid_int][1]))
                        
                        intersections_on_new_segment = refreshed_intersections
                        intersections_on_new_segment.sort(key=lambda point: 
                            ((point[1] - x1_current_el) ** 2 + (point[2] - y1_current_el) ** 2) ** 0.5)
                    
                    # Build the sequence of nodes for the new element(s)
                    node_sequence_for_new_element = [self.temp_node] + \
                                                  [nid for nid, _, _ in intersections_on_new_segment] + \
                                                  [node_for_end_of_element]
                    
                    # Remove consecutive duplicates from node_sequence (can happen if intersection coincided with end_node)
                    final_node_sequence = []
                    if node_sequence_for_new_element:
                        final_node_sequence.append(node_sequence_for_new_element[0])
                        for i in range(1, len(node_sequence_for_new_element)):
                            if node_sequence_for_new_element[i] != node_sequence_for_new_element[i-1]:
                                final_node_sequence.append(node_sequence_for_new_element[i])
                    
                    elements_added_this_action_ids = []
                    for i in range(len(final_node_sequence) - 1):
                        start_node_seg = final_node_sequence[i]
                        end_node_seg = final_node_sequence[i+1]
                        
                        # Double check element doesn't exist (e.g. if splitting made it)
                        seg_exists = any(set(el_chk['nodes']) == {start_node_seg, end_node_seg} for el_chk in self.solver.elements.values())
                        if not seg_exists and start_node_seg != end_node_seg: # Ensure not zero length
                            new_eid = max(self.solver.elements.keys()) + 1 if self.solver.elements else 1
                            self.solver.add_element(new_eid, start_node_seg, end_node_seg, effective_etype, mat_id, sec_id)
                            elements_added_this_action_ids.append(new_eid)
                    
                    self._update_plot()
                    self._update_element_list() # Critical after splits and adds
                    
                    self._save_state(f"Add Element(s) from N{self.temp_node} to N{node_for_end_of_element}")
                    
                except Exception as e:
                    messagebox.showerror('Error adding element', str(e))
                    import traceback
                    traceback.print_exc()
                finally:
                    self.temp_node = None
                    if self.temp_line: 
                        self.temp_line.remove()
                        self.temp_line = None
                    self.canvas.draw()

        elif self.current_mode == 'delete':
            # find closest node to click
            closest_node = self._find_closest_node(click_x, click_y)
            
            if closest_node is None:
                return
                
            # check if node is connected to any elements
            connected_elements = []
            for eid, el in self.solver.elements.items():
                if closest_node in el['nodes']:
                    connected_elements.append(eid)
            
            if connected_elements:
                if not messagebox.askyesno('Warning', 
                    f'Node {closest_node} is connected to {len(connected_elements)} elements. Delete node and all connected elements?'):
                    return
                # Delete connected elements
                for eid in connected_elements:
                    del self.solver.elements[eid]
            
            # Delete the node
            del self.solver.nodes[closest_node]
            
            # Renumber remaining nodes and elements sequentially
            self._renumber_nodes()
            self._renumber_elements()
            
            # Update delete node visibility
            self._update_delete_node_visibility()
            
            # Update the UI
            self._update_plot()
            self._update_element_list()
            self._update_node_list()  # Update node list after deletion
            
            # Save state for undo/redo
            self._save_state(f"Delete Node {closest_node}")

    def _find_closest_node(self, x, y, threshold=0.1):
        if not self.solver.nodes:
            return None
            
        closest_node = None
        min_dist = float('inf')
        
        for nid, node in self.solver.nodes.items():
            dist = ((node[0] - x) ** 2 + (node[1] - y) ** 2) ** 0.5
            if dist < min_dist and dist < threshold:
                min_dist = dist
                closest_node = nid
                
        return closest_node

    # ---------------- event handlers ------------------
    def _safe_float(self,widget,default=0):
        try: return float(widget.get())
        except ValueError: return default

    def _safe_int(self,widget):
        return int(float(widget.get()))

    def _update_plot(self, deformed=False):
        self.ax.clear()

        # Define font sizes and offsets
        FS_NODE = 10
        FS_ELEM = 9
        FS_FORCE_VAL = 8
        FS_REACTION_VAL = 8

        NODE_LABEL_OFFSET_Y_ABS = 0.05
        ELEMENT_LABEL_OFFSET_Y_ABS = 0.05
        # FORCE_TEXT_PERP_OFFSET_FACTOR = 0.1 # Factor of max_arrow_length for perp offset
        # REACTION_TEXT_OFFSET_FACTOR = 0.3 # Multiplier for bc_size for further offset
        TEXT_BBOX_STYLE = dict(facecolor='white', alpha=0.75, edgecolor='none', pad=0.2)

        # Plot elements with different colors for edited ones and element IDs
        for eid, el in self.solver.elements.items():
            n1, n2 = el['nodes']
            # Ensure nodes actually exist to prevent KeyError before trying to get coordinates
            if n1 not in self.solver.nodes or n2 not in self.solver.nodes:
                print(f"Warning: Element {eid} references non-existent node(s) {n1} or {n2}. Skipping plot.")
                continue 

            x1, y1 = self.solver.nodes[n1]
            x2, y2 = self.solver.nodes[n2]
            
            # Calculate midpoint for element ID text
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2

            # Check if element is selected in the dropdown
            is_selected = (self.element_var.get() and 
                         int(self.element_var.get().split(':')[0].split()[1]) == eid)
            is_edited = el.get('edited', False)
            is_zero_force = eid in self.zero_force_members
            
            element_color = 'g' if is_edited else 'r' if is_selected else 'k'
            element_style = '--' if is_zero_force else '-'
            element_lw = 1.5 if is_zero_force else 2
            element_alpha = 0.7 if is_zero_force else 1.0
            text_color_zfm = 'orange' # Color for zero-force member ID text

            if deformed and 'displacements' in self.solver.results:
                U = self.solver.results['displacements']
                d1 = U[3*(n1-1):3*(n1-1)+2] * 100  # Scale factor
                d2 = U[3*(n2-1):3*(n2-1)+2] * 100
                self.ax.plot([x1, x2], [y1, y2], color='k', lw=1, alpha=0.3) # Original structure
                self.ax.plot([x1+d1[0], x2+d2[0]], [y1+d1[1], y2+d2[1]],
                           linestyle=':', color=element_color, lw=element_lw, alpha=element_alpha,
                           label='deformed' if eid==list(self.solver.elements.keys())[0] else "")
                # Add element ID to deformed shape (optional, can be cluttered)
                # self.ax.text(mid_x + (d1[0]+d2[0])/2, mid_y + (d1[1]+d2[1])/2, f"E{eid}", color='purple', fontsize=FS_ELEM, ha='center', va='center')
            else:
                self.ax.plot([x1, x2], [y1, y2], 
                           color=element_color, linestyle=element_style,
                           lw=element_lw, alpha=element_alpha)
            
            # Add element ID to original structure plot
            va_val = 'bottom' if y1 <= y2 else 'top'
            y_text_offset_for_element = ELEMENT_LABEL_OFFSET_Y_ABS if y1 <= y2 else -ELEMENT_LABEL_OFFSET_Y_ABS
            current_text_color = text_color_zfm if is_zero_force else 'purple'
            self.ax.text(mid_x, mid_y + y_text_offset_for_element, f"E{eid}", color=current_text_color, fontsize=FS_ELEM, ha='center', va=va_val)

        # Plot nodes
        for nid, (x, y) in self.solver.nodes.items():
            self.ax.plot(x, y, 'bo', ms=6)
            self.ax.text(x, y + NODE_LABEL_OFFSET_Y_ABS, f"{nid}", fontsize=FS_NODE, ha='center')
        
        # Plot loads as arrows
        if self.solver.loads:
            # Calculate max force for scaling
            x_range = self.plot_limits['xmax'] - self.plot_limits['xmin']
            y_range = self.plot_limits['ymax'] - self.plot_limits['ymin']
            max_arrow_length = min(x_range, y_range) * 0.15  # 15% of plot dimension
            
            # Scale factor for arrows
            max_abs_force_val = 0
            for nid_check, load_check in self.solver.loads.items():
                if nid_check in self.solver.nodes:
                    fx_abs = abs(load_check['fx'])
                    fy_abs = abs(load_check['fy'])
                    if fx_abs > max_abs_force_val: max_abs_force_val = fx_abs
                    if fy_abs > max_abs_force_val: max_abs_force_val = fy_abs
            if max_abs_force_val == 0: max_abs_force_val = 1.0 # Avoid division by zero if all forces are zero

            scale_factor = max_arrow_length / max(max_abs_force_val, 1e-10)

            for nid, load in self.solver.loads.items():
                if nid in self.solver.nodes:
                    x_node, y_node = self.solver.nodes[nid]
                    
                    # When showing deformed shape, optionally draw loads on deformed positions
                    if deformed and 'displacements' in self.solver.results:
                        pass # Keep loads on original positions for clarity
                    
                    fx_original = load['fx']
                    fy_original = load['fy']

                    # Draw Fx component arrow
                    if abs(fx_original) > 1e-6: # Threshold to avoid drawing zero-length arrows
                        current_arrow_length_fx = abs(fx_original) * scale_factor
                        current_arrow_length_fx = min(current_arrow_length_fx, max_arrow_length)
                        
                        # Adjust start point and dx for negative forces to point towards the node
                        arrow_start_x = x_node
                        arrow_dx = np.sign(fx_original) * current_arrow_length_fx
                        if fx_original < 0:
                            arrow_start_x = x_node + abs(arrow_dx) # Start to the right
                            # arrow_dx remains negative, pointing left
                        
                        self.ax.arrow(arrow_start_x, y_node, arrow_dx, 0,
                                    head_width=current_arrow_length_fx*0.2, 
                                    head_length=current_arrow_length_fx*0.3,
                                    fc='red', ec='red', 
                                    length_includes_head=True)
                        
                        display_fx = fx_original
                        if self.force_unit.get() == 'lbf':
                            display_fx /= 4.44822
                        force_text_val_fx = f"Fx: {display_fx:.1f} {self.force_unit.get()}"
                        
                        text_x_fx = x_node + arrow_dx * 0.5
                        text_y_fx = y_node
                        perp_offset_dist_fx = min(x_range,y_range) * 0.015
                        offset_dy_text_fx = perp_offset_dist_fx * (-1 if fx_original >=0 else 1)
                        # Ensure text is slightly away from the arrow shaft for negative forces
                        if fx_original < 0: 
                            text_x_fx = x_node + abs(arrow_dx) * 0.5 + abs(arrow_dx) * 0.1 # Shift further right for neg arrow
                        else:
                            text_x_fx = x_node + arrow_dx * 0.5

                        self.ax.text(text_x_fx, text_y_fx + offset_dy_text_fx, force_text_val_fx,
                                   color='red', fontsize=FS_FORCE_VAL,
                                   ha='center', va='center', bbox=TEXT_BBOX_STYLE)

                    # Draw Fy component arrow
                    if abs(fy_original) > 1e-6: # Threshold
                        current_arrow_length_fy = abs(fy_original) * scale_factor
                        current_arrow_length_fy = min(current_arrow_length_fy, max_arrow_length)

                        # Adjust start point and dy for negative forces to point towards the node
                        arrow_start_y = y_node
                        arrow_dy = np.sign(fy_original) * current_arrow_length_fy
                        if fy_original < 0:
                            arrow_start_y = y_node + abs(arrow_dy) # Start above
                            # arrow_dy remains negative, pointing down
                        
                        self.ax.arrow(x_node, arrow_start_y, 0, arrow_dy,
                                    head_width=current_arrow_length_fy*0.2, 
                                    head_length=current_arrow_length_fy*0.3,
                                    fc='blue', ec='blue',
                                    length_includes_head=True)
                        
                        display_fy = fy_original
                        if self.force_unit.get() == 'lbf':
                            display_fy /= 4.44822
                        force_text_val_fy = f"Fy: {display_fy:.1f} {self.force_unit.get()}"
                        
                        text_x_fy = x_node
                        text_y_fy = y_node + arrow_dy * 0.5
                        perp_offset_dist_fy = min(x_range,y_range) * 0.015 
                        offset_dx_text_fy = perp_offset_dist_fy * (-1 if fy_original <=0 else 1)
                        # Ensure text is slightly away from the arrow shaft for negative forces
                        if fy_original < 0:
                            text_y_fy = y_node + abs(arrow_dy) * 0.5 + abs(arrow_dy) * 0.1 # Shift further up for neg arrow
                        else:
                            text_y_fy = y_node + arrow_dy * 0.5

                        self.ax.text(text_x_fy + offset_dx_text_fy, text_y_fy, force_text_val_fy,
                                   color='blue', fontsize=FS_FORCE_VAL,
                                   ha='center', va='center', bbox=TEXT_BBOX_STYLE)
                    
                    # Draw moment arrow if there's a moment
                    m = load['m']
                    if m != 0:
                        # Set radius for moment arc proportional to max_arrow_length
                        radius = max_arrow_length * 0.3
                        direction_for_arrowhead = 1 if m > 0 else -1
                        end_angle_for_arrowhead_calc_rad = np.radians(direction_for_arrowhead * 270)

                        if m >= 0:
                            arc_patch_theta1 = 0
                            arc_patch_theta2 = 270
                        else:
                            arc_patch_theta1 = 90 
                            arc_patch_theta2 = 0 
                        
                        moment_color = 'deeppink'
                        arc = patches.Arc((x_node, y_node), radius*2, radius*2, 
                                        theta1=arc_patch_theta1, theta2=arc_patch_theta2, 
                                        color=moment_color, linewidth=2)
                        self.ax.add_patch(arc)
                        
                        arrow_tail_pos_x = x_node + radius * np.cos(end_angle_for_arrowhead_calc_rad)
                        arrow_tail_pos_y = y_node + radius * np.sin(end_angle_for_arrowhead_calc_rad)
                        arrow_vector_dx = -radius * np.sin(end_angle_for_arrowhead_calc_rad) * direction_for_arrowhead * 0.2
                        arrow_vector_dy =  radius * np.cos(end_angle_for_arrowhead_calc_rad) * direction_for_arrowhead * 0.2
                        
                        self.ax.arrow(arrow_tail_pos_x, arrow_tail_pos_y, arrow_vector_dx, arrow_vector_dy, 
                                    head_width=radius*0.15, 
                                    head_length=radius*0.2,
                                    fc=moment_color, ec=moment_color, 
                                    length_includes_head=True)
                        
                        moment_unit = 'N·m' if self.force_unit.get() == 'N' else 'lbf·ft'
                        display_m = abs(m)
                        if self.force_unit.get() == 'lbf':
                            display_m /= 1.35582
                        moment_text_val = f"{display_m:.1f} {moment_unit}"
                        # Slightly increased offset for moment text
                        self.ax.text(x_node, y_node - radius*0.3, moment_text_val, 
                                   color=moment_color, fontsize=FS_FORCE_VAL, # Using FS_FORCE_VAL
                                   ha='center', va='top', bbox=TEXT_BBOX_STYLE)
        
        # Plot boundary conditions and reactions
        if self.solver.boundary_conditions:
            bc_size = min(x_range, y_range) * 0.05 # Slightly increased bc_size for visibility
            has_reactions = 'reactions' in self.solver.results
            
            for nid, bc in self.solver.boundary_conditions.items():
                if nid in self.solver.nodes:
                    x, y = self.solver.nodes[nid]
                    
                    if deformed and 'displacements' in self.solver.results:
                        # Optionally, draw BCs on deformed shape or skip for clarity
                        # For now, BCs remain on original positions
                        pass # Keep BCs on original positions
                    
                    rx_val, ry_val, rm_val = 0,0,0
                    reaction_text_parts = []
                    if has_reactions and nid in self.solver.results['reactions']:
                        rx_val, ry_val, rm_val = self.solver.results['reactions'][nid]
                        # Unit conversion for display
                        display_rx = rx_val / 4.44822 if self.force_unit.get() == 'lbf' else rx_val
                        display_ry = ry_val / 4.44822 if self.force_unit.get() == 'lbf' else ry_val
                        display_rm = rm_val / 1.35582 if self.force_unit.get() == 'lbf' else rm_val
                        
                        if abs(rx_val) > 1e-6: reaction_text_parts.append(f"Rx={display_rx:.1f} {self.force_unit.get()}")
                        if abs(ry_val) > 1e-6: reaction_text_parts.append(f"Ry={display_ry:.1f} {self.force_unit.get()}")
                        if abs(rm_val) > 1e-6: reaction_text_parts.append(f"M={display_rm:.1f} {'N·m' if self.force_unit.get() == 'N' else 'lbf·ft'}")    

                    reaction_text = '\n'.join(reaction_text_parts)
                    text_y_offset_bc = -bc_size * 1.2 # General offset for reaction text below symbol
                    text_x_offset_bc = 0
                    text_ha_bc = 'center'
                    text_va_bc = 'top'

                    # Define types based on constraints
                    is_fixed = bc.get('ux') == 0 and bc.get('uy') == 0 and bc.get('th') == 0
                    is_pinned = bc.get('ux') == 0 and bc.get('uy') == 0 and bc.get('th') is None
                    is_roller_y_constrained = bc.get('uy') == 0 and bc.get('ux') is None and bc.get('th') is None # Rolls in X, Y fixed
                    is_roller_x_constrained = bc.get('ux') == 0 and bc.get('uy') is None and bc.get('th') is None # Rolls in Y, X fixed

                    if is_fixed:
                        line_len_vert = bc_size * 0.8
                        bar_width = bc_size * 1.2
                        hash_len = bc_size * 0.3
                        num_hashes = 5
                        # Vertical line from node
                        self.ax.plot([x, x], [y, y - line_len_vert], 'b-', lw=2)
                        # Horizontal bar
                        self.ax.plot([x - bar_width/2, x + bar_width/2], [y - line_len_vert, y - line_len_vert], 'b-', lw=2)
                        # Hash marks
                        for i in range(num_hashes):
                            hash_x_start = x - bar_width/2 + i * (bar_width / (num_hashes -1))
                            self.ax.plot([hash_x_start, hash_x_start - hash_len*0.707],
                                       [y - line_len_vert, y - line_len_vert - hash_len*0.707], 'b-', lw=1)
                        text_y_offset_bc = y - line_len_vert - hash_len - bc_size * 0.2
                    
                    elif is_pinned:
                        tri_height = bc_size
                        tri_width_half = bc_size * 0.6
                        triangle = patches.Polygon([[x, y], [x - tri_width_half, y - tri_height], [x + tri_width_half, y - tri_height]],
                                                 closed=True, color='blue', alpha=0.7)
                        self.ax.add_patch(triangle)
                        text_y_offset_bc = y - tri_height - bc_size * 0.2
                    
                    elif is_roller_y_constrained: # Rolls in X, Y constrained (image roller)
                        tri_height = bc_size * 0.8
                        tri_width_half = bc_size * 0.5
                        circle_r = bc_size * 0.15
                        # Triangle
                        triangle = patches.Polygon([[x, y], [x - tri_width_half, y - tri_height], [x + tri_width_half, y - tri_height]],
                                                 closed=True, color='blue', alpha=0.7)
                        self.ax.add_patch(triangle)
                        # Circles below triangle base
                        circle_y_center = y - tri_height - circle_r
                        self.ax.add_patch(patches.Circle((x - 2*circle_r, circle_y_center), circle_r, color='blue', alpha=0.7))
                        self.ax.add_patch(patches.Circle((x, circle_y_center), circle_r, color='blue', alpha=0.7))
                        self.ax.add_patch(patches.Circle((x + 2*circle_r, circle_y_center), circle_r, color='blue', alpha=0.7))
                        text_y_offset_bc = circle_y_center - circle_r - bc_size * 0.2

                    elif is_roller_x_constrained: # Rolls in Y, X constrained (rotated roller)
                        tri_width = bc_size * 0.8 # Triangle "height" when rotated is its width along x-axis
                        tri_height_half = bc_size * 0.5 # Triangle "width" when rotated is its height along y-axis
                        circle_r = bc_size * 0.15
                        # Rotated Triangle (points left)
                        triangle = patches.Polygon([[x, y], [x - tri_width, y - tri_height_half], [x - tri_width, y + tri_height_half]],
                                                 closed=True, color='blue', alpha=0.7)
                        self.ax.add_patch(triangle)
                        # Circles left of triangle base
                        circle_x_center = x - tri_width - circle_r
                        self.ax.add_patch(patches.Circle((circle_x_center, y - 2*circle_r), circle_r, color='blue', alpha=0.7))
                        self.ax.add_patch(patches.Circle((circle_x_center, y), circle_r, color='blue', alpha=0.7))
                        self.ax.add_patch(patches.Circle((circle_x_center, y + 2*circle_r), circle_r, color='blue', alpha=0.7))
                        text_x_offset_bc = circle_x_center - circle_r - bc_size * 0.2
                        text_y_offset_bc = y # Center vertically for rotated roller
                        text_ha_bc = 'right'
                        text_va_bc = 'center'
                    
                    else: # Custom/Fallback to arrows for individual constraints
                        has_x_constraint = bc.get('ux') == 0
                        has_y_constraint = bc.get('uy') == 0
                        has_rot_constraint = bc.get('th') == 0
                        arrow_len_roller = bc_size * 0.6 # Smaller arrows for custom
                        
                        # Store reaction parts for custom display next to their arrows
                        custom_reaction_parts_drawn = set()

                        if has_x_constraint:
                            self.ax.plot([x - arrow_len_roller, x + arrow_len_roller], [y,y], 'b-', lw=3, solid_capstyle='butt') # Thicker line for X constraint
                            if reaction_text and 'Rx' in reaction_text and 'Rx' not in custom_reaction_parts_drawn:
                                rx_part = [p for p in reaction_text_parts if 'Rx' in p][0]
                                self.ax.text(x + arrow_len_roller + bc_size*0.1, y, rx_part, color='blue', 
                                           fontsize=FS_REACTION_VAL, ha='left', va='center', bbox=TEXT_BBOX_STYLE)
                                custom_reaction_parts_drawn.add('Rx')
                        
                        if has_y_constraint:
                            self.ax.plot([x,x], [y - arrow_len_roller, y + arrow_len_roller], 'b-', lw=3, solid_capstyle='butt') # Thicker line for Y constraint
                            if reaction_text and 'Ry' in reaction_text and 'Ry' not in custom_reaction_parts_drawn:
                                ry_part = [p for p in reaction_text_parts if 'Ry' in p][0]
                                self.ax.text(x, y + arrow_len_roller + bc_size*0.1, ry_part, color='blue', 
                                           fontsize=FS_REACTION_VAL, ha='center', va='bottom', bbox=TEXT_BBOX_STYLE)
                                custom_reaction_parts_drawn.add('Ry')
                        
                        if has_rot_constraint:
                            rot_symbol_size = bc_size * 0.4
                            # Square symbol for rotation constraint
                            self.ax.add_patch(patches.Rectangle((x - rot_symbol_size/2, y - rot_symbol_size/2), 
                                                               rot_symbol_size, rot_symbol_size, fill=True, color='blue', alpha=0.7))
                            if reaction_text and 'M=' in reaction_text and 'M=' not in custom_reaction_parts_drawn:
                                m_part = [p for p in reaction_text_parts if 'M=' in p][0]
                                self.ax.text(x, y - rot_symbol_size - bc_size*0.1, m_part, color='blue', 
                                           fontsize=FS_REACTION_VAL, ha='center', va='top', bbox=TEXT_BBOX_STYLE)
                                custom_reaction_parts_drawn.add('M=')
                        # Fallback for text if not drawn with specific arrows
                        if reaction_text and not (is_fixed or is_pinned or is_roller_y_constrained or is_roller_x_constrained):
                             remaining_reaction_text = '\n'.join([p for p in reaction_text_parts if not any(k in p for k in custom_reaction_parts_drawn)])
                             if remaining_reaction_text:
                                self.ax.text(x + text_x_offset_bc, y + text_y_offset_bc * 0.5, remaining_reaction_text, color='blue', 
                                       fontsize=FS_REACTION_VAL, ha=text_ha_bc, va=text_va_bc, bbox=TEXT_BBOX_STYLE)
                        continue # Skip common reaction text for custom

                    # Common reaction text drawing for standard symbols (Fixed, Pinned, Rollers)
                    if reaction_text and (is_fixed or is_pinned or is_roller_y_constrained or is_roller_x_constrained):
                        # Use text_y_offset_bc or text_x_offset_bc determined by the symbol type
                        plot_text_x = x + text_x_offset_bc if is_roller_x_constrained else x
                        plot_text_y = text_y_offset_bc if is_roller_x_constrained else text_y_offset_bc # y is absolute for others
                        
                        self.ax.text(plot_text_x, plot_text_y, reaction_text, color='blue',
                                   fontsize=FS_REACTION_VAL, ha=text_ha_bc, va=text_va_bc, bbox=TEXT_BBOX_STYLE)
        
        self.ax.set_xlim(self.plot_limits['xmin'], self.plot_limits['xmax'])
        self.ax.set_ylim(self.plot_limits['ymin'], self.plot_limits['ymax'])
        
        # Add grid
        self.ax.grid(True, linestyle='--', alpha=0.7)
        
        # Equal aspect ratio
        self.ax.set_aspect('equal')
        
        # Add axis labels with units
        unit = self.distance_unit.get()
        self.ax.set_xlabel(f'X ({unit})')
        self.ax.set_ylabel(f'Y ({unit})')
        
        # Add title based on mode
        # self.ax.set_title(f'Mode: {self.current_mode.capitalize()} | Analysis: {self.analysis_mode_var.get().capitalize()}')
        self.ax.set_title(f'Mode: {self.current_mode.capitalize()} | Analysis: Frame') # Hardcoded to Frame
        
        if deformed:
            self.ax.legend(loc='best')
            
        self.canvas.draw()

    # add actions --------------------------------------
    def _gui_add_node(self):
        nid=self._safe_int(self._entry_nid); x=self._safe_float(self._entry_nx); y=self._safe_float(self._entry_ny)
        try:
            self.solver.add_node(nid,x,y)
            self._update_plot()
        except Exception as e: messagebox.showerror('Error',str(e))

    def _gui_add_element(self):
        eid=self._safe_int(self._entry_eid)
        n1=self._safe_int(self._entry_e_n1); n2=self._safe_int(self._entry_e_n2)
        etype=self._etype.get()
        try:
            self.solver.add_element(eid,n1,n2,etype)
            self._update_plot()
        except Exception as e: messagebox.showerror('Error',str(e))

    def _gui_add_load(self):
        nid = self._safe_int(self._entry_ln)
        Fx = self._safe_float(self._entry_Fx)
        Fy = self._safe_float(self._entry_Fy)
        M = self._safe_float(self._entry_M)
        
        # Convert force units if needed
        if self.force_unit.get() == 'lbf':
            Fx *= 4.44822  # Convert lbf to N
            Fy *= 4.44822  # Convert lbf to N
            M *= 1.35582   # Convert lbf·ft to N·m
        
        # Save the current state before making changes
        self._save_state(f"Before Add Load to Node {nid}")
        
        self.solver.add_load(nid, Fx, Fy, M)
        self._update_plot()
        self._update_mode()  # Ensure all modes are properly accessible
        
        # Save the new state
        self._save_state(f"Add Load to Node {nid}")

    
    def _gui_solve(self):
        try:
            # Pass the current analysis mode from the GUI to the solver
            # current_gui_analysis_mode = self.analysis_mode_var.get() # Removed
            # self.solver.solve(analysis_mode=current_gui_analysis_mode) # Pass 'frame' or remove param
            self.solver.solve() # Solver will use its default or internal 'frame' mode
            messagebox.showinfo('Solved', f'Analysis complete (Frame mode).') # Hardcoded to Frame
            self._update_plot(deformed=False)
        except Exception as e:
            error_message = str(e)
            
            # Format message for better readability
            if "Structure is likely under-constrained" in error_message or "Stiffness matrix is singular" in error_message:
                # Perform structural diagnostics before showing dialog
                diagnostics = self._diagnose_structure('frame') # Pass 'frame' directly
                
                # Create a more detailed error dialog
                error_dialog = tk.Toplevel(self)
                error_dialog.title("Structural Analysis Error")
                error_dialog.geometry("700x550")
                
                # Add icon and header
                header_frame = ttk.Frame(error_dialog)
                header_frame.pack(fill='x', pady=10, padx=15)
                
                # Error icon would go here if available
                ttk.Label(header_frame, text="Analysis Failed: Structure Unstable", font=('Arial', 14, 'bold')).pack(side='left')
                
                # Main error message
                main_msg = error_message.split('\n')[0]  # First line
                ttk.Label(error_dialog, text=main_msg, wraplength=670).pack(fill='x', padx=15, pady=5)
                
                # Create a notebook/tab control for organized troubleshooting
                notebook = ttk.Notebook(error_dialog)
                notebook.pack(fill='both', expand=True, padx=15, pady=5)
                
                # Tab 1: Status Checklist
                checklist_frame = ttk.Frame(notebook, padding=10)
                notebook.add(checklist_frame, text="Diagnostic Checklist")
                
                # Create the checklist with status indicators
                checklist_text = ttk.Label(checklist_frame, text="Structure Stability Checklist:", 
                                          font=('Arial', 10, 'bold'))
                checklist_text.pack(fill='x', pady=(0, 10), anchor='w')
                
                # Create a frame for the checklist items
                checklist_items_frame = ttk.Frame(checklist_frame)
                checklist_items_frame.pack(fill='both', expand=True)
                
                # Add checklist items with status indicators
                row = 0
                for item_name, status, message in diagnostics['checklist']:
                    icon = "✓" if status else "✗"
                    color = "green" if status else "red"
                    
                    item_frame = ttk.Frame(checklist_items_frame)
                    item_frame.pack(fill='x', pady=2)
                    
                    # Add status icon
                    status_label = ttk.Label(item_frame, text=icon, foreground=color, font=('Arial', 10, 'bold'))
                    status_label.pack(side='left', padx=(5, 10))
                    
                    # Add item description with message
                    full_message = f"{item_name}: {message}"
                    desc_label = ttk.Label(item_frame, text=full_message, wraplength=600, justify='left')
                    desc_label.pack(side='left', fill='x', expand=True)
                    
                    row += 1
                
                # Add a summary and recommendation
                summary_frame = ttk.LabelFrame(checklist_frame, text="Summary & Recommendation")
                summary_frame.pack(fill='x', pady=10)
                
                ttk.Label(summary_frame, text=diagnostics['summary'], wraplength=650, justify='left').pack(padx=5, pady=5)
                
                # Tab 2: Technical Details
                detail_frame = ttk.Frame(notebook, padding=10)
                notebook.add(detail_frame, text="Technical Details")
                
                # Create scrolled text area
                import tkinter.scrolledtext as scrolledtext
                details_text = scrolledtext.ScrolledText(detail_frame, wrap=tk.WORD, height=12)
                details_text.pack(fill='both', expand=True, padx=5, pady=5)
                
                # Get the detailed part of the message (after first line)
                details = '\n'.join(error_message.split('\n')[1:])
                details_text.insert(tk.END, details)
                details_text.config(state='disabled')  # Make read-only
                
                # Tab 3: General Help
                help_frame = ttk.Frame(notebook, padding=10)
                notebook.add(help_frame, text="General Help")
                
                # Add general help information
                # current_analysis_type = self.analysis_mode_var.get() # Removed
                current_analysis_type = 'frame' # Hardcoded
                boundary_count = len(self.solver.boundary_conditions)
                node_count = len(self.solver.nodes)
                element_count = len(self.solver.elements)
                
                help_text = f"Your structure has: {node_count} nodes, {element_count} elements, and {boundary_count} boundary condition(s).\n\n"
                
                # Add static determinacy explanation
                help_text += "Static Determinacy Check (2n = m + r):\n"
                help_text += " • n = number of nodes = " + str(node_count) + "\n"
                help_text += " • m = number of elements/members = " + str(element_count) + "\n"
                
                # Calculate actual number of reactions (constrained DOFs)
                r = 0
                for nid, bc in self.solver.boundary_conditions.items():
                    if bc.get('ux') == 0:
                        r += 1
                    if bc.get('uy') == 0:
                        r += 1
                    if bc.get('th') == 0:
                        r += 1
                
                help_text += " • r = number of independent support reaction components (e.g., a pin provides 2 (Rx, Ry); a fixed support provides 3 (Rx, Ry, Mz)) = " + str(r) + "\n\n"
                
                # Calculate static determinacy
                n = node_count
                m = element_count
                static_check = 2*n - (m + r)
                
                if static_check == 0:
                    help_text += f"For a statically determinate structure: 2n = m + r\n"
                    help_text += f"2×{n} = {m} + {r} ✓ Your structure is statically determinate.\n\n"
                elif static_check < 0:
                    help_text += f"For a statically determinate structure: 2n = m + r\n"
                    help_text += f"2×{n} < {m} + {r} ✗ Your structure is statically indeterminate (has {abs(static_check)} redundant constraint(s)).\n\n"
                else:
                    help_text += f"For a statically determinate structure: 2n = m + r\n"
                    help_text += f"2×{n} > {m} + {r} ✗ Your structure is a mechanism (has {static_check} degree(s) of freedom).\n\n"
                
                help_text += "Structural Stability Definitions:\n"
                help_text += " • Mechanism: A structure that can move without deforming. It cannot safely carry loads\n   because it has unconstrained degrees of freedom.\n\n"
                help_text += " • Statically Determinate: A structure where reactions and internal forces can be\n   determined using only equilibrium equations. The 2n = m + r equation is satisfied.\n\n"
                help_text += " • Statically Indeterminate: A structure with redundant members or supports.\n   Has higher reliability but requires more complex analysis methods.\n\n"
                
                # Specific recommendations based on analysis type
                # if current_analysis_type == 'truss': # This block can be removed or merged/simplified
                #     min_required = 2  # Minimum required support reactions for a basic truss
                #     help_text += "For a 2D TRUSS analysis:\n"
                #     help_text += " • Each node must be properly connected (check for disconnected nodes)\n"
                #     help_text += " • You need at least 3 support reactions total (e.g., one fixed support OR one pin + one roller)\n"
                #     help_text += " • Common truss supports: pins (constrain X and Y) and rollers (constrain only X or only Y)\n"
                #     help_text += " • For statically determinate trusses, supports should provide exactly 3 reactions\n"
                # else:  # Frame/beam analysis (this is the only mode now)
                min_required = 3  # Minimum required support reactions for a basic frame
                help_text += "For a 2D FRAME/BEAM analysis:\n"
                help_text += " • Each node must be properly connected (check for disconnected nodes)\n"
                help_text += " • You need at least 3 support reactions total (e.g., one fixed support OR various combinations of pins/rollers)\n"
                help_text += " • Common frame supports: fixed (constrain X, Y, and rotation), pins, and rollers\n"
                help_text += " • For a simple beam, one fixed support OR one pin + one roller is sufficient\n"
                help_text += " • For statically determinate frames, supports should provide exactly 3 reactions\n"
                # End of specific recommendations adjustment
                
                if boundary_count < min_required:
                    help_text += f"\nProblem: You only have {boundary_count} boundary condition(s), which is likely insufficient.\n"
                    help_text += "Action: Add more boundary conditions (supports) to properly constrain your structure.\n"
                
                # Add special cases information
                help_text += "\nCommon Issues:\n"
                help_text += " • Disconnected or floating nodes (add elements to connect them)\n"
                help_text += " • Insufficient supports (add boundary conditions)\n"
                help_text += " • Improperly defined sections (check section properties)\n"
                help_text += " • 'Mechanisms' where parts can still move despite supports\n"
                help_text += " • Using wrong element types (beams vs. truss elements)\n"
                
                ttk.Label(help_frame, text=help_text, wraplength=650, justify='left').pack(padx=5, pady=5)
                
                # Close button at the bottom
                button_frame = ttk.Frame(error_dialog)
                button_frame.pack(fill='x', padx=15, pady=10)
                ttk.Button(button_frame, text="Close", command=error_dialog.destroy).pack(side='right', padx=5)
                
                # Make dialog modal
                error_dialog.transient(self)
                error_dialog.grab_set()
                self.wait_window(error_dialog)
            else:
                # For other errors, use simple messagebox
                messagebox.showerror('Solve Error', str(e))

    def _gui_plot_def(self):
        if 'displacements' not in self.solver.results:
            messagebox.showwarning('Info','Run Solve first.')
            return
        self._update_plot(deformed=True)

    def _gui_export(self,fmt):
        if 'displacements' not in self.solver.results:
            messagebox.showwarning('Info','Run Solve first.')
            return
        fname=filedialog.asksaveasfilename(defaultextension=f'.{fmt}',
                                           filetypes=[(f'{fmt.upper()} file',f'*.{fmt}')])
        if fname:
            if fmt == 'pdf':
                try:
                    self._generate_pdf_report(fname)
                    messagebox.showinfo('Export', f'PDF Report saved to {fname}')
                except Exception as e:
                    messagebox.showerror('PDF Export Error', f'Could not generate PDF: {str(e)}')
                    import traceback
                    traceback.print_exc()
            # else: # CSV export - Removed
            # self.solver.export_results(fname,fmt)
            # messagebox.showinfo('Export',f'Saved to {fname}')

    def _generate_pdf_report(self, filename):
        if 'displacements' not in self.solver.results:
            messagebox.showwarning('Info', 'Run Solve first before exporting PDF report.')
            return

        original_ax_title = self.ax.get_title() # Save original title
        
        # Define a consistent threshold for what's considered a "zero" force
        # This should align with display precision (e.g., for :.2f, 0.005 is a good threshold)
        zero_force_threshold = 5e-3 # Changed from 1e-6

        with PdfPages(filename) as pdf:
            # Page 1: Undeformed Structure Plot
            self.ax.set_title("Undeformed Structure")
            self._update_plot(deformed=False) # Ensure current plot is undeformed
            pdf.savefig(self.fig) 
            self.ax.set_title(original_ax_title) # Restore title for GUI

            # Page 2: Deformed Structure Plot
            if 'displacements' in self.solver.results:
                self.ax.set_title("Deformed Structure (Scaled Displacements)")
                self._update_plot(deformed=True)
                pdf.savefig(self.fig)
                self._update_plot(deformed=False) # Revert GUI to undeformed
                self.ax.set_title(original_ax_title) # Restore title for GUI

            # Subsequent Pages: SFD and BMD for beam-like elements
            beam_threshold_I = 1e-9 # Elements with I > this are treated as beams for SFD/BMD
            
            # Add a summary page for forces before individual diagrams
            # This requires creating a new figure and populating it with text.
            # For simplicity, this textual summary will be basic.
            summary_fig, summary_ax = plt.subplots(figsize=(8.5, 11)) # Letter paper size
            summary_ax.axis('off') # No axes for text page
            summary_ax.set_title("Results Summary", fontsize=16)
            
            text_lines = ["Structural Analysis Report Summary"]
            text_lines.append("===================================") # Added separator
            
            # Node Coordinates
            text_lines.append("\n--- Node Coordinates ---")
            if not self.solver.nodes:
                text_lines.append("  No nodes defined.")
            else:
                dist_unit = self.distance_unit.get()
                for nid, coords in sorted(self.solver.nodes.items()):
                    text_lines.append(f"  Node {nid}: (X={coords[0]:.3f}, Y={coords[1]:.3f}) {dist_unit}")
            text_lines.append("--------------------")

            text_lines.append("\n--- External Loads ---")
            if not self.solver.loads:
                text_lines.append("  No external loads applied.")
            else:
                for nid, load in self.solver.loads.items():
                    fx, fy, m = load['fx'], load['fy'], load['m']
                    f_unit = self.force_unit.get()
                    m_unit = 'N·m' if f_unit == 'N' else 'lbf·ft'
                    parts = []
                    if abs(fx) > 1e-6: parts.append(f"Fx={fx:.2f} {f_unit}")
                    if abs(fy) > 1e-6: parts.append(f"Fy={fy:.2f} {f_unit}")
                    if abs(m) > 1e-6: parts.append(f"M={m:.2f} {m_unit}")
                    if parts:
                        text_lines.append(f"Node {nid}: { ', '.join(parts)}")
            text_lines.append("--------------------")

            text_lines.append("\n--- Support Reactions ---")
            if not self.solver.results.get('reactions'):
                text_lines.append("  No support reactions calculated (or solve not run).")
            else:
                for nid, r_vals in self.solver.results['reactions'].items():
                    rx, ry, rm = r_vals
                    f_unit = self.force_unit.get()
                    m_unit = 'N·m' if f_unit == 'N' else 'lbf·ft'
                    parts = []
                    if abs(rx) > 1e-6: parts.append(f"Rx={rx:.2f} {f_unit}")
                    if abs(ry) > 1e-6: parts.append(f"Ry={ry:.2f} {f_unit}")
                    if abs(rm) > 1e-6: parts.append(f"M={rm:.2f} {m_unit}")
                    if parts:
                        text_lines.append(f"Node {nid}: { ', '.join(parts)}")
            text_lines.append("--------------------")

            text_lines.append("\n--- Truss Determinacy Check (m+r=2n) ---")
            num_nodes = len(self.solver.nodes)
            num_elements = len(self.solver.elements)
            num_reactions = 0
            # Count translational reaction components for the classic 2D truss determinacy check
            for bc_node_id, bc_props in self.solver.boundary_conditions.items():
                if bc_props.get('ux') == 0: 
                    num_reactions += 1
                if bc_props.get('uy') == 0: 
                    num_reactions += 1
                # Rotational constraints (th=0) are typically not counted in the basic m+r=2n for trusses,
                # as it assumes pin joints. They affect overall stability differently.

            if num_nodes > 0: 
                m_val = num_elements
                r_val = num_reactions
                n_val = num_nodes
                determinacy_value = (m_val + r_val) - (2 * n_val)
                
                text_lines.append(f"  Number of Members (m): {m_val}")
                text_lines.append(f"  Number of Joints (n): {n_val}")
                text_lines.append(f"  Number of External Reaction Components (r): {r_val} (translational)")
                text_lines.append(f"  Equation: m + r = {m_val + r_val}")
                text_lines.append(f"  Equation: 2n = {2 * n_val}")
                
                if determinacy_value == 0:
                    text_lines.append("  Status: The truss is Statically Determinate (according to m+r=2n).")
                elif determinacy_value > 0:
                    text_lines.append(f"  Status: The truss is Statically Indeterminate to the {determinacy_value} degree (m+r > 2n).")
                else: # determinacy_value < 0
                    text_lines.append(f"  Status: The truss is Unstable (m+r < 2n, {abs(determinacy_value)} DOF too many, or improper arrangement).")
            else:
                text_lines.append("  No structure defined to perform determinacy check.")
            text_lines.append("--------------------")

            text_lines.append("\\n--- Element Axial Forces ---")
            if not self.solver.elements:
                text_lines.append("  No elements in the structure.")
            else:
                all_axial_forces_found = True # Initialize flag
                for eid in self.solver.elements:
                    axial_force = self.solver.get_element_axial_force(eid)
                    if axial_force is not None:
                        f_unit = self.force_unit.get()
                        # Add tolerance for 'Zero' status
                        if abs(axial_force) < zero_force_threshold: # Use the new consistent threshold
                            status = 'Zero'
                        elif axial_force > 0:
                            status = 'Tension'
                        else:
                            status = 'Compression'
                        
                        # If status is 'Zero', display the value as 0.00 to avoid -0.00
                        display_value = 0.0 if status == 'Zero' else axial_force
                        text_lines.append(f"Element {eid}: {display_value:.2f} {f_unit} ({status})")
                    else:
                        text_lines.append(f"Element {eid}: Could not retrieve axial force.") 
                        all_axial_forces_found = False # Ensure this is set if any force is None
                text_lines.append("--------------------")

            current_y_pos = 0.95
            line_height = 0.025 # Adjusted for potentially more lines
            for line in text_lines:
                summary_ax.text(0.05, current_y_pos, line, fontsize=10, va='top')
                current_y_pos -= line_height
                if current_y_pos < 0.05: # New page if text overflows
                    pdf.savefig(summary_fig)
                    plt.close(summary_fig)
                    summary_fig, summary_ax = plt.subplots(figsize=(8.5, 11))
                    summary_ax.axis('off')
                    current_y_pos = 0.95
            
            pdf.savefig(summary_fig)
            plt.close(summary_fig)

            for eid, el_props in self.solver.elements.items():
                sec = self.solver.sections[el_props['sec']]
                if sec['I'] > beam_threshold_I: # This is a beam-like element
                    x_coords, shear, moment = self.solver.get_element_shear_moment(eid, num_points=100)
                    if x_coords is not None:
                        # Create SFD plot
                        fig_sfd, ax_sfd = plt.subplots(figsize=(8, 4))
                        ax_sfd.plot(x_coords, shear, 'b-')
                        ax_sfd.fill_between(x_coords, 0, shear, where=shear>0, interpolate=True, color='lightblue', alpha=0.5)
                        ax_sfd.fill_between(x_coords, 0, shear, where=shear<0, interpolate=True, color='lightcoral', alpha=0.5)
                        ax_sfd.set_title(f'Element {eid} - Shear Force Diagram ({self.force_unit.get()})')
                        ax_sfd.set_xlabel(f'Distance along element ({self.distance_unit.get()})')
                        ax_sfd.set_ylabel(f'Shear Force ({self.force_unit.get()})')
                        ax_sfd.grid(True)
                        pdf.savefig(fig_sfd)
                        plt.close(fig_sfd)

                        # Create BMD plot
                        fig_bmd, ax_bmd = plt.subplots(figsize=(8, 4))
                        ax_bmd.plot(x_coords, moment, 'r-')
                        ax_bmd.fill_between(x_coords, 0, moment, where=moment>0, interpolate=True, color='lightcoral', alpha=0.5)
                        ax_bmd.fill_between(x_coords, 0, moment, where=moment<0, interpolate=True, color='lightblue', alpha=0.5)
                        moment_unit_string = 'N·m' if self.force_unit.get() == "N" else 'lbf·ft'
                        ax_bmd.set_title(f'Element {eid} - Bending Moment Diagram ({moment_unit_string})')
                        ax_bmd.set_xlabel(f'Distance along element ({self.distance_unit.get()})')
                        ax_bmd.set_ylabel(f'Bending Moment ({moment_unit_string})')
                        ax_bmd.grid(True)
                        pdf.savefig(fig_bmd)
                        plt.close(fig_bmd)

            # Restore GUI plot to its last state if needed (e.g. if ZFM was active)
            self._update_plot() 

    def _zoom_in(self):
        # Zoom in by reducing the plot limits by 20%
        x_range = self.plot_limits['xmax'] - self.plot_limits['xmin']
        y_range = self.plot_limits['ymax'] - self.plot_limits['ymin']
        
        self.plot_limits['xmin'] += x_range * 0.1
        self.plot_limits['xmax'] -= x_range * 0.1
        self.plot_limits['ymin'] += y_range * 0.1
        self.plot_limits['ymax'] -= y_range * 0.1
        
        self._update_plot()

    def _zoom_out(self):
        # Zoom out by increasing the plot limits by 20%
        x_range = self.plot_limits['xmax'] - self.plot_limits['xmin']
        y_range = self.plot_limits['ymax'] - self.plot_limits['ymin']
        
        self.plot_limits['xmin'] -= x_range * 0.1
        self.plot_limits['xmax'] += x_range * 0.1
        self.plot_limits['ymin'] -= y_range * 0.1
        self.plot_limits['ymax'] += y_range * 0.1
        
        self._update_plot()

    def _reset_view(self):
        # Reset to initial plot limits
        self.plot_limits = {'xmin': -10, 'xmax': 10, 'ymin': -10, 'ymax': 10}
        self._update_plot()

    def _on_release(self, event):
        # End panning
        self.pan_start = None

    def _on_mouse_move(self, event):
        if event.inaxes != self.ax:
            return

        # Handle panning
        if self.pan_start is not None and event.button == 3:  # Right click drag
            # Calculate movement in screen coordinates
            dx_screen = event.x - self.pan_start[0]
            dy_screen = event.y - self.pan_start[1]
            
            # Convert screen movement to data coordinates
            start_data = self._screen_to_data_coords(self.pan_start[0], self.pan_start[1])
            end_data = self._screen_to_data_coords(event.x, event.y)
            
            dx_data = start_data[0] - end_data[0]
            dy_data = start_data[1] - end_data[1]
            
            # Update plot limits
            self.plot_limits['xmin'] += dx_data
            self.plot_limits['xmax'] += dx_data
            self.plot_limits['ymin'] += dy_data
            self.plot_limits['ymax'] += dy_data
            
            # Update pan start position
            self.pan_start = (event.x, event.y)
            
            # Update plot
            self._update_plot()
            return

        # Handle element placement preview
        if self.current_mode == 'element' and self.temp_node is not None:
            # Update temporary line to current mouse position
            if self.temp_line:
                x1, y1 = self.solver.nodes[self.temp_node]
                self.temp_line.set_data([x1, event.xdata], [y1, event.ydata])
                self.canvas.draw()

    def _on_force_unit_change(self, *args):
        """Update force unit labels when unit selection changes"""
        try:
            # Update labels - NO LONGER NEEDED as labels are static now
            # force_label_fx = f'Fx ({self.force_unit.get()})'
            # self._entry_Fx.master.master.children['!label'].configure(text=force_label_fx)
            # force_label_fy = f'Fy ({self.force_unit.get()})'
            # self._entry_Fy.master.master.children['!label'].configure(text=force_label_fy)
            
            # moment_unit_text = 'N·m' if self.force_unit.get() == 'N' else 'lbf·ft'
            # self._entry_M.master.master.children['!label'].configure(text=f'Moment ({moment_unit_text})')
            
            # Convert values in entry fields if they contain values
            # This part is still relevant if you want values to auto-convert upon unit change
            # However, the original request was only about label text. 
            # For now, I'll keep the conversion logic as it might be expected behavior.
            # If you want to remove auto-conversion of values, let me know.
            self._convert_force_values() 
            
            # Update plot with new unit labels for forces/moments shown on plot
            self._update_plot()
        except Exception as e:
            print(f"Error updating force units: {str(e)}")

    def _on_distance_unit_change(self, *args):
        """Update distance unit labels when unit selection changes"""
        try:
            # Update axis labels in plot
            self._update_plot()  # This will update the axis labels
            
            # No need to convert node coordinates as they remain in base units internally
        except Exception as e:
            print(f"Error updating distance units: {str(e)}")
    
    def _convert_force_values(self):
        """Convert force values in entry fields when unit changes"""
        try:
            # Only convert if values are present
            if self._entry_Fx.get():
                fx_value = float(self._entry_Fx.get())
                if self.force_unit.get() == 'N':  # Converting from lbf to N
                    fx_value *= 4.44822
                else:  # Converting from N to lbf
                    fx_value /= 4.44822
                self._entry_Fx.delete(0, tk.END)
                self._entry_Fx.insert(0, f"{fx_value:.2f}")
                
            if self._entry_Fy.get():
                fy_value = float(self._entry_Fy.get())
                if self.force_unit.get() == 'N':  # Converting from lbf to N
                    fy_value *= 4.44822
                else:  # Converting from N to lbf
                    fy_value /= 4.44822
                self._entry_Fy.delete(0, tk.END)
                self._entry_Fy.insert(0, f"{fy_value:.2f}")
                
            if self._entry_M.get():
                m_value = float(self._entry_M.get())
                if self.force_unit.get() == 'N':  # Converting from lbf·ft to N·m
                    m_value *= 1.35582
                else:  # Converting from N·m to lbf·ft
                    m_value /= 1.35582
                self._entry_M.delete(0, tk.END)
                self._entry_M.insert(0, f"{m_value:.2f}")
                
        except Exception as e:
            print(f"Error converting force values: {str(e)}")

    def _show_section_type_dialog(self):
        """Show dialog for selecting section type"""
        dialog = tk.Toplevel(self)
        dialog.title("Select Cross-Section Type")
        dialog.geometry("300x300")
        
        section_type = tk.StringVar()
        
        ttk.Label(dialog, text="Select section type:").pack(pady=10)
        
        ttk.Radiobutton(dialog, text="Rectangle", variable=section_type, value="rectangle").pack(fill='x', pady=2)
        ttk.Radiobutton(dialog, text="Round", variable=section_type, value="round").pack(fill='x', pady=2)
        ttk.Radiobutton(dialog, text="I-Beam", variable=section_type, value="ibeam").pack(fill='x', pady=2)
        ttk.Radiobutton(dialog, text="Channel", variable=section_type, value="channel").pack(fill='x', pady=2)
        ttk.Radiobutton(dialog, text="T-Beam", variable=section_type, value="tbeam").pack(fill='x', pady=2)
        
        # Set default
        section_type.set("rectangle")
        
        result = [None]  # use list to store result as nonlocal variable
        
        def on_ok():
            result[0] = section_type.get()
            dialog.destroy()
            
        ttk.Button(dialog, text="OK", command=on_ok).pack(pady=20)
        
        dialog.transient(self)
        dialog.grab_set()
        self.wait_window(dialog)
        
        return result[0]

    def _show_section_dimensions_dialog(self, section_type):
        """Show dialog for section-specific dimensions"""
        dialog = tk.Toplevel(self)
        dialog.title(f"Enter {section_type} Dimensions")
        dialog.geometry("300x400")
        
        entries = {}
        dimensions = {}
        
        if section_type == 'rectangle':
            ttk.Label(dialog, text="Width (mm):").pack(pady=5)
            entries['width'] = ttk.Entry(dialog)
            entries['width'].pack(pady=5)
            ttk.Label(dialog, text="Height (mm):").pack(pady=5)
            entries['height'] = ttk.Entry(dialog)
            entries['height'].pack(pady=5)
            
        elif section_type == 'round':
            ttk.Label(dialog, text="Diameter (mm):").pack(pady=5)
            entries['diameter'] = ttk.Entry(dialog)
            entries['diameter'].pack(pady=5)
            
        elif section_type == 'ibeam':
            ttk.Label(dialog, text="Height (mm):").pack(pady=5)
            entries['height'] = ttk.Entry(dialog)
            entries['height'].pack(pady=5)
            ttk.Label(dialog, text="Width (mm):").pack(pady=5)
            entries['width'] = ttk.Entry(dialog)
            entries['width'].pack(pady=5)
            ttk.Label(dialog, text="Web Thickness (mm):").pack(pady=5)
            entries['web_thickness'] = ttk.Entry(dialog)
            entries['web_thickness'].pack(pady=5)
            ttk.Label(dialog, text="Flange Thickness (mm):").pack(pady=5)
            entries['flange_thickness'] = ttk.Entry(dialog)
            entries['flange_thickness'].pack(pady=5)
            
        elif section_type == 'channel':
            ttk.Label(dialog, text="Height (mm):").pack(pady=5)
            entries['height'] = ttk.Entry(dialog)
            entries['height'].pack(pady=5)
            ttk.Label(dialog, text="Width (mm):").pack(pady=5)
            entries['width'] = ttk.Entry(dialog)
            entries['width'].pack(pady=5)
            ttk.Label(dialog, text="Web Thickness (mm):").pack(pady=5)
            entries['web_thickness'] = ttk.Entry(dialog)
            entries['web_thickness'].pack(pady=5)
            ttk.Label(dialog, text="Flange Thickness (mm):").pack(pady=5)
            entries['flange_thickness'] = ttk.Entry(dialog)
            entries['flange_thickness'].pack(pady=5)
            
        elif section_type == 'tbeam':
            ttk.Label(dialog, text="Height (mm):").pack(pady=5)
            entries['height'] = ttk.Entry(dialog)
            entries['height'].pack(pady=5)
            ttk.Label(dialog, text="Width (mm):").pack(pady=5)
            entries['width'] = ttk.Entry(dialog)
            entries['width'].pack(pady=5)
            ttk.Label(dialog, text="Web Thickness (mm):").pack(pady=5)
            entries['web_thickness'] = ttk.Entry(dialog)
            entries['web_thickness'].pack(pady=5)
            ttk.Label(dialog, text="Flange Thickness (mm):").pack(pady=5)
            entries['flange_thickness'] = ttk.Entry(dialog)
            entries['flange_thickness'].pack(pady=5)
        
        def on_ok():
            try:
                for key, entry in entries.items():
                    dimensions[key] = float(entry.get())
                dialog.destroy()
            except ValueError:
                messagebox.showerror("Error", "Please enter valid numbers for all dimensions")
        
        ttk.Button(dialog, text="OK", command=on_ok).pack(pady=20)
        
        dialog.transient(self)
        dialog.grab_set()
        self.wait_window(dialog)
        
        return dimensions if entries else None

    def _is_point_on_line_segment(self, px, py, x1, y1, x2, y2, epsilon=1e-6):
        """Check if a point (px, py) is on the line segment from (x1, y1) to (x2, y2)"""
        # Check if point is within bounding box of line segment
        if not (min(x1, x2) - epsilon <= px <= max(x1, x2) + epsilon and
                min(y1, y2) - epsilon <= py <= max(y1, y2) + epsilon):
            return False
            
        # Check if point is on the line (using cross product)
        cross_product = abs((py - y1) * (x2 - x1) - (px - x1) * (y2 - y1))
        return cross_product < epsilon

    def _delete_all(self):
        """Delete all nodes, elements, loads, and boundary conditions after confirmation"""
        if not self.solver.nodes:
            messagebox.showinfo('Info', 'No nodes to delete.')
            return
            
        confirm = messagebox.askyesno('Confirm Delete All', 
                                    'Are you sure you want to delete ALL nodes and elements?\n\nThis action cannot be undone!',
                                    icon='warning')
        if not confirm:
            return
            
        # Save the current state before making changes
        self._save_state("Before Delete All")
            
        # Clear all data structures
        self.solver.nodes.clear()
        self.solver.elements.clear()
        self.solver.loads.clear()
        self.solver.boundary_conditions.clear()
        self.solver.results.clear()
        
        # Reset temporary variables
        self.temp_node = None
        if self.temp_line:
            self.temp_line.remove()
            self.temp_line = None
            
        # Force mode to 'node' since no nodes exist
        self.mode_var.set('node')
        self.current_mode = 'node'
        
        # Update UI
        self._update_mode()
        self._update_plot()
        
        # Save the new state
        self._save_state("Delete All")
        
        messagebox.showinfo('Success', 'All nodes and elements have been deleted.')

    def _on_bc_type_selected(self, event):
        """Handle BC type selection from dropdown"""
        selected_bc_type = self.bc_type_var.get()
        if selected_bc_type == "Custom":
            self.custom_bc_frame.pack(fill='x', pady=2)
            # Set default values for custom BC
            self.bc_ux_var.set(True)
            self.bc_uy_var.set(True)
            self.bc_theta_var.set(False)  # Default to pinned (no rotation constraint)
        else:
            self.custom_bc_frame.pack_forget()
            # Preset values based on selection
            if selected_bc_type == "Fixed":
                self.bc_ux_var.set(True)
                self.bc_uy_var.set(True)
                self.bc_theta_var.set(True)
            elif selected_bc_type == "Pinned":
                self.bc_ux_var.set(True)
                self.bc_uy_var.set(True)
                self.bc_theta_var.set(False)
            elif selected_bc_type == "Roller-X":
                self.bc_ux_var.set(False)
                self.bc_uy_var.set(True)
                self.bc_theta_var.set(False)
            elif selected_bc_type == "Roller-Y":
                self.bc_ux_var.set(True)
                self.bc_uy_var.set(False)
                self.bc_theta_var.set(False)

    def _gui_apply_bc(self):
        """Apply the selected boundary condition"""
        try:
            nid = self._safe_int(self._entry_bn)
            bc_type = self.bc_type_var.get()
            
            # Check if node exists
            if nid not in self.solver.nodes:
                messagebox.showerror('Error', f'Node {nid} does not exist')
                return
                
            # Save the current state before making changes
            self._save_state(f"Before Apply BC to Node {nid}")
            
            # Clear any existing boundary condition for this node
            if nid in self.solver.boundary_conditions:
                self.solver.boundary_conditions.pop(nid)
                
            # Apply boundary condition based on type
            if bc_type == "Fixed":
                self.solver.add_boundary_condition(nid, ux=0, uy=0, th=0)
                bc_description = "Fixed"
            elif bc_type == "Pinned":
                self.solver.add_boundary_condition(nid, ux=0, uy=0, th=None)
                bc_description = "Pinned"
            elif bc_type == "Roller-X":
                self.solver.add_boundary_condition(nid, ux=None, uy=0, th=None)
                bc_description = "Roller (X free)"
            elif bc_type == "Roller-Y":
                self.solver.add_boundary_condition(nid, ux=0, uy=None, th=None)
                bc_description = "Roller (Y free)"
            elif bc_type == "Custom":
                # Get values from checkboxes
                ux = 0 if self.bc_ux_var.get() else None
                uy = 0 if self.bc_uy_var.get() else None
                th = 0 if self.bc_theta_var.get() else None
                self.solver.add_boundary_condition(nid, ux=ux, uy=uy, th=th)
                
                # Create description of custom BC
                constraints = []
                if ux == 0: constraints.append("X")
                if uy == 0: constraints.append("Y")
                if th == 0: constraints.append("Rotation")
                bc_description = f"Custom ({', '.join(constraints)} constrained)"
            
            # Update plot
            self._update_plot()
            
            # Update mode to ensure all features remain accessible
            self._update_mode()
            
            # Save the new state
            self._save_state(f"Apply {bc_description} BC to Node {nid}")
            
        except Exception as e:
            messagebox.showerror('Error', str(e))

    # Add function to delete boundary conditions
    def _gui_delete_bc(self):
        """Delete boundary condition from a node"""
        try:
            nid = self._safe_int(self._entry_bn)
            
            # Check if boundary condition exists
            if nid not in self.solver.boundary_conditions:
                messagebox.showwarning('Warning', f'No boundary condition exists at node {nid}')
                return
                
            # Ask for confirmation
            if not messagebox.askyesno('Confirm', f'Delete boundary condition at node {nid}?'):
                return
            
            # Save the current state before making changes
            self._save_state(f"Before Delete BC from Node {nid}")
                
            # Remove boundary condition
            del self.solver.boundary_conditions[nid]
            
            # Update plot
            self._update_plot()
            
            # Make sure mode is properly updated to allow for node deletion
            self._update_mode()
            
            # Save the new state
            self._save_state(f"Delete BC from Node {nid}")
            
        except Exception as e:
            messagebox.showerror('Error', str(e))

    def _gui_update_element(self):
        """Update the selected element with current material and section properties"""
        # Check if an element is selected
        if not self.element_var.get():
            messagebox.showwarning('Warning', 'Please select an element first')
            return
            
        # Get selected element ID
        eid = int(self.element_var.get().split(':')[0].split()[1])
        
        # Get selected material and section
        material_name = self.material_var.get()
        section_name = self.section_var.get()
        
        if not material_name or not section_name:
            messagebox.showwarning('Warning', 'Please select both material and section')
            return
            
        # Find material ID and section ID by name
        mat_id = None
        sec_id = None
        
        for mid, props in self.material_database.items():
            if props['name'] == material_name:
                mat_id = mid
                break
                
        for sid, props in self.section_database.items():
            if props['name'] == section_name:
                sec_id = sid
                break
                
        if mat_id is None or sec_id is None:
            messagebox.showwarning('Warning', 'Material or section not found')
            return
        
        # Save state before change
        self._save_state(f"Before Update Element {eid}")
            
        # Update the element
        self.solver.elements[eid]['mat'] = mat_id
        self.solver.elements[eid]['sec'] = sec_id
        self.solver.elements[eid]['edited'] = True
        
        # Update UI
        self._update_plot()
        self._update_mode()  # Ensure all modes are properly accessible
        
        # Save state after change
        self._save_state(f"Update Element {eid}")

    def _gui_update_all_elements(self):
        """Apply current material and section to all elements"""
        if not self.solver.elements:
            messagebox.showwarning('Warning', 'No elements exist to update')
            return
            
        # Get selected material and section
        material_name = self.material_var.get()
        section_name = self.section_var.get()
        
        if not material_name or not section_name:
            messagebox.showwarning('Warning', 'Please select both material and section')
            return
            
        # Find material ID and section ID by name
        mat_id = None
        sec_id = None
        
        for mid, props in self.material_database.items():
            if props['name'] == material_name:
                mat_id = mid
                break
                
        for sid, props in self.section_database.items():
            if props['name'] == section_name:
                sec_id = sid
                break
                
        if mat_id is None or sec_id is None:
            messagebox.showwarning('Warning', 'Material or section not found')
            return
            
        # Ask for confirmation
        if not messagebox.askyesno('Confirm', f'Apply material {material_name} and section {section_name} to all elements?'):
            return
        
        # Save state before changes
        self._save_state("Before Update All Elements")
            
        # Update all elements
        count = 0
        for eid in self.solver.elements:
            self.solver.elements[eid]['mat'] = mat_id
            self.solver.elements[eid]['sec'] = sec_id
            self.solver.elements[eid]['edited'] = True
            count += 1
            
        # Update UI
        self._update_plot()
        self._update_element_list()  # Refresh element list to show updated info
        self._update_mode()  # Ensure all modes are properly accessible
        
        # Save state after changes
        self._save_state("Update All Elements")

    def _show_coordinate_dialog(self, initial_coords, node_id=None):
        """Show dialog for fine-tuning node coordinates"""
        dialog = tk.Toplevel(self)
        
        # Set title based on whether we're editing an existing node or creating a new one
        if node_id is None:
            dialog.title("Adjust Node Coordinates")
        else:
            dialog.title(f"Edit Node {node_id} Coordinates")
            
        dialog.geometry("300x180")
        dialog.transient(self)
        dialog.grab_set()  # Make dialog modal
        
        # Set dialog position near the cursor
        x, y = initial_coords
        
        # Create content frame with padding
        content_frame = ttk.Frame(dialog, padding="10")
        content_frame.pack(fill='both', expand=True)
        
        # Add instruction text
        if node_id is None:
            instruction_text = "Fine-tune node coordinates:"
        else:
            instruction_text = f"Edit coordinates for Node {node_id}:"
            
        ttk.Label(content_frame, text=instruction_text, 
                 font=('Arial', 10)).pack(pady=(0, 10))
        
        # Unit display
        unit_text = self.distance_unit.get()
        
        # Create coordinate entry fields
        coord_frame = ttk.Frame(content_frame)
        coord_frame.pack(fill='x', pady=5)
        
        ttk.Label(coord_frame, text=f"X ({unit_text}):", width=10).grid(row=0, column=0, padx=5, pady=5)
        x_entry = ttk.Entry(coord_frame, width=15)
        x_entry.grid(row=0, column=1, padx=5, pady=5)
        x_entry.insert(0, f"{x:.3f}")
        
        ttk.Label(coord_frame, text=f"Y ({unit_text}):", width=10).grid(row=1, column=0, padx=5, pady=5)
        y_entry = ttk.Entry(coord_frame, width=15)
        y_entry.grid(row=1, column=1, padx=5, pady=5)
        y_entry.insert(0, f"{y:.3f}")
        
        # Focus on the x coordinate for immediate editing
        x_entry.focus_set()
        x_entry.selection_range(0, tk.END)
        
        result = [None]  # Use list to store result as nonlocal variable
        
        def on_ok():
            try:
                x_val = float(x_entry.get())
                y_val = float(y_entry.get())
                result[0] = (x_val, y_val)
                dialog.destroy()
            except ValueError:
                messagebox.showerror("Error", "Please enter valid numeric coordinates")
        
        def on_cancel():
            dialog.destroy()
        
        # Add buttons
        button_frame = ttk.Frame(content_frame)
        button_frame.pack(fill='x', pady=(10, 0))
        ttk.Button(button_frame, text="OK", command=on_ok).pack(side='right', padx=5)
        ttk.Button(button_frame, text="Cancel", command=on_cancel).pack(side='right', padx=5)
        
        # Bind Enter key to OK button
        dialog.bind("<Return>", lambda event: on_ok())
        dialog.bind("<Escape>", lambda event: on_cancel())
        
        # Wait for dialog to close
        self.wait_window(dialog)
        
        return result[0]

    def _diagnose_structure(self, analysis_mode):
        """Analyze the structure for specific issues and return a diagnostic report"""
        node_count = len(self.solver.nodes)
        element_count = len(self.solver.elements)
        boundary_count = len(self.solver.boundary_conditions)
        
        # Initialize results dictionary
        diagnostics = {
            'checklist': [],
            'summary': '',
            'critical_issues': 0
        }
        
        # Check 1: Verify structure has nodes
        has_nodes = node_count > 0
        if has_nodes:
            diagnostics['checklist'].append(
                ("Structure has nodes", True, f"{node_count} nodes defined")
            )
        else:
            diagnostics['checklist'].append(
                ("Structure has nodes", False, "No nodes defined in the structure")
            )
            diagnostics['critical_issues'] += 1
            
        # Check 2: Verify structure has elements
        has_elements = element_count > 0
        if has_elements:
            diagnostics['checklist'].append(
                ("Structure has elements", True, f"{element_count} elements defined")
            )
        else:
            diagnostics['checklist'].append(
                ("Structure has elements", False, "No elements defined in the structure")
            )
            diagnostics['critical_issues'] += 1
            
        # Check 3: Disconnected nodes check
        disconnected_nodes = []
        for nid in self.solver.nodes:
            connected = False
            for el in self.solver.elements.values():
                if nid in el['nodes']:
                    connected = True
                    break
            if not connected:
                disconnected_nodes.append(nid)
                
        if not disconnected_nodes:
            diagnostics['checklist'].append(
                ("All nodes are connected", True, "Every node is attached to at least one element")
            )
        else:
            diagnostics['checklist'].append(
                ("All nodes are connected", False, f"Nodes {', '.join(map(str, disconnected_nodes))} are not connected to any element")
            )
            diagnostics['critical_issues'] += 1
            
        # Check 4: Boundary condition count
        if analysis_mode == 'truss':
            min_constraints = 3  # Minimum for 2D truss - usually 3 reaction components
        else:  # 'frame'
            min_constraints = 3  # Minimum for 2D frame - usually 3 reaction components
            
        # Count actual constrained DOFs (not just boundary condition nodes)
        constrained_dofs = 0
        for bc in self.solver.boundary_conditions.values():
            if bc.get('ux') == 0:
                constrained_dofs += 1
            if bc.get('uy') == 0:
                constrained_dofs += 1
            if bc.get('th') == 0:
                constrained_dofs += 1
                
        has_sufficient_constraints = constrained_dofs >= min_constraints
        
        if has_sufficient_constraints:
            diagnostics['checklist'].append(
                ("Sufficient constraints", True, f"Structure has {constrained_dofs} constrained degrees of freedom")
            )
        else:
            diagnostics['checklist'].append(
                ("Sufficient constraints", False, f"Only {constrained_dofs} constrained degrees of freedom (minimum required: {min_constraints})")
            )
            diagnostics['critical_issues'] += 1
            
        # Check 5: Appropriate element types (for frame/truss mode)
        if analysis_mode == 'truss':
            incorrect_elements = [eid for eid, el in self.solver.elements.items() if el['type'] != 'truss']
            if not incorrect_elements:
                diagnostics['checklist'].append(
                    ("Element types match analysis mode", True, "All elements are truss elements")
                )
            else:
                diagnostics['checklist'].append(
                    ("Element types match analysis mode", False, f"Elements {', '.join(map(str, incorrect_elements))} are not truss elements")
                )
                # This is a warning rather than critical error
        else:  # frame mode - both truss and beam elements are allowed
            diagnostics['checklist'].append(
                ("Element types match analysis mode", True, "Current elements work with frame analysis")
            )
            
        # Check 6: Loads present (not critical, but helpful to know)
        load_count = len(self.solver.loads)
        if load_count > 0:
            diagnostics['checklist'].append(
                ("Structure has loads", True, f"{load_count} load(s) defined")
            )
        else:
            diagnostics['checklist'].append(
                ("Structure has loads", False, "No loads defined - results will be trivial")
            )
        
        # Check 7: Static determinacy check using the equation 2n = m + r
        # For a statically determinate structure: 2n = m + r
        # Where: n = number of nodes, m = number of elements, r = number of support reactions
        n = node_count
        m = element_count
        
        # Calculate actual number of reactions (constrained DOFs)
        r = 0
        for nid, bc in self.solver.boundary_conditions.items():
            if bc.get('ux') == 0:
                r += 1
            if bc.get('uy') == 0:
                r += 1
            if bc.get('th') == 0:
                r += 1
        
        static_check = 2*n - (m + r)
        
        if static_check == 0:
            static_status = "statically determinate"
            diagnostics['checklist'].append(
                ("Static determinacy", True, f"Structure is statically determinate (2n = m + r: 2×{n} = {m} + {r})")
            )
        elif static_check < 0:
            static_status = "statically indeterminate"
            degree = abs(static_check)
            diagnostics['checklist'].append(
                ("Static determinacy", False, f"Structure is statically indeterminate to degree {degree} (2n < m + r: 2×{n} < {m} + {r})")
            )
        else:  # static_check > 0
            static_status = "mechanism"
            diagnostics['checklist'].append(
                ("Static determinacy", False, f"Structure is a mechanism with {static_check} degrees of freedom (2n > m + r: 2×{n} > {m} + {r})")
            )
            diagnostics['critical_issues'] += 1
        
        # Check 8: Look for potential mechanisms
        potential_mechanism = False
        
        # Simple check - if we have only pinned connections in a frame, it might be a mechanism
        if analysis_mode == 'frame' and element_count > 0:
            # Count fixed supports
            fixed_supports = sum(1 for bc in self.solver.boundary_conditions.values() 
                              if bc.get('ux') == 0 and bc.get('uy') == 0 and bc.get('th') == 0)
            
            # If no fixed supports and only one roller/pin, likely a mechanism
            if fixed_supports == 0 and constrained_dofs < 4:
                potential_mechanism = True
                
        # Add mechanism warning if applicable
        if potential_mechanism and static_status != "mechanism":
            diagnostics['checklist'].append(
                ("No potential mechanisms", False, "Structure might contain a mechanism - check for rigid body motion")
            )
        elif static_status == "mechanism":
            # Already reported as a mechanism in the static determinacy check
            pass
        else:
            diagnostics['checklist'].append(
                ("No potential mechanisms", True, "No obvious mechanisms detected")
            )
            
        # Generate overall summary
        if diagnostics['critical_issues'] == 0:
            if static_status == "statically indeterminate":
                # Not critical but worth mentioning
                diagnostics['summary'] = (
                    f"Your structure is {static_status}. This means it has redundant members or constraints, "
                    f"which can be beneficial for safety but may lead to more complex analysis. "
                    f"Using the equation 2n = m + r, where n={n} (nodes), m={m} (members), and r={r} (reactions), "
                    f"we get 2×{n} = {2*n} < {m + r} = {m} + {r}, indicating {abs(static_check)} degree(s) of redundancy."
                )
            else:
                diagnostics['summary'] = (
                    f"Your structure is {static_status} and all basic requirements for analysis seem to be met. "
                    f"Using the equation 2n = m + r, where n={n} (nodes), m={m} (members), and r={r} (reactions), "
                    f"we get 2×{n} = {2*n} = {m + r} = {m} + {r}, which indicates a statically determinate structure."
                )
        else:
            if static_status == "mechanism":
                diagnostics['summary'] = (
                    f"Your structure is a mechanism with {static_check} degree(s) of freedom. "
                    f"A mechanism can move without deforming, meaning it cannot carry load in a stable way. "
                    f"Using the equation 2n = m + r, where n={n} (nodes), m={m} (members), and r={r} (reactions), "
                    f"we get 2×{n} = {2*n} > {m + r} = {m} + {r}. "
                    f"Fix this by adding more members or supports to properly constrain the structure."
                )
            else:
                diagnostics['summary'] = (
                    f"Found {diagnostics['critical_issues']} critical issues. "
                    f"Fix the items marked with ✗ above before attempting to solve. "
                    f"The most common issue is insufficient constraints (boundary conditions)."
                )
            
        return diagnostics

    def _save_state(self, action_name=""):
        """Save current state to history"""
        # Deep copy the current state
        state = {
            'nodes': {str(k): v.tolist() for k, v in self.solver.nodes.items()},
            'elements': copy.deepcopy(self.solver.elements),
            'boundary_conditions': copy.deepcopy(self.solver.boundary_conditions),
            'loads': copy.deepcopy(self.solver.loads),
            'plot_limits': copy.deepcopy(self.plot_limits),
            'action': action_name
        }
        
        # If we're not at the end of the history, truncate it
        if self.history_index < len(self.history) - 1:
            self.history = self.history[:self.history_index + 1]
            
        # Add new state
        self.history.append(state)
        self.history_index = len(self.history) - 1
        
        # Limit history size
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
            self.history_index = len(self.history) - 1
            
        # Update button states
        self._update_history_buttons()

    def _restore_state(self, state):
        """Restore a saved state"""
        # Restore nodes
        self.solver.nodes = {int(k): np.array(v, dtype=float) for k, v in state['nodes'].items()}
        
        # Restore elements
        self.solver.elements = state['elements']
        
        # Restore boundary conditions
        self.solver.boundary_conditions = state['boundary_conditions']
        
        # Restore loads
        self.solver.loads = state['loads']
        
        # Restore plot limits
        self.plot_limits = state['plot_limits']
        
        # Update UI
        self._update_plot()
        self._update_node_list()
        self._update_element_list()
        self._update_mode()  # This will update visibility of various controls

    def _undo(self):
        """Undo the last action"""
        if self.history_index > 0:
            self.history_index -= 1
            self._restore_state(self.history[self.history_index])
            self._update_history_buttons()

    def _redo(self):
        """Redo the previously undone action"""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self._restore_state(self.history[self.history_index])
            self._update_history_buttons()

    def _update_history_buttons(self):
        """Update the state of the undo/redo buttons based on history"""
        # Undo button state
        if self.history_index > 0:
            self.undo_button['state'] = 'normal'
        else:
            self.undo_button['state'] = 'disabled'
            
        # Redo button state
        if self.history_index < len(self.history) - 1:
            self.redo_button['state'] = 'normal'
        else:
            self.redo_button['state'] = 'disabled'

    # ---------------- Helper functions for geometry ------------------
    def _get_closest_point_on_segment(self, p, a, b):
        """Return the closest point on segment ab to point p."""
        px, py = p
        ax, ay = a
        bx, by = b

        segment_vec = np.array([bx - ax, by - ay])
        p_to_a_vec = np.array([px - ax, py - ay])

        segment_len_sq = segment_vec[0]**2 + segment_vec[1]**2
        if segment_len_sq == 0: # Segment is a point
            return ax, ay

        # Project p_to_a_vec onto segment_vec
        # t is the projection parameter: 0 means point a, 1 means point b
        t = np.dot(p_to_a_vec, segment_vec) / segment_len_sq

        if t < 0: # Closest point is a
            return ax, ay
        elif t > 1: # Closest point is b
            return bx, by
        else: # Closest point is along the segment
            closest_x = ax + t * segment_vec[0]
            closest_y = ay + t * segment_vec[1]
            return closest_x, closest_y

    def _find_closest_element_and_snap_point(self, click_x, click_y, snap_threshold_data_units):
        """
        Find the closest element to the click point and the snapped coordinates on that element.
        Returns (element_id, (snapped_x, snapped_y)) or (None, None).
        The snap_threshold is in data coordinate units.
        """
        closest_element_id = None
        min_dist_to_element_line = float('inf')
        best_snap_point = None

        for eid, el_props in self.solver.elements.items():
            n1_id, n2_id = el_props['nodes']
            if n1_id not in self.solver.nodes or n2_id not in self.solver.nodes:
                continue # Skip if nodes don't exist

            node1_coords = self.solver.nodes[n1_id]
            node2_coords = self.solver.nodes[n2_id]

            snapped_x, snapped_y = self._get_closest_point_on_segment(
                (click_x, click_y), node1_coords, node2_coords
            )
            
            dist_sq = (click_x - snapped_x)**2 + (click_y - snapped_y)**2
            
            if dist_sq < snap_threshold_data_units**2:
                if dist_sq < min_dist_to_element_line:
                    min_dist_to_element_line = dist_sq
                    closest_element_id = eid
                    best_snap_point = (snapped_x, snapped_y)
        
        if closest_element_id is not None:
            return closest_element_id, best_snap_point
        return None, None

    def _gui_identify_zero_force_members(self):
        if 'forces' not in self.solver.results:
            messagebox.showwarning('Info', 'Please run Solve first to calculate forces.')
            return

        self.zero_force_members.clear()
        zero_force_member_ids = []
        threshold = 5e-3  # Force magnitude below which a member is considered zero-force. Changed from 1e-6.

        for eid, el in self.solver.elements.items():
            # Ensure element type is truss-like (I very small) if we want to be strict
            # For now, we identify based on axial force regardless of I, assuming user intends a truss analysis for this feature.
            sec_props = self.solver.sections.get(el['sec'])
            is_truss_like = sec_props and sec_props['I'] < 1e-9 # Check if I is negligible

            axial_force = self.solver.get_element_axial_force(eid)
            if axial_force is not None and abs(axial_force) < threshold:
                # Optionally, only mark if is_truss_like for strictness
                # if is_truss_like:
                self.zero_force_members.add(eid)
                zero_force_member_ids.append(str(eid))
        
        if zero_force_member_ids:
            message = f"Identified {len(zero_force_member_ids)} zero-force member(s): {', '.join(zero_force_member_ids)}\n\n"
            message += "These members will be shown with a dashed orange line and orange ID."
            messagebox.showinfo("Zero-Force Members", message)
        else:
            messagebox.showinfo("Zero-Force Members", "No zero-force members identified (below threshold). Ensure you are analyzing a truss structure (elements with I approx 0).")

        self._update_plot() # Redraw to show highlighting

# ---------- run GUI -------------------------------------------------------
if __name__=='__main__':
    root = tk.Tk()
    root.state('zoomed')  # Start maximized
    app = StructuralGUI(root)
    root.mainloop()

