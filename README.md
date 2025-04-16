# BeamMeUpScotty

<p align="center">
<img src="BeamMeUp.png" alt="Alt text" width="30%"/>
</p>

BeamMeUpScotty is a 2D structural analysis tool developed in Python. It enables users to model, analyze, and visualize **trusses** and **beams** using **numerical approximation** of analytical methods, with an eventual transition to **finite element methods (FEM)**. The project is intended for practicing both **numerical methods** and **finite element methods** in structural analysis.

## Features

### Structural Analysis Capabilities

- **2D Analysis of Truss and Beam Structures**:  
  Analyze trusses (axial force only) and Euler-Bernoulli beams (bending and shear). 

- **Material Properties**:  
  Define Young's modulus, cross-sectional area, and moment of inertia for each element.

- **Boundary Conditions**:  
  Apply various support types (fixed, roller, pinned) and external loads (point loads, distributed loads, moments).

- **Numerical Approximation Solver**:  
  Assembles global stiffness matrices, applies input boundary conditions, and solves for nodal displacements using **numerical methods**.

### Visualization

- **Structure Plotting**:  
  Visualize undeformed and deformed structures.

- **Force Diagrams**:  
  Generate shear force and bending moment diagrams for beams and frames.

- **Interactive Interface**:  
  User-friendly interface for model creation and result interpretation.

## Planned Features

- **Solver for Beams with Varied Cross Sections**  
  Enhance beam analysis to handle beams with varying cross-sections and complex loading.

- **GUI**  
  Implement a graphical user interface to make the tool more accessible and interactive.

- **Result Export**  
  Allow result export to `.csv` and `.pdf` formats for easy reporting.

<p align="center">
<img src="cs_beams.png" alt="Alt text" width="20%"/>
</p>

## Installation

... (Instructions for installing the project, such as `pip install` or cloning the repo)

## Usage

... (Basic instructions for using the project, including examples of how to run the solver)

## Requirements

... (List of Python libraries and dependencies, such as `numpy`, `scipy`, etc.)

## License

MIT License
