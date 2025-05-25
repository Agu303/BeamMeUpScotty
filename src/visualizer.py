import numpy as np
import matplotlib.pyplot as plt

class StructureVisualizer:
    def __init__(self, solver):
        self.solver=solver

    def plot(self, ax=None, deformed=False, scale=100):
        if ax is None:
            fig,ax = plt.subplots(figsize=(7,6))
        # plot elements
        for eid,el in self.solver.elements.items():
            n1,n2 = el['nodes']
            x1,y1 = self.solver.nodes[n1]
            x2,y2 = self.solver.nodes[n2]
            if deformed and 'displacements' in self.solver.results:
                U=self.solver.results['displacements']
                d1=U[3*(n1-1):3*(n1-1)+2]*scale
                d2=U[3*(n2-1):3*(n2-1)+2]*scale
                ax.plot([x1,x2],[y1,y2],color='k',lw=1,alpha=0.3)
                ax.plot([x1+d1[0],x2+d2[0]],[y1+d1[1],y2+d2[1]],
                        linestyle=':',color='r',lw=2,label='deformed' if eid==list(self.solver.elements.keys())[0] else "")
            else:
                ax.plot([x1,x2],[y1,y2],color='k',lw=2)
        # plot nodes
        for nid,(x,y) in self.solver.nodes.items():
            ax.plot(x,y,'bo',ms=6)
            ax.text(x,y+0.02,f"{nid}",fontsize=8,ha='center')
        ax.set_aspect('equal'); ax.grid(True)
        ax.set_xlabel('X'); ax.set_ylabel('Y')
        if deformed: ax.legend(loc='best')
        return ax